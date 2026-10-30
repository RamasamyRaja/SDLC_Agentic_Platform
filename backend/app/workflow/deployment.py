"""
DevOps Agent: deploys ONLY an Architect-approved merge request, from the
approved commit, and records real execution evidence for every step.

It is deterministic by design (no LLM decides whether a deployment "worked").
A target is configured by the operator through server settings
(DEPLOY_COMMAND, DEPLOY_HEALTHCHECK_URL); without one, the outcome is an
honest UNAVAILABLE state - an artifact may be prepared, nothing is deployed.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redaction import redact
from app.models.repository import Repository
from app.models.task import Task
from app.models.workflow import Deployment, DeploymentStatus, DevelopmentRun, MergeRequest, MrReviewStatus, RemoteStatus
from app.workflow import gitops


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Steps:
    def __init__(self, dep: Deployment, db: Session):
        self.dep, self.db, self.items = dep, db, []

    def add(self, name: str, status: str, detail: str = "", exit_code: int | None = None, output: str = "") -> dict:
        item = {"name": name, "status": status, "detail": detail, "exit_code": exit_code,
                "output": output[-4000:] if output else "", "at": _now()}
        self.items.append(item)
        self.dep.steps = list(self.items)
        self.db.add(self.dep)
        self.db.commit()
        return item


def eligibility(mr: MergeRequest | None, run: DevelopmentRun | None, repo: Repository) -> tuple[bool, str]:
    if mr is None or run is None:
        return False, "No merge request exists for this task."
    if mr.review_status != MrReviewStatus.APPROVED.value:
        return False, f"The merge request is {mr.review_status}; deployment requires an Architect-approved MR."
    if not mr.commit_sha:
        return False, "The merge request has no recorded commit."
    ws = Path(repo.workspace_path or "")
    if not ws.is_dir():
        return False, "The repository workspace is missing on disk."
    head = gitops.branch_head(ws, mr.source_branch)
    if head != mr.commit_sha:
        return False, f"Branch {mr.source_branch} is at {head or 'nothing'}, not the approved commit {mr.commit_sha[:12]}; the approved changes were altered."
    # A real remote pull request must actually be merged before anything is deployed.
    if mr.remote_status == RemoteStatus.REMOTE_CREATED.value:
        provider, namespace, repo_name = gitops.detect_provider(repo.url)
        token = get_settings().GIT_PROVIDER_TOKEN
        if not (provider and mr.remote_identifier and token):
            return False, "A remote pull request exists but its merge state cannot be verified (provider, PR number or GIT_PROVIDER_TOKEN missing)."
        try:
            state = gitops.fetch_remote_mr_state(provider, namespace, repo_name, mr.remote_identifier, token=token)
        except gitops.ProviderError as exc:
            return False, f"Could not verify the remote pull request merge state: {exc}"
        if not state.merged:
            return False, f"Remote pull request {mr.remote_url or mr.remote_identifier} is {state.state or 'not merged'}; merge it on {provider} before deploying."
        if state.head_sha and state.head_sha != mr.commit_sha:
            return False, f"The merged remote pull request is at {state.head_sha[:12]}, not the approved commit {mr.commit_sha[:12]}."
        return True, "Approved commit matches the branch head and the remote pull request is merged."
    return True, ("Merge request approved and the branch head matches the approved commit. "
                  "No remote pull request exists for it, so remote merge could not be verified.")


def execute(db: Session, *, dep_id, task: Task, repo: Repository, mr: MergeRequest) -> DeploymentStatus:
    """Runs the pipeline; returns the terminal status (also persisted on the row)."""
    settings = get_settings()
    dep = db.get(Deployment, dep_id)
    dep.started_at = datetime.now(timezone.utc)
    steps = _Steps(dep, db)
    log: list[str] = []

    def finish(status: DeploymentStatus, error: str | None = None) -> DeploymentStatus:
        dep.status = status.value
        dep.error = error
        dep.log = "\n".join(log)[-20000:]
        dep.finished_at = datetime.now(timezone.utc)
        db.add(dep); db.commit()
        return status

    ws = Path(repo.workspace_path or "")
    run = db.get(DevelopmentRun, mr.run_id)
    ok, why = eligibility(mr, run, repo)
    steps.add("eligibility-check", "PASSED" if ok else "FAILED", why)
    if not ok:
        return finish(DeploymentStatus.DEPLOYMENT_FAILED, why)

    # --- artifact from the approved commit -------------------------------
    root = Path(settings.WORKSPACE_ROOT).resolve()
    art_dir = root / "_artifacts" / str(task.id)
    art_dir.mkdir(parents=True, exist_ok=True)
    artifact = art_dir / f"{mr.commit_sha}.tar.gz"
    try:
        proc = subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(artifact), mr.commit_sha], cwd=str(ws),
                              capture_output=True, text=True, timeout=300, check=False)
        if proc.returncode != 0 or not artifact.is_file():
            raise RuntimeError((proc.stderr or "git archive failed")[-400:])
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        dep.artifact_path, dep.artifact_sha256, dep.commit_sha = str(artifact), digest, mr.commit_sha
        steps.add("artifact", "PASSED", f"{artifact.name} ({artifact.stat().st_size} bytes, sha256 {digest[:16]}...)")
    except Exception as exc:  # noqa: BLE001
        steps.add("artifact", "FAILED", str(exc))
        return finish(DeploymentStatus.DEPLOYMENT_FAILED, f"Artifact preparation failed: {exc}")

    # --- configuration validation ----------------------------------------
    command = settings.DEPLOY_COMMAND
    if not command:
        steps.add("configuration", "BLOCKED", "No deployment target is configured (DEPLOY_COMMAND is not set).")
        steps.add("deploy", "SKIPPED", "Nothing was deployed.")
        steps.add("health-check", "SKIPPED", "Nothing to check.")
        return finish(DeploymentStatus.UNAVAILABLE,
                      "No deployment target configured. The artifact was prepared from the approved commit, but nothing was deployed.")
    argv = shlex.split(command)
    if not argv or shutil.which(argv[0]) is None and not Path(argv[0]).exists():
        steps.add("configuration", "FAILED", f"Deploy executable not found: {argv[0] if argv else '(empty)'}")
        return finish(DeploymentStatus.DEPLOYMENT_FAILED, "DEPLOY_COMMAND points to an executable that does not exist.")
    steps.add("configuration", "PASSED", f"Deploy command: {argv[0]}")

    # --- release directory + execution -----------------------------------
    release = root / "_deploy" / str(task.id) / mr.commit_sha
    shutil.rmtree(release, ignore_errors=True)
    release.mkdir(parents=True)
    with tarfile.open(artifact) as tar:
        tar.extractall(release, filter="data")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(release), "RAD_TASK_ID": str(task.id),
           "RAD_COMMIT_SHA": mr.commit_sha, "RAD_BRANCH": mr.source_branch, "RAD_ARTIFACT_PATH": str(artifact),
           "RAD_RELEASE_DIR": str(release)}
    try:
        proc = subprocess.run(argv, cwd=str(release), env=env, capture_output=True, text=True,
                              timeout=settings.DEPLOY_TIMEOUT_SECONDS, check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        out = redact(out)
        log.append(out)
        if proc.returncode != 0:
            steps.add("deploy", "FAILED", f"exit code {proc.returncode}", proc.returncode, out)
            return finish(DeploymentStatus.DEPLOYMENT_FAILED, f"Deploy command exited with {proc.returncode}")
        steps.add("deploy", "PASSED", "Deploy command exited 0", 0, out)
    except subprocess.TimeoutExpired:
        steps.add("deploy", "FAILED", f"timed out after {settings.DEPLOY_TIMEOUT_SECONDS}s")
        return finish(DeploymentStatus.DEPLOYMENT_FAILED, "Deploy command timed out")
    except OSError as exc:
        steps.add("deploy", "FAILED", str(exc))
        return finish(DeploymentStatus.DEPLOYMENT_FAILED, f"Deploy command could not start: {exc}")

    # --- verification: four SEPARATE pieces of evidence --------------------------------------------
    evidence: dict = {"command": {"status": "PASSED", "detail": "Deploy command exited 0 (this alone does not prove the target runs the new code)"}}
    dep.evidence = evidence

    def conclude(status: DeploymentStatus, error: str | None = None) -> DeploymentStatus:
        h, v, sm = (evidence.get(k, {}).get("status") for k in ("health", "version", "smoke"))
        if v == "PASSED" and sm == "PASSED":
            level = "FULLY_VERIFIED"
        elif v == "PASSED":
            level = "VERSION_VERIFIED"
        elif sm == "PASSED":
            level = "SMOKE_VERIFIED"
        elif h == "PASSED":
            level = "HEALTH_ONLY"
        else:
            level = "COMMAND_ONLY"
        dep.verification_level = level
        dep.evidence = dict(evidence)
        return finish(status, error)

    url = (settings.DEPLOY_HEALTHCHECK_URL or "").replace("{commit_sha}", mr.commit_sha)
    if url:
        last = ""
        ok_health = False
        for attempt in range(1, settings.DEPLOY_HEALTHCHECK_RETRIES + 1):
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:   # noqa: S310 - operator-configured URL
                    if 200 <= resp.status < 300:
                        dep.health_check = {"status": "PASSED", "url": url, "http_status": resp.status, "attempts": attempt}
                        steps.add("health-check", "PASSED", f"HTTP {resp.status} from {url} (attempt {attempt})")
                        evidence["health"] = {"status": "PASSED", "detail": f"HTTP {resp.status} from the configured health URL", "url": url}
                        ok_health = True
                        break
                    last = f"HTTP {resp.status}"
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last = str(getattr(exc, "reason", exc))
            time.sleep(settings.DEPLOY_HEALTHCHECK_INTERVAL_SECONDS)
        if not ok_health:
            dep.health_check = {"status": "FAILED", "url": url, "detail": last, "attempts": settings.DEPLOY_HEALTHCHECK_RETRIES}
            evidence["health"] = {"status": "FAILED", "detail": last, "url": url}
            steps.add("health-check", "FAILED", f"{last} after {settings.DEPLOY_HEALTHCHECK_RETRIES} attempts")
            return conclude(DeploymentStatus.DEPLOYMENT_FAILED, f"Health check failed: {last}")
    else:
        dep.health_check = {"status": "SKIPPED", "detail": "DEPLOY_HEALTHCHECK_URL is not configured"}
        evidence["health"] = {"status": "SKIPPED", "detail": "DEPLOY_HEALTHCHECK_URL is not configured"}
        steps.add("health-check", "SKIPPED", "No health-check URL configured.")

    if settings.DEPLOY_VERSION_URL:
        vurl = settings.DEPLOY_VERSION_URL.replace("{commit_sha}", mr.commit_sha)
        ok, detail = check_deployed_version(vurl, mr.commit_sha, settings.DEPLOY_VERSION_JSON_KEY)
        evidence["version"] = {"status": "PASSED" if ok else "FAILED", "detail": detail, "url": vurl}
        steps.add("version-check", "PASSED" if ok else "FAILED", detail)
        if not ok:
            return conclude(DeploymentStatus.DEPLOYMENT_FAILED, f"Deployed version check failed: {detail}")
    else:
        evidence["version"] = {"status": "SKIPPED", "detail": "DEPLOY_VERSION_URL is not configured; the deployed commit was not verified"}

    if settings.DEPLOY_SMOKE_COMMAND:
        sargv = shlex.split(settings.DEPLOY_SMOKE_COMMAND)
        try:
            sp = subprocess.run(sargv, cwd=str(release), env=env, capture_output=True, text=True, timeout=settings.DEPLOY_SMOKE_TIMEOUT_SECONDS, check=False)
            sout = redact((sp.stdout or "") + (sp.stderr or ""))
            log.append(sout)
            ok = sp.returncode == 0
            evidence["smoke"] = {"status": "PASSED" if ok else "FAILED", "detail": f"smoke command exited {sp.returncode}", "exit_code": sp.returncode}
            steps.add("smoke-test", "PASSED" if ok else "FAILED", f"exit code {sp.returncode}", sp.returncode, sout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            ok = False
            evidence["smoke"] = {"status": "FAILED", "detail": f"smoke command could not complete: {exc.__class__.__name__}"}
            steps.add("smoke-test", "FAILED", evidence["smoke"]["detail"])
        if not ok:
            return conclude(DeploymentStatus.DEPLOYMENT_FAILED, "Post-deployment smoke test failed")
    else:
        evidence["smoke"] = {"status": "SKIPPED", "detail": "DEPLOY_SMOKE_COMMAND is not configured"}

    passed = {k for k, v in evidence.items() if v.get("status") == "PASSED"} - {"command"}
    if not passed:
        return conclude(DeploymentStatus.UNAVAILABLE,
                        "The deploy command exited 0, but no health check, version check or smoke test is configured, so the deployment could not be verified and is not reported as deployed.")
    if settings.DEPLOY_REQUIRE_VERSION_VERIFICATION and passed == {"health"}:
        return conclude(DeploymentStatus.UNAVAILABLE,
                        "Target health passed, but the deployed version/commit was not verified (DEPLOY_REQUIRE_VERSION_VERIFICATION is on; set DEPLOY_VERSION_URL or DEPLOY_SMOKE_COMMAND).")
    return conclude(DeploymentStatus.DEPLOYED)


def check_deployed_version(url: str, commit: str, json_key: str | None) -> tuple[bool, str]:
    """The TARGET application must report the approved commit (full SHA, or at least its first 7 characters)."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:   # noqa: S310 - operator-configured URL
            body = resp.read(200_000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, f"version endpoint unreachable: {getattr(exc, 'reason', exc)}"
    reported = body
    if json_key:
        try:
            node = json.loads(body)
            for part in json_key.split("."):
                node = node[part]
            reported = str(node)
        except (ValueError, KeyError, TypeError, IndexError):
            return False, f"version endpoint response has no key {json_key!r}"
    reported = reported.strip().lower()
    c = commit.lower()
    for n in (len(c), 12, 7):
        if c[:n] in reported:
            return True, f"target reports commit {c[:n]} (expected {c[:12]})"
    return False, f"target does not report the approved commit {c[:12]}; it reported: {redact(reported[:120])!r}"
