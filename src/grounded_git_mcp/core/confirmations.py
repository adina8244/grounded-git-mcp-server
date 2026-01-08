from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _now() -> int:
    """Unix timestamp (seconds). Kept as a function for testability/mocking."""
    return int(time.time())


def _sha256_text(s: str) -> str:
    """Hash helper used for deterministic identifiers and command fingerprints."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _stable_cmd_text(args: list[str]) -> str:
    """
    Create a stable, unambiguous command representation for hashing/auditing.

    We avoid shell-joined strings to prevent ambiguity/injection-like edge cases
    when commands contain spaces/quotes.
    """
    return "\n".join(args)


@dataclass(frozen=True)
class Preconditions:
    """Execution preconditions enforced at confirm-time to avoid stale/unsafe writes."""
    expected_head: str | None = None
    expected_branch: str | None = None
    require_clean: bool = False
    require_no_conflicts: bool = True


@dataclass
class Confirmation:
    """
    One-time confirmation token produced during proposal and consumed during execution.

    Security properties:
    - bounded lifetime (`expires_at`)
    - bounded usage (`max_uses`, default 1)
    - binds execution to an exact command (`cmd_hash`) + repo root
    """
    confirmation_id: str
    root: str
    args: list[str]
    classification: dict[str, Any]
    cmd_hash: str
    created_at: int
    expires_at: int
    max_uses: int = 1
    used: int = 0
    preconditions: Preconditions = Preconditions()

    def is_expired(self) -> bool:
        """True if the confirmation is past its expiration time."""
        return _now() > self.expires_at

    def can_use(self) -> bool:
        """True if not expired and the token was not consumed beyond `max_uses`."""
        return (not self.is_expired()) and self.used < self.max_uses


class FileConfirmationStore:
    """
    Minimal durable store:
      .grounded_git_mcp/confirmations.json
      .grounded_git_mcp/audit.jsonl
    """

    def __init__(self, repo_root: Path) -> None:
        """
        Create (or open) the durable approval store under the repository.

        The store lives inside `.grounded_git_mcp/` so approvals are:
        - local to the repo
        - transparent to the user (plain JSON/JSONL)
        """
        self._dir = repo_root / ".grounded_git_mcp"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db = self._dir / "confirmations.json"
        self._audit = self._dir / "audit.jsonl"

        if not self._db.exists():
            self._db.write_text("{}", encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        """Load confirmations from disk (best-effort empty on missing/blank)."""
        return json.loads(self._db.read_text(encoding="utf-8") or "{}")

    def _save(self, data: dict[str, Any]) -> None:
        """
        Persist confirmations to disk using an atomic write pattern.

        Atomic write (tmp + replace) prevents partial/corrupted state if the process crashes mid-write.
        """
        tmp = self._db.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._db)

    def put(self, c: Confirmation) -> None:
        """Persist a proposed confirmation and append an audit record."""
        data = self._load()
        # Durable audit trail:
        # Keep an append-only record of proposed approvals for post-hoc review and accountability.
        data[c.confirmation_id] = asdict(c)
        self._save(data)
        self.audit("proposed", c.confirmation_id, extra={"classification": c.classification})

    def get(self, confirmation_id: str) -> Confirmation | None:
        """Return a confirmation by id, or None if it does not exist."""
        data = self._load()
        raw = data.get(confirmation_id)
        if not raw:
            return None
        raw["preconditions"] = Preconditions(**(raw.get("preconditions") or {}))
        return Confirmation(**raw)

    def mark_used(self, c: Confirmation, result: dict[str, Any]) -> None:
        """Mark a confirmation as consumed and append an execution audit record."""
        data = self._load()
        raw = data.get(c.confirmation_id)
        if not raw:
            return
        
        raw["used"] = int(raw.get("used", 0)) + 1
        data[c.confirmation_id] = raw
        self._save(data)
        self.audit("executed", c.confirmation_id, extra={"result": result})

    # One-shot enforcement: prevents replay of approvals.
    def audit(self, action: str, confirmation_id: str, extra: dict[str, Any] | None = None) -> None:
        """Append an audit line (JSONL) for transparency and post-hoc review."""
        line = {
            "ts": _now(),
            "action": action,
            "confirmation_id": confirmation_id,
            **(extra or {}),
        }
        with self._audit.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def new_confirmation_id(root: Path, args: list[str]) -> str:
    # deterministic-ish id is fine, but still unique enough: time + hash
    """Generate a short-lived unique id for a proposed command within a repo."""
    seed = f"{root.resolve()}\n{_now()}\n{_stable_cmd_text(args)}"
    return _sha256_text(seed)[:16]


def command_hash(args: list[str]) -> str:
    """Stable fingerprint of a command used to bind confirmation -> exact argv."""
    return _sha256_text(_stable_cmd_text(args))
