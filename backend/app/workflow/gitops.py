"""
Git operations for the lifecycle, always as argv lists (never a shell string).

* The Development Agent works in a dedicated `git worktree` on a new branch
  based on the commit that was onboarded. The onboarded checkout (which the
  index/retrieval layer reads) and the default branch are never modified.
* Commits are created with hooks disabled and a fixed author identity.
* Credentials are passed per-invocation through an HTTP header and are never
  written to .git/config, a remote URL, a log line or a stored error.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import ValidationError


class GitCommandFailed(Exception):
    def __init__(self, args: list[str], returncode: int, output: str):
        self.returncode = returncode
        self.output = output
        super().__init__(f"git {' '.join(args[:3])} failed (exit {returncode}): {output[-800:]}")


def _scrub(text: str) -> str:
    from app.core.redaction import redact
    return redact(text)


def diagnose_http(status: int, body, headers: dict | None = None) -> str:
    """Actionable, credential-free explanation of a provider failure."""
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    msg = _scrub(str((body or {}).get("message", "") if isinstance(body, dict) else body))[:300]
    if status == 401:
        return f"authentication failed (HTTP 401): GIT_PROVIDER_TOKEN is missing, invalid or expired. {msg}"
    if status == 403:
        if headers.get("x-ratelimit-remaining") == "0" or "rate limit" in msg.lower():
            return f"the provider's API rate limit was reached (HTTP 403); retry after {headers.get('retry-after') or headers.get('x-ratelimit-reset') or 'a while'}. {msg}"
        return f"permission denied (HTTP 403): the token lacks write access to this repository (needs contents:write + pull_requests:write). {msg}"
    if status == 404:
        return f"not found (HTTP 404): the repository does not exist or the token cannot see it. {msg}"
    if status == 422:
        return f"the provider rejected the request (HTTP 422): {msg}"
    if status == 429:
        return f"rate limited (HTTP 429); retry after {headers.get('retry-after') or 'a while'}. {msg}"
    return f"HTTP {status}: {msg}"


def git(args: list[str], cwd: Path, *, timeout: int = 120, check: bool = True,
        extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env, check=False,
    )
    if check and proc.returncode != 0:
        raise GitCommandFailed(args, proc.returncode, _scrub((proc.stderr or "") + (proc.stdout or "")))
    return proc


_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")


def validate_branch_name(name: str) -> str:
    if not _BRANCH_RE.match(name) or ".." in name or name.endswith(".lock") or name.endswith("/") or "//" in name:
        raise ValidationError(f"Unsafe branch name: {name!r}")
    return name


def rev_parse(cwd: Path, ref: str) -> str:
    return git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd).stdout.strip()


def prepare_worktree(workspace: Path, worktree_dir: Path, *, branch: str, base_sha: str, default_branch: str) -> None:
    """Create `worktree_dir` on a NEW branch at `base_sha`. Refuses to touch the default branch."""
    validate_branch_name(branch)
    if branch == default_branch:
        raise ValidationError("The development branch must differ from the repository's default branch")
    rev_parse(workspace, base_sha)  # raises if the onboarded commit is gone
    if worktree_dir.exists():
        git(["worktree", "remove", "--force", str(worktree_dir)], workspace, check=False)
        if worktree_dir.exists():
            import shutil
            shutil.rmtree(worktree_dir, ignore_errors=True)
    git(["worktree", "prune"], workspace, check=False)
    git(["branch", "-D", branch], workspace, check=False)   # stale branch from an interrupted attempt only
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-b", branch, str(worktree_dir), base_sha], workspace)


def stage_all(worktree: Path) -> None:
    git(["add", "-A"], worktree)


@dataclass
class DiffResult:
    changed_files: list[str]
    additions: int
    deletions: int
    diff_text: str
    truncated: bool


def verified_diff(worktree: Path, *, base: str = "HEAD", max_chars: int = 400_000) -> DiffResult:
    """The truth about what changed: derived from git, never from what an agent claims."""
    stage_all(worktree)
    numstat = git(["diff", "--cached", "--numstat", base], worktree).stdout
    files: list[str] = []
    add = dele = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, d, path = parts
        files.append(path)
        add += int(a) if a.isdigit() else 0
        dele += int(d) if d.isdigit() else 0
    text = git(["diff", "--cached", base], worktree).stdout
    truncated = len(text) > max_chars
    return DiffResult(files, add, dele, text[:max_chars], truncated)


def commit_all(worktree: Path, message: str) -> str:
    settings = get_settings()
    stage_all(worktree)
    if not git(["diff", "--cached", "--name-only"], worktree).stdout.strip():
        raise ValidationError("Nothing to commit: the working tree has no changes")
    git(
        ["-c", f"user.name={settings.DEV_GIT_AUTHOR_NAME}", "-c", f"user.email={settings.DEV_GIT_AUTHOR_EMAIL}",
         "commit", "--no-verify", "-m", message],
        worktree,
    )
    return git(["rev-parse", "HEAD"], worktree).stdout.strip()


def branch_head(workspace: Path, branch: str) -> str | None:
    proc = git(["rev-parse", "--verify", f"refs/heads/{branch}"], workspace, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def push_branch(worktree: Path, remote_url: str, branch: str, *, token: str | None) -> tuple[bool, str]:
    """Push `branch` to `remote_url`. Returns (ok, message); never raises for remote-side failures."""
    settings = get_settings()
    extra: dict[str, str] = {}
    args = ["push", remote_url, f"refs/heads/{branch}:refs/heads/{branch}"]
    if token and remote_url.startswith("https://"):
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        args = ["-c", f"http.extraHeader=Authorization: Basic {basic}", *args]
    try:
        proc = git(args, worktree, timeout=settings.GIT_PUSH_TIMEOUT_SECONDS, check=False, extra_env=extra)
    except subprocess.TimeoutExpired:
        return False, "git push timed out"
    out = _scrub((proc.stderr or "") + (proc.stdout or "")).strip()
    if proc.returncode != 0:
        low = out.lower()
        if "authentication failed" in low or "could not read username" in low or "403" in low:
            out = "push denied: GIT_PROVIDER_TOKEN is missing, invalid or lacks write access. " + out[-600:]
        elif "non-fast-forward" in low or "rejected" in low:
            out = "push rejected: the remote branch already exists with different history (concurrent change or a re-run); not forcing. " + out[-600:]
        elif "could not resolve host" in low or "timed out" in low or "unable to access" in low:
            out = "push failed: the remote could not be reached (network). " + out[-600:]
    return proc.returncode == 0, out[-1500:]


# --------------------------------------------------------------------------
# Provider (GitHub / GitLab) merge-request creation
# --------------------------------------------------------------------------

@dataclass
class RemoteMR:
    url: str
    identifier: str
    provider: str


class ProviderError(Exception):
    pass


def detect_provider(repo_url: str) -> tuple[str | None, str | None, str | None]:
    """(provider, owner/namespace, repo) from a repository URL, or (None, ...) if unsupported."""
    settings = get_settings()
    parsed = urllib.parse.urlparse(repo_url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    scp = re.match(r"^[\w.-]+@([\w.-]+):(.+?)(?:\.git)?$", repo_url)   # git@github.com:owner/repo.git
    if scp:
        host, path = scp.group(1).lower(), scp.group(2)
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None, None, None
    kind = (settings.GIT_PROVIDER_KIND or "auto").lower()
    if kind == "auto":
        kind = "github" if host == "github.com" else "gitlab" if "gitlab" in host else ""
    if kind not in {"github", "gitlab"}:
        return None, None, None
    namespace = "/".join(parts[:-1]) if kind == "gitlab" else parts[-2]
    return kind, namespace, parts[-1]


def _http_json(method: str, url: str, headers: dict, body: dict | None = None, timeout: int = 30):
    """Bounded retry with backoff for network errors, 429 and 5xx (GET/POST are safe here: PR creation is looked up before
    and after, and a duplicate PR is answered with 422 which is resolved to the existing one)."""
    import time
    settings = get_settings()
    attempts = max(1, settings.GIT_API_RETRIES)
    for n in range(1, attempts + 1):
        try:
            status, resp = _http_json_once(method, url, headers, body, timeout)
        except ProviderError:
            if n == attempts:
                raise
        else:
            if status not in (429, 500, 502, 503, 504) or n == attempts:
                return status, resp
        time.sleep(settings.GIT_API_RETRY_BACKOFF_SECONDS * n)


def _http_json_once(method: str, url: str, headers: dict, body: dict | None = None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 - provider URL from server config
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"message": raw[:500]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Could not reach the Git provider API: {getattr(exc, 'reason', exc)}") from exc


def create_remote_mr(provider: str, namespace: str, repo: str, *, token: str, source: str, target: str,
                     title: str, description: str) -> RemoteMR:
    """Create the MR/PR on the provider. Idempotent: an existing open MR for the same branch is returned."""
    settings = get_settings()
    if provider == "github":
        base = settings.GITHUB_API_URL.rstrip("/")
        headers = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}
        status, body = _http_json("POST", f"{base}/repos/{namespace}/{repo}/pulls", headers,
                                  {"title": title, "head": source, "base": target, "body": description})
        if status in (200, 201) and body:
            return RemoteMR(body["html_url"], str(body["number"]), "github")
        if status == 422:   # most commonly "a pull request already exists"
            q = urllib.parse.urlencode({"head": f"{namespace}:{source}", "state": "open"})
            s2, existing = _http_json("GET", f"{base}/repos/{namespace}/{repo}/pulls?{q}", headers)
            if s2 == 200 and existing:
                return RemoteMR(existing[0]["html_url"], str(existing[0]["number"]), "github")
        raise ProviderError(f"GitHub rejected the pull request: {diagnose_http(status, body)}")
    if provider == "gitlab":
        base = settings.GITLAB_API_URL.rstrip("/")
        pid = urllib.parse.quote(f"{namespace}/{repo}", safe="")
        headers = {"PRIVATE-TOKEN": token}
        status, body = _http_json("POST", f"{base}/projects/{pid}/merge_requests", headers,
                                  {"source_branch": source, "target_branch": target, "title": title, "description": description})
        if status in (200, 201) and body:
            return RemoteMR(body["web_url"], str(body["iid"]), "gitlab")
        if status == 409:
            q = urllib.parse.urlencode({"source_branch": source, "state": "opened"})
            s2, existing = _http_json("GET", f"{base}/projects/{pid}/merge_requests?{q}", headers)
            if s2 == 200 and existing:
                return RemoteMR(existing[0]["web_url"], str(existing[0]["iid"]), "gitlab")
        raise ProviderError(f"GitLab rejected the merge request: {diagnose_http(status, body)}")
    raise ProviderError(f"Unsupported provider {provider!r}")


@dataclass
class RemoteMRState:
    merged: bool
    state: str            # provider-reported state (open/closed/merged/opened)
    head_sha: str | None
    merge_commit_sha: str | None


def fetch_remote_mr_state(provider: str, namespace: str, repo: str, identifier: str, *, token: str) -> RemoteMRState:
    """Ask the provider whether the pull/merge request has really been merged. Raises ProviderError if it cannot be determined."""
    settings = get_settings()
    if provider == "github":
        base = settings.GITHUB_API_URL.rstrip("/")
        headers = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}
        status, body = _http_json("GET", f"{base}/repos/{namespace}/{repo}/pulls/{identifier}", headers)
        if status != 200 or not isinstance(body, dict):
            raise ProviderError(f"GitHub returned HTTP {status} when checking pull request #{identifier}: {_scrub(str((body or {}).get('message', body)))[:300]}")
        return RemoteMRState(bool(body.get("merged")) or bool(body.get("merged_at")), str(body.get("state", "")),
                             (body.get("head") or {}).get("sha"), body.get("merge_commit_sha"))
    if provider == "gitlab":
        base = settings.GITLAB_API_URL.rstrip("/")
        pid = urllib.parse.quote(f"{namespace}/{repo}", safe="")
        status, body = _http_json("GET", f"{base}/projects/{pid}/merge_requests/{identifier}", {"PRIVATE-TOKEN": token})
        if status != 200 or not isinstance(body, dict):
            raise ProviderError(f"GitLab returned HTTP {status} when checking merge request !{identifier}: {_scrub(str((body or {}).get('message', body)))[:300]}")
        return RemoteMRState(body.get("state") == "merged", str(body.get("state", "")), body.get("sha"), body.get("merge_commit_sha"))
    raise ProviderError(f"Unsupported provider {provider!r}")
