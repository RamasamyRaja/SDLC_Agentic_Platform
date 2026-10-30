"""
QA stage: run the repository's *own* checks against the implemented change and
record exactly what happened.

Principles
* The set of commands is chosen by this module from a fixed table keyed on what
  files the repository contains - it is never taken from model output.
* Every check records name, command, status, exit code, output, failure details,
  runner and timestamps, and whether it is REQUIRED or advisory. A check that never
  ran is never PASSED. A run that executed zero tests is never PASSED.
* Missing tools/dependencies are reported as DEPENDENCY_MISSING (not as a pass,
  and not disguised as a code failure). A runner that is unavailable is BLOCKED.
  A module the *change itself* imports but that does not exist (a local module, or
  a third-party module in an environment whose dependencies were installed) is a
  FAILED check - the code is wrong - not an environment gap.
* Checks run on a COPY of the worktree so they cannot dirty the diff.
* Runners: "docker" (default; per-run isolated volumes, no network for the checks,
  read-only root, unprivileged user, memory/CPU/PID limits, timeout) and "local"
  (explicit opt-in subprocess runner for development/tests only).

Verdict semantics (see `evaluate`)
  PASSED   every REQUIRED check ran and passed (and, if configured, every acceptance
           criterion was verified); nothing required is unresolved.
  PARTIAL  something passed, but required verification is missing or inconclusive
           (dependency missing, runner blocked, zero tests, skipped, expected tests absent).
  FAILED   a REQUIRED check failed or timed out.
  NOT_RUN  nothing executed.
Advisory (optional) checks are reported but never decide the verdict.
"""
from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.core.config import get_settings
from app.core.redaction import redact
from app.models.workflow import CheckStatus, ValidationVerdict

try:  # optional at import time; the docker runner reports BLOCKED if unavailable
    import docker  # type: ignore
except ImportError:  # pragma: no cover
    docker = None

SUMMARY_SCHEMA = 1
MAX_WORKTREE_BYTES = 256 * 1024 * 1024
_UNPRIVILEGED = "65534:65534"


@dataclass
class CheckSpec:
    name: str
    argv: list[str] | None            # None => SKIPPED with `note`
    image: str = "alpine:3.20"
    note: str | None = None
    required: bool = True
    kind: str = "check"               # compile | test | build | lint | typecheck | check
    ecosystem: str | None = None      # python | node | ... (decides which dependency preparation applies)


@dataclass
class CheckResult:
    name: str
    command: str | None
    status: CheckStatus
    exit_code: int | None = None
    output: str = ""
    failure_details: str | None = None
    runner: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    required: bool = True
    kind: str = "check"
    metrics: dict | None = None


@dataclass
class EnvState:
    """What the runner could set up for the checks. `deps` is one of: not_applicable | not_prepared | installed | failed."""
    runner: str = "local"
    deps: str = "not_prepared"
    detail: str = ""

    @property
    def deps_ready(self) -> bool:
        return self.deps == "installed"


_DEFAULT_NPM_TEST = re.compile(r"no test specified", re.I)
# Environment-gap signatures. NOTE: "No module named" / ModuleNotFoundError are handled separately in classify():
# whether they are an environment gap or a defect of the change depends on WHICH module is missing.
_MISSING_PATTERNS = re.compile(
    r"(command not found|not found: |: not found|Cannot find module|"
    r"ENOENT|executable file not found|No such file or directory: '?(?:python|pytest|node|npm|mvn|gradle|go|cargo)|"
    r"is not recognized|Unable to locate|could not find (?:a )?(?:crate|package)|Missing script)", re.I)
_MODULE_MISSING = re.compile(r"No module named ['\"]?([A-Za-z_][\w.]*)['\"]?")
_PYTEST_COUNT = re.compile(r"(\d+)\s+(passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b")
_NO_TESTS_RAN = re.compile(r"\bno tests ran\b|collected 0 items|no tests found|No tests found", re.I)


def _repo_has(root: Path, *globs: str) -> bool:
    return any(next(root.glob(g), None) is not None for g in globs)


_SKIP_DIRS = ("node_modules", ".git", "venv", ".venv", "target", "build", "dist", "__pycache__")


def _has_files(root: Path, suffix: str, limit_dirs=_SKIP_DIRS) -> bool:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in limit_dirs]
        if any(f.endswith(suffix) for f in filenames):
            return True
    return False


def local_module_names(root: Path) -> set[str]:
    """Top-level importable names that exist in the repository itself (packages, modules, src/ layout)."""
    names: set[str] = set()
    for base in (root, root / "src"):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.name.startswith((".", "_")) and child.name != "__init__.py":
                continue
            if child.is_dir():
                names.add(child.name)
            elif child.suffix == ".py":
                names.add(child.stem)
    return names


# ----------------------------- planning the checks -----------------------------

def python_requirement_files(root: Path) -> list[str]:
    found = []
    for name in ("requirements.txt", "requirements-dev.txt", "requirements-test.txt", "requirements_test.txt", "dev-requirements.txt"):
        if (root / name).is_file():
            found.append(name)
    return found


def pyproject_requirements(root: Path) -> list[str]:
    """Declared dependencies from pyproject.toml WITHOUT building the project (no build backend is executed)."""
    pp = root / "pyproject.toml"
    if not pp.is_file():
        return []
    try:
        data = tomllib.loads(pp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    project = data.get("project") or {}
    reqs = list(project.get("dependencies") or [])
    extras = project.get("optional-dependencies") or {}
    for key in ("dev", "test", "tests"):
        reqs += list(extras.get(key) or [])
    return [r for r in reqs if isinstance(r, str) and r.strip()]


def plan_checks(root: Path) -> list[CheckSpec]:
    """Deterministic, repository-driven check plan. Fixed commands only."""
    optional = get_settings().qa_optional_checks
    specs: list[CheckSpec] = []

    def add(name, argv, image, *, kind, ecosystem=None, note=None):
        specs.append(CheckSpec(name, argv, image, note=note, required=name not in optional, kind=kind, ecosystem=ecosystem))

    if _has_files(root, ".py"):
        add("python-compile", ["python", "-m", "compileall", "-q", "."], "python:3.12-slim", kind="compile", ecosystem="python")
        has_tests = (root / "tests").is_dir() or (root / "test").is_dir() or _repo_has(root, "**/test_*.py", "**/*_test.py") \
            or (root / "pytest.ini").exists() or (root / "tox.ini").exists()
        if has_tests:
            add("python-tests", ["python", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"], "python:3.12-slim", kind="test", ecosystem="python")

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = (json.loads(pkg.read_text(encoding="utf-8")) or {}).get("scripts", {}) or {}
        except (OSError, ValueError):
            scripts = {}
        for script in ("lint", "typecheck", "build", "test"):
            body = scripts.get(script)
            if body is None:
                continue
            kind = "test" if script == "test" else script
            if script == "test" and _DEFAULT_NPM_TEST.search(body):
                # Informational: the repository defines no tests. Whether that is acceptable is decided by `evaluate`
                # (a plan that expects tests turns it into a gap) - it is not a "missing check" by itself.
                specs.append(CheckSpec("npm-test", None, note="package.json only has npm's placeholder test script; no tests are defined",
                                       required=False, kind="test", ecosystem="node"))
                continue
            add(f"npm-{script}", ["npm", "run", script, "--silent"], "node:22-bookworm-slim", kind=kind, ecosystem="node")
        if not scripts:
            specs.append(CheckSpec("npm-scripts", None, note="package.json defines no scripts", required=False, kind="check", ecosystem="node"))

    if (root / "pom.xml").is_file():
        add("maven-test", ["mvn", "-B", "-q", "-o", "test"], "maven:3.9-eclipse-temurin-21", kind="test", ecosystem="java")
    elif _repo_has(root, "build.gradle", "build.gradle.kts"):
        add("gradle-test", ["gradle", "--offline", "-q", "test"], "gradle:8-jdk21", kind="test", ecosystem="java")
    elif _has_files(root, ".java"):
        add("java-compile", ["sh", "-c", "mkdir -p /tmp/classes && find . -name '*.java' -print0 | xargs -0 javac -d /tmp/classes"],
            "eclipse-temurin:21-jdk", kind="compile", ecosystem="java")

    if (root / "go.mod").is_file():
        add("go-vet", ["go", "vet", "./..."], "golang:1.23", kind="lint", ecosystem="go")
        add("go-test", ["go", "test", "./..."], "golang:1.23", kind="test", ecosystem="go")
    if (root / "Cargo.toml").is_file():
        add("cargo-test", ["cargo", "test", "--offline", "-q"], "rust:1.82", kind="test", ecosystem="rust")

    if not specs:
        specs.append(CheckSpec("repository-checks", None, required=True, kind="check",
                               note="No recognised build or test configuration (Python, Node, Java, Go, Rust) was found, so no automated check could run."))
    return specs


# ----------------------------- classification -----------------------------

def parse_test_counts(output: str) -> dict | None:
    """Parse a pytest-style summary ('3 passed, 1 skipped in 0.1s'). None when no summary line is present."""
    counts: dict[str, int] = {}
    for n, word in _PYTEST_COUNT.findall(output or ""):
        key = "errors" if word.startswith("error") else word
        counts[key] = counts.get(key, 0) + int(n)   # a line can repeat across -x reruns; the sum is still a lower bound
    if not counts and _NO_TESTS_RAN.search(output or ""):
        return {"passed": 0, "failed": 0, "skipped": 0, "collected": 0}
    if not counts:
        return None
    counts.setdefault("passed", 0)
    counts["collected"] = counts["passed"] + counts.get("failed", 0) + counts.get("errors", 0) + counts.get("skipped", 0)
    return counts


def classify(exit_code: int | None, output: str, *, timed_out: bool = False, kind: str | None = None,
             local_modules: set[str] | None = None, deps_ready: bool = False) -> CheckStatus:
    if timed_out:
        return CheckStatus.TIMED_OUT
    if exit_code == 0:
        if kind == "test":
            counts = parse_test_counts(output)
            # Exit 0 with nothing executed (no tests collected, or everything skipped) verifies nothing.
            if counts is not None and counts.get("passed", 0) == 0:
                return CheckStatus.NO_TESTS
        return CheckStatus.PASSED
    if kind == "test" and exit_code == 5:     # pytest: "no tests were collected"
        return CheckStatus.NO_TESTS
    if kind == "test" and exit_code not in (126, 127):
        counts = parse_test_counts(output)
        if counts is not None and counts.get("collected", 1) == 0:
            return CheckStatus.NO_TESTS
    if exit_code in (126, 127):
        return CheckStatus.DEPENDENCY_MISSING
    m = _MODULE_MISSING.search(output or "")
    if m:
        root_name = m.group(1).split(".")[0]
        if local_modules is not None and root_name in local_modules:
            return CheckStatus.FAILED            # the repository's own module does not import: a defect of the code
        if deps_ready and root_name != "pytest":
            return CheckStatus.FAILED            # dependencies WERE installed, so the code imports something undeclared
        return CheckStatus.DEPENDENCY_MISSING
    if _MISSING_PATTERNS.search(output or ""):
        return CheckStatus.DEPENDENCY_MISSING
    return CheckStatus.FAILED


_UNRESOLVED = {CheckStatus.DEPENDENCY_MISSING, CheckStatus.BLOCKED, CheckStatus.SKIPPED, CheckStatus.NO_TESTS, CheckStatus.UNVERIFIED}
_EXECUTED = {CheckStatus.PASSED, CheckStatus.FAILED, CheckStatus.TIMED_OUT}


def _reason(r: CheckResult) -> str:
    s = r.status
    if s == CheckStatus.DEPENDENCY_MISSING:
        return "a tool or dependency is missing in the runner, so the check could not run (not a verdict on the code)"
    if s == CheckStatus.BLOCKED:
        return (r.failure_details or "the runner was unavailable")[:300]
    if s == CheckStatus.NO_TESTS:
        return "the test command ran but no tests were executed (none collected, or all skipped); this verifies nothing"
    if s == CheckStatus.SKIPPED:
        return (r.failure_details or "the check was not run")[:300]
    if s == CheckStatus.TIMED_OUT:
        return r.failure_details or "the check timed out"
    if s == CheckStatus.FAILED:
        return (r.failure_details or f"exit code {r.exit_code}")[:300]
    if s == CheckStatus.UNVERIFIED:
        return "needs human verification"
    return ""


def evaluate(results: list[CheckResult], *, acceptance: list[str] | None = None, expects_tests: bool = False,
             acceptance_required: bool | None = None, env: EnvState | None = None) -> dict:
    """
    Turn raw check results into the verdict AND the explanation of it. Pure function (no I/O) so every rule is unit-tested.
    Returns a JSON-serialisable dict; see the module docstring for the semantics of each verdict.
    """
    settings = get_settings()
    if acceptance_required is None:
        acceptance_required = settings.QA_ACCEPTANCE_REQUIRED_FOR_PASS
    real = [r for r in results if r.kind != "acceptance"]

    required = [r for r in real if r.required]
    advisory = [r for r in real if not r.required]

    def row(r: CheckResult) -> dict:
        return {"name": r.name, "kind": r.kind, "status": r.status.value, "exit_code": r.exit_code, "reason": _reason(r)}

    executed_required = [r for r in required if r.status in _EXECUTED]
    passed_required = [r for r in required if r.status == CheckStatus.PASSED]
    failed_required = [r for r in required if r.status in (CheckStatus.FAILED, CheckStatus.TIMED_OUT)]
    unresolved_required = [r for r in required if r.status in _UNRESOLVED]
    # A SKIPPED check that is "not applicable" (nothing to run, nothing required) is informational, never a gap.
    not_applicable = [r for r in advisory if r.status == CheckStatus.SKIPPED]
    advisory_other = [r for r in advisory if r.status != CheckStatus.SKIPPED]
    advisory_failed = [r for r in advisory_other if r.status in (CheckStatus.FAILED, CheckStatus.TIMED_OUT)]
    advisory_unavailable = [r for r in advisory_other if r.status in _UNRESOLVED]

    reasons: list[dict] = []
    gap_reasons: list[str] = []
    for r in failed_required:
        reasons.append({**row(r), "effect": "fails the verdict (required check failed)"})
    for r in unresolved_required:
        reasons.append({**row(r), "effect": "keeps the verdict at PARTIAL (required verification is incomplete)"})
        gap_reasons.append(f"required check '{r.name}' is {r.status.value}")

    tests_passed = any(r.kind == "test" and r.status == CheckStatus.PASSED and r.required for r in real)
    expected_tests_gap = bool(expects_tests and not tests_passed)
    if expected_tests_gap:
        msg = "The approved plan expects tests, but no required test check executed tests successfully"
        reasons.append({"name": "plan-expected-tests", "kind": "test", "status": "NOT_VERIFIED", "exit_code": None,
                        "reason": msg, "effect": "keeps the verdict at PARTIAL (mandatory verification is missing)"})
        gap_reasons.append("tests expected by the plan did not run successfully")

    acc_items = [{"criterion": c, "verification": "PENDING_ARCHITECT_REVIEW", "automated": False} for c in (acceptance or [])]
    acceptance_gap = bool(acc_items and acceptance_required)
    if acceptance_gap:
        gap_reasons.append(f"{len(acc_items)} acceptance criteria are not verified by an automated check")
        reasons.append({"name": "acceptance-criteria", "kind": "acceptance", "status": "UNVERIFIED", "exit_code": None,
                        "reason": "acceptance criteria are not verified by any automated check (QA_ACCEPTANCE_REQUIRED_FOR_PASS is on)",
                        "effect": "keeps the verdict at PARTIAL"})

    any_executed = any(r.status in _EXECUTED for r in real)
    if failed_required:
        verdict = ValidationVerdict.FAILED
    elif not any_executed:
        verdict = ValidationVerdict.NOT_RUN
    elif unresolved_required or expected_tests_gap or acceptance_gap:
        verdict = ValidationVerdict.PARTIAL
    elif passed_required:
        verdict = ValidationVerdict.PASSED
    else:
        # only advisory checks executed and nothing was required to run: nothing mandatory was verified
        verdict = ValidationVerdict.PARTIAL
        gap_reasons.append("no required check was executed")

    # ---- human-readable headline
    if verdict == ValidationVerdict.PASSED:
        extra = []
        if advisory_failed:
            extra.append(f"{len(advisory_failed)} advisory check(s) failed: {', '.join(r.name for r in advisory_failed)}")
        if acc_items:
            extra.append(f"{len(acc_items)} acceptance criteria await the Architect's confirmation")
        headline = f"All {len(passed_required)} required check(s) passed" + (f" ({'; '.join(extra)})" if extra else "") + "."
    elif verdict == ValidationVerdict.FAILED:
        headline = "Required check(s) failed: " + ", ".join(f"{r.name} ({r.status.value})" for r in failed_required) + "."
    elif verdict == ValidationVerdict.NOT_RUN:
        headline = "No check was executed" + (": " + "; ".join(f"{r.name} {r.status.value}" for r in real[:4]) if real else ".")
    else:
        headline = (f"{len(passed_required)} of {len(required)} required check(s) passed; verification is incomplete: "
                    + "; ".join(gap_reasons[:4]) + ".")

    return {
        "schema": SUMMARY_SCHEMA,
        "verdict": verdict.value,
        "headline": headline,
        "reasons": reasons,
        "counts": {"required": len(required), "executed": len([r for r in real if r.status in _EXECUTED]),
                   "passed": len(passed_required), "failed": len(failed_required), "unresolved": len(unresolved_required) + (1 if expected_tests_gap else 0),
                   "advisory": len(advisory_other), "advisory_failed": len(advisory_failed)},
        "required": [r.name for r in required],
        "executed": [r.name for r in real if r.status in _EXECUTED],
        "passed": [r.name for r in real if r.status == CheckStatus.PASSED],
        "failed": [row(r) for r in failed_required],
        "unresolved": [row(r) for r in unresolved_required],
        "advisory": [row(r) for r in advisory_other],
        "not_applicable": [{"name": r.name, "reason": r.failure_details or "nothing to run for this repository"} for r in not_applicable],
        "tests_expected_by_plan": bool(expects_tests),
        "acceptance": {"total": len(acc_items), "automated_verified": 0, "pending_architect_review": len(acc_items),
                       "required_for_pass": bool(acceptance_required), "items": acc_items},
        "environment": {"runner": env.runner if env else None, "dependencies": env.deps if env else None, "detail": env.detail if env else None},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def compute_verdict(results: list[CheckResult]) -> ValidationVerdict:
    """Verdict only (kept for callers that do not need the explanation)."""
    return ValidationVerdict(evaluate(results)["verdict"])


def explain_legacy(checks: list, *, verdict: str) -> dict:
    """
    Explanation for a run validated BEFORE checks were classified. It only restates what the stored rows say; it never
    changes the stored verdict. Rows have `required = NULL`, so nothing can be claimed about required-vs-advisory.
    """
    real = [c for c in checks if c.status != "UNVERIFIED" and not str(c.name).startswith("acceptance:")]
    by_status: dict[str, list[str]] = {}
    for c in real:
        by_status.setdefault(c.status, []).append(c.name)
    gaps = {k: v for k, v in by_status.items() if k in ("DEPENDENCY_MISSING", "BLOCKED", "SKIPPED", "NO_TESTS")}
    bits = [f"{k.replace('_', ' ').lower()}: {', '.join(v)}" for k, v in gaps.items()]
    headline = {
        "PASSED": f"{len(by_status.get('PASSED', []))} check(s) passed.",
        "PARTIAL": "Some checks passed but others could not run" + (" (" + "; ".join(bits) + ")" if bits else "") + ".",
        "FAILED": "A check failed: " + ", ".join(by_status.get("FAILED", []) + by_status.get("TIMED_OUT", [])) + ".",
        "NOT_RUN": "No check was executed.",
    }.get(verdict, verdict)
    return {
        "schema": 0, "legacy": True, "verdict": verdict, "headline": headline,
        "note": "Validated before checks were classified as required/advisory. Re-run validation for a precise explanation; the stored verdict is unchanged.",
        "counts": {"executed": len([c for c in real if c.status in ("PASSED", "FAILED", "TIMED_OUT")]), "passed": len(by_status.get("PASSED", [])),
                   "failed": len(by_status.get("FAILED", [])) + len(by_status.get("TIMED_OUT", [])),
                   "unresolved": sum(len(v) for v in gaps.values()), "required": None, "advisory": None, "advisory_failed": None},
        "unresolved": [{"name": n, "status": k, "reason": ""} for k, names in gaps.items() for n in names],
        "failed": [{"name": n, "status": k, "reason": ""} for k in ("FAILED", "TIMED_OUT") for n in by_status.get(k, [])],
        "reasons": [], "required": [], "executed": [], "passed": by_status.get("PASSED", []), "advisory": [], "not_applicable": [],
        "acceptance": {"total": len([c for c in checks if str(c.name).startswith("acceptance:")]), "automated_verified": 0,
                       "pending_architect_review": len([c for c in checks if str(c.name).startswith("acceptance:")]), "required_for_pass": False, "items": []},
        "environment": {"runner": None, "dependencies": None, "detail": None},
    }


def _tail(text: str) -> str:
    limit = get_settings().QA_MAX_OUTPUT_CHARS
    text = redact(text)
    return text if len(text) <= limit else "...[truncated]...\n" + text[-limit:]


# ------------------------------- runners ---------------------------------

def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "node_modules/.cache"), symlinks=True, dirs_exist_ok=True)


def _limits():  # pragma: no cover - runs in the child process
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (get_settings().QA_CHECK_TIMEOUT_SECONDS * 2,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024,) * 2)
    os.setsid()


def _finish(spec: CheckSpec, cmd_text: str | None, code, out: str, timed_out: bool, runner: str, started, *,
            local_modules: set[str] | None, deps_ready: bool) -> CheckResult:
    status = classify(code, out, timed_out=timed_out, kind=spec.kind, local_modules=local_modules, deps_ready=deps_ready)
    metrics = parse_test_counts(out) if spec.kind == "test" else None
    return CheckResult(spec.name, cmd_text, status, code, out,
                       None if status == CheckStatus.PASSED else _failure_details(status, code, out),
                       runner, started, datetime.now(timezone.utc), spec.required, spec.kind, metrics)


def run_local(spec: CheckSpec, worktree: Path) -> CheckResult:
    settings = get_settings()
    started = datetime.now(timezone.utc)
    if settings.ENVIRONMENT == "production" and not settings.QA_ALLOW_LOCAL_RUNNER_IN_PRODUCTION:
        return CheckResult(spec.name, shlex.join(spec.argv or []), CheckStatus.BLOCKED, None, "",
                           "The local QA runner executes repository code on the API host and is refused when ENVIRONMENT=production "
                           "(set QA_RUNNER=docker, or QA_ALLOW_LOCAL_RUNNER_IN_PRODUCTION=true to accept the risk).",
                           "local", started, datetime.now(timezone.utc), spec.required, spec.kind)
    tmp = Path(tempfile.mkdtemp(prefix="rad-qa-"))
    work = tmp / "work"
    try:
        _copy_tree(worktree, work)
        argv = list(spec.argv or [])
        if argv and argv[0] == "python":
            argv[0] = sys.executable
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp), "LANG": "C.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "CI": "1", "NO_COLOR": "1"}
        if argv and argv[0] == sys.executable:
            env["PYTHONPATH"] = str(work)
        
        try:
            run_options = {
                "cwd": str(work),
                "env": env,
                "capture_output": True,
                "text": True,
                "timeout": settings.QA_CHECK_TIMEOUT_SECONDS,
            }

            if os.name != "nt":
                run_options["preexec_fn"] = _limits

            proc = subprocess.run(argv, **run_options)
            out = _tail((proc.stdout or "") + (proc.stderr or ""))
            code, timed_out = proc.returncode, False

        except subprocess.TimeoutExpired as exc:
            out = _tail(((exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")))
            code, timed_out = None, True
        except FileNotFoundError as exc:
            out, code, timed_out = f"executable file not found: {exc.filename}", 127, False
        return _finish(spec, shlex.join(spec.argv or []), code, out, timed_out, "local", started,
                       local_modules=local_module_names(work), deps_ready=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_docker_command(spec: CheckSpec, rel_path: str | None = None, *, src: str = "/src", with_deps: bool = False) -> list[str]:
    """Shell wrapper executed inside the container: copy the read-only source volume to tmpfs, run the fixed command there."""
    prefix = ""
    if with_deps and spec.ecosystem == "python":
        prefix = "PYTHONPATH=/deps/site:/tmp/work "
    elif spec.ecosystem == "python":
        prefix = "PYTHONPATH=/tmp/work "
    source = f"/workspace/{shlex.quote(rel_path)}" if rel_path else src
    return ["sh", "-c", f"mkdir -p /tmp/work && cp -a {source}/. /tmp/work/ && cd /tmp/work && {prefix}{shlex.join(spec.argv or [])}"]


def build_install_argv(requirement_files: list[str], requirements: list[str], extra_args: list[str], *, want_pytest: bool) -> list[str]:
    """pip install into /deps/site, wheels only: no setup.py / build backend of any package is executed."""
    argv = ["pip", "install", "--no-input", "--disable-pip-version-check", "--no-cache-dir", "--only-binary=:all:",
            "--target", "/deps/site", *extra_args]
    for f in requirement_files:
        argv += ["-r", f"/src/{f}"]
    argv += requirements
    if want_pytest:
        argv.append("pytest")
    return argv


class DockerSandbox:
    """
    One validation pass in Docker. Every pass gets its OWN volumes - the source (a copy of just this worktree, so a check can
    never see another repository or task) and, if needed, the installed dependencies - and removes them afterwards.

        src volume  --ro--> every container            (worktree copy, no .git, no node_modules)
        deps volume --rw--> install container only     (network ON, no secrets, wheel-only, unprivileged, read-only root)
        deps volume --ro--> check containers           (network OFF)
    """

    def __init__(self, worktree: Path, specs: list[CheckSpec], client=None):
        self.settings = get_settings()
        self.worktree = worktree
        self.specs = specs
        self.client = client
        self.tag = uuid.uuid4().hex[:12]
        self.src_volume = f"rad-qa-src-{self.tag}"
        self.deps_volume = f"rad-qa-deps-{self.tag}"
        self.volumes: list[str] = []
        self.env = EnvState(runner="docker", deps="not_applicable")
        self.blocked_reason: str | None = None
        self._local_modules = local_module_names(worktree)

    # ---- helpers
    def _user(self) -> str:
        return self.settings.SANDBOX_USER or _UNPRIVILEGED

    def _uid_gid(self) -> tuple[int, int]:
        try:
            u, g = (self._user().split(":") + ["65534"])[:2]
            return int(u), int(g)
        except ValueError:
            return 65534, 65534

    def _ensure_image(self, image: str) -> None:
        try:
            self.client.images.get(image)
        except Exception:  # noqa: BLE001 - ImageNotFound or a transient error: try pulling
            self.client.images.pull(image)

    def _tar_worktree(self) -> bytes:
        uid, gid = self._uid_gid()
        buf = io.BytesIO()
        total = 0
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for dirpath, dirnames, filenames in os.walk(self.worktree):
                dirnames[:] = [d for d in dirnames if d not in skip]
                rel_dir = Path(dirpath).relative_to(self.worktree)
                for name in list(dirnames) + filenames:
                    p = Path(dirpath) / name
                    if p.is_symlink():
                        continue     # never copy a link into the sandbox: it could point at a host path
                    rel = (rel_dir / name).as_posix()
                    info = tar.gettarinfo(str(p), arcname=rel)
                    info.uid, info.gid, info.uname, info.gname = uid, gid, "", ""
                    if p.is_dir():
                        info.mode = 0o755
                        tar.addfile(info)
                        continue
                    total += info.size
                    if total > MAX_WORKTREE_BYTES:
                        raise ValueError(f"the worktree is larger than {MAX_WORKTREE_BYTES // (1024 * 1024)} MB; refusing to copy it into the sandbox")
                    with open(p, "rb") as fh:
                        tar.addfile(info, fh)
        return buf.getvalue()

    def _dir_tar(self, name: str) -> bytes:
        uid, gid = self._uid_gid()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name)
            info.type, info.mode, info.uid, info.gid = tarfile.DIRTYPE, 0o755, uid, gid
            tar.addfile(info)
        return buf.getvalue()

    def _seed(self, volume: str, bind: str, tar_bytes: bytes) -> None:
        """Write an archive into a volume through a stopped helper container (no host path is ever bind-mounted)."""
        helper = self.client.containers.create(
            image="alpine:3.20", command=["true"], volumes={volume: {"bind": bind, "mode": "rw"}},
            network_disabled=True, labels={"com.rad.ai-agent": "qa-seed"})
        try:
            helper.put_archive(bind, tar_bytes)
        finally:
            try:
                helper.remove(force=True)
            except Exception:  # noqa: BLE001
                pass

    # ---- lifecycle
    
    def _prepare_dependencies(self) -> None:
        s = self.settings
        py = next(
            (sp for sp in self.specs if sp.ecosystem == "python" and sp.argv),
            None,
        )
        if py is None:
            return

        if not s.QA_DEPENDENCY_INSTALL:
            self.env = EnvState(
                "docker",
                "not_prepared",
                "QA_DEPENDENCY_INSTALL is false: pytest and the repository's dependencies are not installed",
            )
            return

        req_files = python_requirement_files(self.worktree)
        reqs = pyproject_requirements(self.worktree)
        want_pytest = any(
            sp.kind == "test" and sp.ecosystem == "python" and sp.argv
            for sp in self.specs
        )
        argv = build_install_argv(
            req_files,
            reqs,
            shlex.split(s.QA_PIP_EXTRA_ARGS or ""),
            want_pytest=want_pytest,
        )

        container = None
        try:
            self.client.volumes.create(
                name=self.deps_volume,
                labels={"com.rad.ai-agent": "qa"},
            )
            self.volumes.append(self.deps_volume)
            self._seed(
                self.deps_volume,
                "/deps",
                self._dir_tar("site"),
            )
            self._ensure_image(py.image)

            container = self.client.containers.run(
                image=py.image,
                command=argv,
                detach=True,
                user=self._user(),
                working_dir="/tmp",
                volumes={
                    self.src_volume: {"bind": "/src", "mode": "ro"},
                    self.deps_volume: {"bind": "/deps", "mode": "rw"},
                },
                environment={"HOME": "/tmp", "PIP_NO_INPUT": "1"},
                mem_limit=s.SANDBOX_MEMORY,
                nano_cpus=int(s.SANDBOX_CPUS * 1e9),
                pids_limit=s.SANDBOX_PIDS_LIMIT,
                read_only=True,
                tmpfs=self._tmpfs(),
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
                labels={"com.rad.ai-agent": "qa-install"},
            )

            code, out, timed_out = self._wait(
                container,
                s.QA_INSTALL_TIMEOUT_SECONDS,
            )

            print(
                "QA INSTALL DIAGNOSTIC:",
                {
                    "exit_code": code,
                    "timed_out": timed_out,
                    "output": out[-4000:],
                },
                flush=True,
            )

            if timed_out:
                self.env = EnvState(
                    "docker",
                    "failed",
                    f"dependency installation timed out after {s.QA_INSTALL_TIMEOUT_SECONDS}s",
                )
            elif code == 0:
                self.env = EnvState(
                    "docker",
                    "installed",
                    "pip install (wheels only) of the declared requirements"
                    + (" + pytest" if want_pytest else "")
                    + " succeeded",
                )
            else:
                lines = [line for line in out.strip().splitlines() if line.strip()]
                self.env = EnvState(
                    "docker",
                    "failed",
                    f"dependency installation failed (exit code {code}): "
                    + " | ".join(lines[-12:])[:2000],
                )

        except Exception as exc:
            self.env = EnvState(
                "docker",
                "failed",
                "dependency preparation could not run: "
                + redact(str(exc))[:300],
            )
        finally:
            self._remove(container)


    def _tmpfs(self) -> dict:
        uid, gid = self._uid_gid()
        return {"/tmp": f"rw,nosuid,nodev,size=768m,mode=1777,uid={uid},gid={gid}"}

    def _wait(self, container, timeout: int) -> tuple[int | None, str, bool]:
        deadline = time.monotonic() + timeout
        timed_out = False
        while True:
            container.reload()
            if container.status in {"exited", "dead"}:
                break
            if time.monotonic() >= deadline:
                container.kill()
                timed_out = True
                break
            time.sleep(0.25)
        code = None if timed_out else int(container.wait(timeout=10).get("StatusCode", 1))
        out = _tail(container.logs(stdout=True, stderr=True).decode("utf-8", "replace"))
        return code, out, timed_out

    @staticmethod
    def _remove(container) -> None:
        try:
            if container:
                container.remove(force=True)
        except Exception:  # noqa: BLE001
            pass

    def run(self, spec: CheckSpec) -> CheckResult:
        started = datetime.now(timezone.utc)
        cmd_text = shlex.join(spec.argv or [])
        s = self.settings

        def blocked(reason: str) -> CheckResult:
            return CheckResult(spec.name, cmd_text, CheckStatus.BLOCKED, None, "", f"Docker sandbox unavailable: {reason}",
                               "docker", started, datetime.now(timezone.utc), spec.required, spec.kind)

        if self.blocked_reason:
            return blocked(self.blocked_reason)
        with_deps = spec.ecosystem == "python" and self.env.deps == "installed"
        if spec.ecosystem == "python" and self.env.deps in ("not_prepared", "failed") and spec.kind == "test":
            # pytest itself is absent: say precisely why instead of letting the container fail with an opaque import error
            return CheckResult(spec.name, cmd_text, CheckStatus.DEPENDENCY_MISSING, None, "",
                               "The test runner and dependencies are not installed in the sandbox: " + self.env.detail,
                               "docker", started, datetime.now(timezone.utc), spec.required, spec.kind)
        container = None
        try:
            self._ensure_image(spec.image)
            volumes = {self.src_volume: {"bind": "/src", "mode": "ro"}}
            if with_deps:
                volumes[self.deps_volume] = {"bind": "/deps", "mode": "ro"}
            container = self.client.containers.run(
                image=spec.image, command=build_docker_command(spec, with_deps=with_deps), detach=True, user=self._user(),
                volumes=volumes, working_dir="/tmp", environment={"HOME": "/tmp", "CI": "1", "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                network_disabled=True, mem_limit=s.SANDBOX_MEMORY, nano_cpus=int(s.SANDBOX_CPUS * 1e9), pids_limit=s.SANDBOX_PIDS_LIMIT,
                read_only=True, tmpfs=self._tmpfs(), security_opt=["no-new-privileges"], cap_drop=["ALL"], labels={"com.rad.ai-agent": "qa"})
            code, out, timed_out = self._wait(container, s.QA_CHECK_TIMEOUT_SECONDS)
            return _finish(spec, cmd_text, code, out, timed_out, "docker", started, local_modules=self._local_modules, deps_ready=with_deps)
        except Exception as exc:  # noqa: BLE001
            return blocked(redact(str(exc))[:300])
        finally:
            self._remove(container)

    def close(self) -> None:
        for name in reversed(self.volumes):
            try:
                self.client.volumes.get(name).remove(force=True)
            except Exception:  # noqa: BLE001
                pass
        try:
            if self.client is not None and hasattr(self.client, "close"):
                self.client.close()
        except Exception:  # noqa: BLE001
            pass


def run_docker(spec: CheckSpec, worktree: Path) -> CheckResult:
    """Single-check convenience wrapper (prepares and tears down its own sandbox)."""
    sandbox = DockerSandbox(worktree, [spec])
    try:
        sandbox.prepare()
        return sandbox.run(spec)
    finally:
        sandbox.close()


def _failure_details(status: CheckStatus, code: int | None, output: str) -> str:
    if status == CheckStatus.TIMED_OUT:
        return f"Timed out after {get_settings().QA_CHECK_TIMEOUT_SECONDS}s"
    if status == CheckStatus.DEPENDENCY_MISSING:
        return "The command could not run because a tool or dependency is missing in the runner (this is not a verdict on the code): " + output.strip()[-400:]
    if status == CheckStatus.NO_TESTS:
        return "No tests were executed" + (f" (exit code {code})" if code else "") + ": " + " | ".join([l for l in (output or "").strip().splitlines() if l.strip()][-3:])[:400]
    lines = [l for l in (output or "").strip().splitlines() if l.strip()]
    return f"exit code {code}: " + " | ".join(lines[-6:])[:800]


def run_checks(worktree: Path, specs: list[CheckSpec] | None = None, *,
               on_result: Callable[[CheckResult], None] | None = None, env_out: EnvState | None = None) -> list[CheckResult]:
    """
    Run every planned check. `on_result` is called as each check finishes so callers can persist progress immediately
    (a crash then loses at most the check that was running). `env_out`, if given, is filled with what the runner could prepare.
    """
    settings = get_settings()
    specs = specs if specs is not None else plan_checks(worktree)
    runner = (settings.QA_RUNNER or "docker").lower()
    results: list[CheckResult] = []

    def emit(r: CheckResult) -> None:
        results.append(r)
        if on_result:
            on_result(r)

    sandbox = None
    try:
        if runner == "docker" and any(sp.argv for sp in specs):
            sandbox = DockerSandbox(worktree, specs)
            sandbox.prepare()
            if env_out is not None:
                env_out.runner, env_out.deps, env_out.detail = sandbox.env.runner, sandbox.env.deps, sandbox.env.detail
        elif env_out is not None:
            env_out.runner, env_out.deps = runner, "not_prepared"
            env_out.detail = ("local runner: uses the API host's own Python environment; no dependency preparation" if runner == "local" else "")
        for spec in specs:
            now = datetime.now(timezone.utc)
            if spec.argv is None:
                emit(CheckResult(spec.name, None, CheckStatus.SKIPPED, None, "", spec.note, None, now, now, spec.required, spec.kind))
            elif runner == "local":
                emit(run_local(spec, worktree))
            elif runner == "docker":
                emit(sandbox.run(spec))
            else:
                emit(CheckResult(spec.name, shlex.join(spec.argv), CheckStatus.BLOCKED, None, "", f"Unknown QA_RUNNER {runner!r}", runner, now, now,
                                 spec.required, spec.kind))
    finally:
        if sandbox is not None:
            sandbox.close()
    return results
