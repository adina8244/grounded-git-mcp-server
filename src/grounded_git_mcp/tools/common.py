from __future__ import annotations

from pathlib import Path

from ..core.git_runner import GitRunnerConfig, SafeGitRunner
from ..core.security import resolve_root


_DEFAULT_CFG = GitRunnerConfig(timeout_s=3.0, max_output_chars=80_000)


def make_runner(root: str = ".") -> SafeGitRunner:
    """
    Build a SafeGitRunner for the given root using the project defaults.

    Centralizing runner creation guarantees consistent limits/timeouts across all tools.
    """
    return SafeGitRunner(root=resolve_root(root), config=_DEFAULT_CFG)


def clean_lines(s: str) -> list[str]:
    """
    Normalize multi-line output into a list of lines.

    Kept as a helper for consistent downstream formatting/parsing.
    """
    return [ln for ln in s.splitlines() if ln is not None]
