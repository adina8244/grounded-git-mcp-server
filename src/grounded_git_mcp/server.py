from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from grounded_git_mcp.resources import diff_range, repo_tree
from grounded_git_mcp.resources.file_at_ref import read_file_at_ref
from grounded_git_mcp.tools import (
    blame,
    detect_conflicts,
    diff_summary,
    grep,
    log,
    repo_info,
    show_commit,
    status_porcelain,
)
from grounded_git_mcp.tools.approval_flow import execute_confirmed, propose_git_command

mcp = FastMCP("grounded-git-mcp")


@mcp.tool()
def repo_info_tool(root: str = ".") -> dict:
    """
    Purpose
    -------
    Return high-level repository metadata for a given `root`.

    When to use
    -----------
    - First call in most sessions to confirm the repo root and current HEAD/branch.
    - Before any propose/execute flow, to bind reasoning to the actual repo state.

    Parameters
    ----------
    root:
        Path to the repository root (or any path inside it). Resolved server-side.

    Returns
    -------
    dict:
        Repository metadata such as resolved root, HEAD/branch, and optionally remotes.

    Safety
    ------
    Read-only. Does not mutate the repository.

    Example
    -------
    repo_info_tool(root=".")
    """
    return repo_info(root=root)


@mcp.tool()
def status_porcelain_tool(root: str = ".", max_entries: int = 200) -> dict:
    """
    Purpose
    -------
    Return `git status --porcelain` output (machine-friendly, bounded).

    When to use
    -----------
    - Determine which files are modified/untracked/staged.
    - Gate write proposals (e.g., require_clean=True) based on actual working tree state.

    Parameters
    ----------
    root:
        Repository root (or a path inside it). Resolved server-side.
    max_entries:
        Hard ceiling to prevent runaway output on large repos.

    Returns
    -------
    dict:
        Stable status representation (porcelain) + flags that indicate truncation.

    Limits
    ------
    Output may be truncated when exceeding `max_entries` or internal output limits.

    Safety
    ------
    Read-only.

    Example
    -------
    status_porcelain_tool(root=".", max_entries=200)
    """
    return status_porcelain(root=root, max_entries=max_entries)


@mcp.tool()
def diff_summary_tool(root: str = ".", staged: bool = False, against: str | None = None) -> dict:
    """
    Purpose
    -------
    Return a compact, bounded diff summary for fast inspection.

    When to use
    -----------
    - Quickly list changed files (before requesting full diffs or file content).
    - Decide between `read_file_resource` and `diff_range_resource`.

    Parameters
    ----------
    staged:
        If True, summarize staged changes; otherwise summarize working tree changes.
    against:
        Optional ref/commit to compare against (tool-defined semantics).

    Returns
    -------
    dict:
        Summary information (e.g., changed files + lightweight stats) suitable for planning next tool calls.

    Limits
    ------
    Summary is intentionally compact; request `diff_range_resource` for detailed patches.

    Safety
    ------
    Read-only.

    Example
    -------
    diff_summary_tool(root=".", staged=False)
    """
    return diff_summary(root=root, staged=staged, against=against)


@mcp.tool()
def log_tool(root: str = ".", n: int = 20) -> dict:
    """
    Purpose
    -------
    Return the most recent commit log entries (bounded).

    When to use
    -----------
    - Identify recent changes / candidate commits for `show_commit_tool` or `diff_range_resource`.
    - Provide context for blame/root-cause reasoning.

    Parameters
    ----------
    n:
        Maximum number of commits to return.

    Returns
    -------
    dict:
        A bounded list of recent commits with identifiers and summary metadata.

    Safety
    ------
    Read-only.

    Example
    -------
    log_tool(root=".", n=20)
    """
    return log(root=root, n=n)


@mcp.tool()
def show_commit_tool(commit: str, root: str = ".", patch: bool = True) -> dict:
    """
    Purpose
    -------
    Return details for a specific commit, optionally including its patch.

    When to use
    -----------
    - Inspect what exactly changed in a commit.
    - Validate whether a suspected change introduced a bug before proposing a fix.

    Parameters
    ----------
    commit:
        Commit hash or revspec.
    patch:
        If True, include the commit diff (still bounded by global output limits).

    Returns
    -------
    dict:
        Commit metadata and (optionally) a bounded patch representation.

    Limits
    ------
    Patch output may be truncated by internal output caps.

    Safety
    ------
    Read-only.

    Example
    -------
    show_commit_tool(commit="HEAD~1", root=".", patch=True)
    """
    return show_commit(commit=commit, root=root, patch=patch)


@mcp.tool()
def grep_tool(
    pattern: str,
    root: str = ".",
    pathspec: str | None = None,
    ignore_case: bool = False,
) -> dict:
    """
    Purpose
    -------
    Search repository text for a pattern (bounded).

    When to use
    -----------
    - Locate relevant files quickly before reading them.
    - Find occurrences of a symbol/function/config key.

    Parameters
    ----------
    pattern:
        Search pattern (string).
    pathspec:
        Optional path filter to narrow search scope (e.g., "src/", "*.py").
    ignore_case:
        Case-insensitive search if True.

    Returns
    -------
    dict:
        Bounded match list (file + line/snippet metadata as supported by the underlying tool).

    Limits
    ------
    Intended as a locator primitive; results may be truncated.

    Safety
    ------
    Read-only.

    Example
    -------
    grep_tool(pattern="SafeGitRunner", root=".", pathspec="src/", ignore_case=False)
    """
    return grep(pattern=pattern, root=root, pathspec=pathspec, ignore_case=ignore_case)


@mcp.tool()
def blame_tool(file_path: str, root: str = ".", start_line: int = 1, end_line: int = 200) -> dict:
    """
    Purpose
    -------
    Return blame information for a file line range.

    When to use
    -----------
    - Root-cause analysis: map suspicious lines to the introducing commit.
    - Validate authorship/timing of changes before proposing a fix.

    Parameters
    ----------
    file_path:
        Repository-relative path to the file.
    start_line, end_line:
        Inclusive line range (bounded by defaults to keep output small).

    Returns
    -------
    dict:
        Line-level blame metadata (commit id, author/time, line text as supported).

    Limits
    ------
    Keep ranges small. Expand only when necessary.

    Safety
    ------
    Read-only.

    Example
    -------
    blame_tool(file_path="src/grounded_git_mcp/core/git_runner.py", root=".", start_line=1, end_line=80)
    """
    return blame(file_path=file_path, root=root, start_line=start_line, end_line=end_line)


@mcp.tool()
def detect_conflicts_tool(root: str = ".") -> dict:
    """
    Purpose
    -------
    Detect unresolved merge conflict state / conflict markers.

    When to use
    -----------
    - Before proposing or executing any write operation.
    - As a safety gate: prefer not to mutate when conflicts are present.

    Returns
    -------
    dict:
        Conflict detection signal and any supporting details.

    Safety
    ------
    Read-only.

    Example
    -------
    detect_conflicts_tool(root=".")
    """
    return detect_conflicts(root=root)


@mcp.tool()
def propose_git_command_tool(
    root: str = ".",
    args: list[str] | None = None,
    expected_branch: str | None = None,
    require_clean: bool = False,
) -> dict:
    """
    Purpose
    -------
    Propose (never execute) a git command under the server's approval/safety model.

    This is Step 1 of the write flow:
    - Validates command against safety policy
    - Classifies risk level and explains why
    - Generates a one-time confirmation token + enforced preconditions
    - Writes a durable audit record for traceability

    When to use
    -----------
    - Any time the agent wants to run a potentially mutating git command.
    - After read-only investigation identified a concrete, minimal change.

    Parameters
    ----------
    args:
        Git argv list, e.g. ["commit", "-m", "Fix ..."] (no shell string).
        If None, treated as empty list.
    expected_branch:
        Optional guardrail: only allow execution if current branch matches.
    require_clean:
        If True, require a clean working tree at execution time.

    Returns
    -------
    dict:
        Proposal payload including:
        - `confirmation_id` (one-shot token)
        - `preconditions` (branch/clean/conflict guards)
        - `classification` (risk level + reasons)
        - `normalized_args` / command fingerprint (tool-defined)

    Safety
    ------
    Does not mutate the repo. Execution requires explicit confirmation via `execute_confirmed_tool`.

    Example
    -------
    propose_git_command_tool(
        root=".",
        args=["commit", "-am", "Fix README wording"],
        expected_branch="main",
        require_clean=True,
    )
    """
    return propose_git_command(
        root=root,
        args=args or [],
        expected_branch=expected_branch,
        require_clean=require_clean,
    )


@mcp.tool()
def execute_confirmed_tool(root: str = ".", confirmation_id: str = "", user_confirmation: str = "") -> dict:
    """
    Purpose
    -------
    Execute a previously proposed git command after explicit user confirmation.

    This is Step 2 of the write flow:
    - Validates confirmation token (one-shot / expiry)
    - Re-checks all preconditions (branch/HEAD/clean state/conflicts)
    - Executes the exact proposed argv (bound to confirmation)
    - Persists an audit record with the execution result

    When to use
    -----------
    - Only after `propose_git_command_tool` returned a `confirmation_id`.
    - Only after the user explicitly confirmed execution in the chat UI.

    Parameters
    ----------
    confirmation_id:
        One-time token from proposal. Must be provided.
    user_confirmation:
        Human confirmation string/flag (tool-defined), used for audit clarity.

    Returns
    -------
    dict:
        Execution result including stdout/stderr/exit_code and audit metadata.

    Safety
    ------
    Enforces one-shot approval and preconditions to prevent replay/stale execution.

    Example
    -------
    execute_confirmed_tool(root=".", confirmation_id="<id>", user_confirmation="approved")
    """
    return execute_confirmed(root=root, confirmation_id=confirmation_id, user_confirmation=user_confirmation)


# Resources (read-only, addressable by URI)


@mcp.resource("repo://{root}/{ref}/tree")
def repo_tree_resource(root: str = ".", ref: str = "HEAD") -> dict:
    """
    Resource
    --------
    List repository tree entries at a specific ref (bounded).

    When to use
    -----------
    - Browse structure before reading files.
    - Quickly discover paths relevant to a feature/bug.

    Parameters
    ----------
    ref:
        Git ref/commit (default HEAD) to avoid ambiguity between working tree and committed state.

    Returns
    -------
    dict:
        Bounded tree listing with paths (and metadata as supported by the underlying resource).

    Limits
    ------
    Tree output is bounded/truncated for large repos.

    Safety
    ------
    Read-only.

    Example
    -------
    repo://./HEAD/tree
    """
    return repo_tree(root=root, ref=ref)


@mcp.resource("repo://{root}/{ref}/file/{path}")
def read_file_resource(root: str = ".", ref: str = "HEAD", path: str = "") -> dict:
    """
    Resource
    --------
    Read file content at a given ref (default HEAD).

    When to use
    -----------
    - Inspect exact committed content at a ref (stable for reasoning and diffs).
    - Avoid working-tree ambiguity when debugging.

    Parameters
    ----------
    path:
        Repository-relative path. Must be provided.

    Returns
    -------
    dict:
        File content payload (and metadata as supported).

    Safety
    ------
    Read-only.

    Example
    -------
    repo://./HEAD/file/src/grounded_git_mcp/server.py
    """
    return read_file_at_ref(root=root, ref=ref, path=path)


@mcp.resource("repo://{root}/diff?base={base}&head={head}&triple_dot={triple_dot}")
def diff_range_resource(
    root: str = ".",
    base: str = "HEAD~1",
    head: str = "HEAD",
    triple_dot: bool = False,
) -> dict:
    """
    Resource
    --------
    Compute a diff between two revspecs (bounded).

    When to use
    -----------
    - Review changes across commits (e.g., base->head) with a concrete patch.
    - Validate a proposed change before execution.

    Parameters
    ----------
    base, head:
        Refs/commits defining the range.
    triple_dot:
        If True, uses `base...head` semantics (merge-base) vs `base..head`.

    Returns
    -------
    dict:
        Bounded diff payload. Intended for reasoning; may be truncated for very large patches.

    Safety
    ------
    Read-only.

    Example
    -------
    repo://./diff?base=HEAD~1&head=HEAD&triple_dot=False
    """
    return diff_range(root=root, base=base, head=head, triple_dot=triple_dot, pathspec=None)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
