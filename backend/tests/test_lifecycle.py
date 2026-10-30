"""
End-to-end tests of the RAD task lifecycle through the real HTTP API, a real PostgreSQL database,
real git repositories/worktrees, the real QA runner (local runner, explicitly enabled), and a scripted
LLM (FakeLLMProvider - no real model is called by the suite).

Covers: RBAC matrix, plan grounding, both approval gates, isolated implementation, git-verified diffs,
validation verdicts (pass + deliberate fail), commit/MR (local remote + fake GitHub API), architect review,
deployment (blocked / unavailable / success / controlled failure) and the report.
"""
import http.server
import json
import os
import stat
import subprocess
import threading
import uuid
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.security import hash_password
from app.llm.fake_provider import FakeLLMProvider
from app.models.user import User, UserRole
from app.workflow import lifecycle

CALC = "def add(a, b):\n    return a + b\n"
TEST_CALC = "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_origin(tmp_path: Path, name="origin", branch="main") -> Path:
    origin = tmp_path / name
    (origin / "tests").mkdir(parents=True)
    (origin / "calc.py").write_text(CALC)
    (origin / "tests" / "test_calc.py").write_text(TEST_CALC)
    (origin / "README.md").write_text("# demo\n")
    _git(origin, "init", "-b", branch)
    _git(origin, "config", "user.email", "t@t.io")
    _git(origin, "config", "user.name", "T")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "init")
    return origin


def plan_json(*, files=None, quote="def add(a, b):", extra_findings=None) -> str:
    files = files or [
        {"file_path": "calc.py", "action": "modify", "change_description": "add subtract()", "symbols": ["add"], "expected_behavior": "subtract(5,3)==2"},
        {"file_path": "tests/test_calc.py", "action": "modify", "change_description": "test subtract", "symbols": [], "expected_behavior": "test passes"},
    ]
    return json.dumps({
        "summary": "Add a subtract function next to add().", "requirement_understanding": "Client needs subtraction.",
        "current_implementation": "calc.py defines add(a, b) only.",
        "findings": [{"statement": "calc.py already defines add", "evidence": [{"file_path": "calc.py", "quote": quote}]}] + (extra_findings or []),
        "recommended_approach": "Add subtract(a, b) beside add().", "rationale": "Smallest change consistent with the module.",
        "alternatives_rejected": ["New module: unnecessary"], "files_to_change": files,
        "implementation_steps": [{"step": 1, "description": "Add subtract", "files": ["calc.py"]}],
        "risks": ["Name clash"], "dependencies": [], "acceptance_criteria": ["subtract(5, 3) returns 2"],
        "test_strategy": {"approach": "pytest", "test_cases": [{"name": "test_subtract", "description": "5-3==2", "file_path": "tests/test_calc.py"}], "validation_notes": []},
        "uncertainties": [], "confidence": 0.85,
    })


def edit_json(*, calc_new="def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
              test_new=None, extra_edits=None, empty=False) -> str:
    if empty:
        return json.dumps({"edits": [], "new_files": [], "notes": ["nothing safe to change"]})
    test_new = test_new or (TEST_CALC + "\n\ndef test_subtract():\n    from calc import subtract\n    assert subtract(5, 3) == 2\n")
    edits = [
        {"file_path": "calc.py", "old_content": CALC, "new_content": calc_new, "rationale": "add subtract"},
        {"file_path": "tests/test_calc.py", "old_content": TEST_CALC, "new_content": test_new, "rationale": "test it"},
    ] + (extra_edits or [])
    return json.dumps({"edits": edits, "new_files": [], "notes": []})


@pytest.fixture(scope="module", autouse=True)
def local_qa_runner():
    s = get_settings()
    saved = (s.QA_RUNNER, s.DEPLOY_COMMAND, s.DEPLOY_HEALTHCHECK_URL, s.GIT_PROVIDER_TOKEN, s.GIT_PROVIDER_KIND, s.GITHUB_API_URL)
    s.QA_RUNNER = "local"
    yield s
    (s.QA_RUNNER, s.DEPLOY_COMMAND, s.DEPLOY_HEALTHCHECK_URL, s.GIT_PROVIDER_TOKEN, s.GIT_PROVIDER_KIND, s.GITHUB_API_URL) = saved


@pytest.fixture(scope="module")
def users(client):
    from app.db.session import SessionLocal
    db = SessionLocal()
    out = {}
    tag = uuid.uuid4().hex[:6]
    for role in UserRole:
        email = f"{role.value.lower()}-{tag}@lifecycle.test"
        db.add(User(email=email, full_name=role.value, password_hash=hash_password("Passw0rd!x"), role=role))
        out[role.value] = email
    db.commit()
    db.close()
    headers = {}
    for role, email in out.items():
        r = client.post("/api/auth/login", json={"email": email, "password": "Passw0rd!x"})
        assert r.status_code == 200, r.text
        headers[role] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return headers


@pytest.fixture(scope="module")
def env(client, users, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("lifecycle")
    origin = make_origin(tmp)
    dev = users["DEVELOPER"]
    repo = client.post("/api/repositories", json={"url": f"file://{origin}"}, headers=dev).json()
    onboard_response = client.post(
    	f"/api/repositories/{repo['id']}/onboard",
    	json={},
    	headers=dev,
    )
    assert onboard_response.status_code == 201, onboard_response.text
    assert client.post(f"/api/repositories/{repo['id']}/index", headers=dev).status_code == 201
    yield {"origin": origin, "repo": repo, "tmp": tmp}
    from app.db.session import SessionLocal
    from app.models.repository import Repository
    from app.retrieval.embeddings import get_embedding_provider
    from app.retrieval.milvus_client import MilvusVectorStore
    from app.services import workspace_service
    MilvusVectorStore(dimension=get_embedding_provider().dimension).delete_by_repository(repo["id"])
    db = SessionLocal(); db.query(Repository).filter(Repository.id == repo["id"]).delete(); db.commit(); db.close()
    workspace_service.remove_workspace(uuid.UUID(repo["id"]))


@pytest.fixture()
def provider(monkeypatch):
    """Install a scripted provider; tests push responses in the order the agents will consume them."""
    fake = FakeLLMProvider(responses=[], model="scripted")
    monkeypatch.setattr(lifecycle, "PROVIDER_FACTORY", lambda: fake)
    return fake


def new_task(client, env, users, title="Add subtract", role="DEVELOPER"):
    r = client.post("/api/tasks", json={"repository_id": env["repo"]["id"], "title": title, "request": "Add a subtract(a, b) function",
                                        "expected_outcome": "subtract(5,3) == 2"}, headers=users[role])
    assert r.status_code == 201, r.text
    return r.json()["task_id"]


def get(client, users, tid, role="DEVELOPER"):
    r = client.get(f"/api/tasks/{tid}", headers=users[role])
    assert r.status_code == 200, r.text
    return r.json()


def post(client, users, tid, path, role, body=None):
    return client.post(f"/api/tasks/{tid}/{path}", json=body or {}, headers=users[role])


def planned_task(client, env, users, provider):
    provider._responses.append(plan_json())
    tid = new_task(client, env, users)
    assert get(client, users, tid)["workflow_stage"] == "PLAN_PENDING_APPROVAL"
    return tid


def approved_task(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    assert post(client, users, tid, "plan/decision", "ARCHITECT", {"decision": "APPROVED"}).status_code == 200
    return tid


def implemented_task(client, env, users, provider, edits=None):
    tid = approved_task(client, env, users, provider)
    provider._responses.append(edits or edit_json())
    r = post(client, users, tid, "implementation", "DEVELOPER")
    assert r.status_code == 202, r.text
    return tid


# ------------------------------------------------------------------ A. RBAC
def test_task_creation_permissions(client, env, users, provider):
    body = {"repository_id": env["repo"]["id"], "request": "Add a subtract function"}
    for role, expected in [("DEVELOPER", 201), ("ADMIN", 201), ("ARCHITECT", 403), ("VIEWER", 403)]:
        provider._responses.append(plan_json())
        assert client.post("/api/tasks", json=body, headers=users[role]).status_code == expected, role
    assert client.post("/api/tasks", json=body).status_code in (201, 403)  # dev-fallback identity is ADMIN in tests


def test_me_exposes_server_permissions(client, users):
    perms = {r: set(client.get("/api/auth/me", headers=users[r]).json()["permissions"]) for r in users}
    assert {"plan:approve", "plan:reject", "mr:approve", "mr:reject"} <= perms["ARCHITECT"]
    assert not perms["ARCHITECT"] & {"task:create", "mr:create"}
    for r in ("ADMIN", "DEVELOPER"):
        assert {"task:create", "mr:create"} <= perms[r]
        assert not perms[r] & {"plan:approve", "plan:reject", "mr:approve", "mr:reject"}
    assert all(p.endswith(":read") for p in perms["VIEWER"])


def test_only_architect_can_decide_plan(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    for role in ("ADMIN", "DEVELOPER", "VIEWER"):
        assert post(client, users, tid, "plan/decision", role, {"decision": "APPROVED"}).status_code == 403, role
        assert post(client, users, tid, "plan/decision", role, {"decision": "REJECTED", "comment": "no"}).status_code == 403, role
    assert get(client, users, tid)["workflow_stage"] == "PLAN_PENDING_APPROVAL"


# ------------------------------------------------------------------ C. planning
def test_plan_is_grounded_and_persisted(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    plan = client.get(f"/api/tasks/{tid}/plan", headers=users["ARCHITECT"]).json()
    assert plan["status"] == "PENDING_APPROVAL" and plan["version"] == 1
    assert plan["plan"]["findings"][0]["evidence"][0]["verified"] is True
    assert [f["file_path"] for f in plan["plan"]["files_to_change"]] == ["calc.py", "tests/test_calc.py"]
    assert all(f["exists"] for f in plan["plan"]["files_to_change"])
    ev = plan["evidence"]
    assert ev["verification"]["verified_quotes"] == 1 and any(f["path"] == "calc.py" and len(f["sha256"]) == 64 for f in ev["files_read"])
    detail = get(client, users, tid)
    assert detail["plan_status"] == "PENDING_APPROVAL" and detail["repository"]["default_branch"] == "main"
    # the Architect agent's own prompt contained the real source, not just a summary
    assert "def add(a, b):" in provider.requests[-1].user_prompt


def test_hallucinated_plan_is_rejected_not_accepted(client, env, users, provider):
    bad = plan_json(files=[{"file_path": "does/not/exist.py", "action": "modify", "change_description": "modify it"}])
    provider._responses += [bad] * 3
    tid = new_task(client, env, users)
    d = get(client, users, tid)
    assert d["workflow_stage"] == "PLAN_FAILED"
    plan = client.get(f"/api/tasks/{tid}/plan", headers=users["DEVELOPER"]).json()
    assert plan["status"] == "FAILED" and "does not exist" in plan["error"]
    assert {a["key"] for a in d["allowed_actions"]} == {"start_planning"}
    assert len(provider.requests) == 3  # bounded rounds, each fed the verification errors


def test_unverifiable_quote_is_fed_back_then_fails(client, env, users, provider):
    provider._responses += [plan_json(quote="this text is nowhere in calc.py")] * 3
    tid = new_task(client, env, users)
    assert get(client, users, tid)["workflow_stage"] == "PLAN_FAILED"
    assert "quote not found" in client.get(f"/api/tasks/{tid}/plan", headers=users["DEVELOPER"]).json()["error"]


def test_plan_revision_loop_and_rejection_comment_required(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    assert post(client, users, tid, "plan/decision", "ARCHITECT", {"decision": "REJECTED"}).status_code == 400
    assert post(client, users, tid, "plan/decision", "ARCHITECT", {"decision": "REVISION_REQUESTED", "comment": "also cover negatives"}).status_code == 200
    assert get(client, users, tid)["workflow_stage"] == "PLAN_REVISION_REQUIRED"
    # implementation must not be startable from here
    assert post(client, users, tid, "implementation", "DEVELOPER").status_code == 409
    provider._responses.append(plan_json())
    assert post(client, users, tid, "plan", "DEVELOPER").status_code == 202
    plans = client.get(f"/api/tasks/{tid}/plans", headers=users["ARCHITECT"]).json()
    assert [p["version"] for p in plans] == [2, 1] and plans[1]["status"] == "REVISION_REQUIRED"
    assert plans[0]["feedback"] == "also cover negatives"
    assert "also cover negatives" in provider.requests[-1].user_prompt
    assert get(client, users, tid)["workflow_stage"] == "PLAN_PENDING_APPROVAL"


# ------------------------------------------------------------------ D. approval gate
def test_implementation_blocked_before_plan_approval(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    for role in ("DEVELOPER", "ADMIN"):
        r = post(client, users, tid, "implementation", role)
        assert r.status_code == 409, r.text
    # no development run, no worktree, source untouched
    assert client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json() == []
    assert not (Path(get_settings().WORKSPACE_ROOT) / "_dev" / tid).exists()
    # and the direct service call is refused as well (defence in depth)
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        from app.core.exceptions import WorkflowStateError
        dev_user = db.query(User).filter(User.role == UserRole.DEVELOPER).first()
        with pytest.raises(WorkflowStateError):
            lifecycle.start_implementation(db, user=dev_user, task_id=uuid.UUID(tid))
    finally:
        db.close()
    # a stale stage cannot be forced via the legacy status endpoint either
    client.patch(f"/api/tasks/{tid}/status", json={"status": "QUEUED"}, headers=users["ADMIN"])
    assert post(client, users, tid, "implementation", "DEVELOPER").status_code == 409


def test_modify_file_tool_and_direct_run_are_closed(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    r = client.post(f"/api/tasks/{tid}/tools/modify_file", headers=users["ADMIN"],
                    json={"input": {"file_path": "calc.py", "old_content": CALC, "new_content": "x"}})
    assert r.status_code in (403, 404, 409)
    r = client.post(f"/api/tasks/{tid}/run", json={"execute_changes": True}, headers=users["ADMIN"])
    assert r.status_code == 409


# ------------------------------------------------------------------ E. real implementation
def test_real_implementation_isolated_verified_diff_and_passing_tests(client, env, users, provider):
    ws = Path(client.get(f"/api/repositories/{env['repo']['id']}", headers=users["DEVELOPER"]).json()["workspace_path"])
    head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ws, capture_output=True, text=True).stdout.strip()
    tid = implemented_task(client, env, users, provider)
    d = get(client, users, tid)
    assert d["workflow_stage"] == "READY_FOR_MR", d["lifecycle"]
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    run = client.get(f"/api/tasks/{tid}/development-runs/{run['id']}", headers=users["DEVELOPER"]).json()
    assert run["status"] == "CHANGES_APPLIED" and sorted(run["changed_files"]) == ["calc.py", "tests/test_calc.py"]
    assert "+def subtract(a, b):" in run["diff"] and "README.md" not in run["diff"]
    assert run["branch_name"].startswith("rad/task-") and run["branch_name"] != "main"
    # the onboarded checkout and its default branch were never touched
    assert (ws / "calc.py").read_text() == CALC
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=ws, capture_output=True, text=True).stdout.strip() == head_before
    assert subprocess.run(["git", "status", "--porcelain"], cwd=ws, capture_output=True, text=True).stdout.strip() == ""
    # the worktree really contains the change
    assert "def subtract" in (Path(get_settings().WORKSPACE_ROOT) / "_dev" / tid / "a1" / "calc.py").read_text()
    checks = {c["name"]: c for c in run["checks"]}
    assert checks["python-compile"]["status"] == "PASSED" and checks["python-compile"]["exit_code"] == 0 and checks["python-compile"]["command"]
    assert checks["python-tests"]["status"] == "PASSED" and "passed" in checks["python-tests"]["output"], checks["python-tests"]
    assert checks["python-tests"]["started_at"] and checks["python-tests"]["runner"] == "local"
    assert run["validation_verdict"] == "PASSED"
    assert any(c["status"] == "UNVERIFIED" for c in client.get(f"/api/tasks/{tid}/development-runs/{run['id']}", headers=users["DEVELOPER"]).json()["checks"])


def test_out_of_scope_edit_is_rejected_and_not_applied(client, env, users, provider):
    readme = {"file_path": "README.md", "old_content": "# demo\n", "new_content": "# hacked\n", "rationale": "oops"}
    tid = implemented_task(client, env, users, provider, edits=edit_json(extra_edits=[readme]))
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    rej = [e for e in run["edits"] if e["status"] == "REJECTED"]
    assert [e["file_path"] for e in rej] == ["README.md"] and "scope" in rej[0]["reason"]
    assert "README.md" not in run["changed_files"]


def test_protected_and_traversal_paths_refused(tmp_path):
    from app.tools.exceptions import PathSecurityError
    from app.workflow import fileops
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "link").symlink_to(tmp_path / "a.txt")
    for bad in (".env", "sub/.env.production", "../escape.txt", "/etc/passwd", ".git/config", "node_modules/x.js", "keys/id_rsa", "cert.pem"):
        with pytest.raises(PathSecurityError):
            fileops.read_text(tmp_path, bad)
    with pytest.raises(PathSecurityError):
        fileops.replace_once(tmp_path, "link", "x", "y")
    assert (tmp_path / "a.txt").read_text() == "x"


def test_no_change_is_an_implementation_failure_not_success(client, env, users, provider):
    tid = implemented_task(client, env, users, provider, edits=edit_json(empty=True))
    d = get(client, users, tid)
    assert d["workflow_stage"] == "IMPLEMENTATION_FAILED"
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    assert run["status"] == "NO_CHANGES" and run["changed_files"] == [] and "no verified source change" in run["error"]
    impl = next(s for s in d["lifecycle"] if s["key"] == "implementation")
    assert impl["status"] == "FAILED"
    rep = client.get(f"/api/tasks/{tid}/report", headers=users["ARCHITECT"]).json()
    assert rep["implementation_completed"] is False and rep["verified"]["git_diff"] in (None, "")


# ------------------------------------------------------------------ F. validation
def test_failing_test_cannot_pass_validation(client, env, users, provider):
    broken = edit_json(calc_new="def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a + b\n")  # wrong on purpose
    tid = implemented_task(client, env, users, provider, edits=broken)
    d = get(client, users, tid)
    assert d["workflow_stage"] == "VALIDATION_FAILED" and d["validation_verdict"] == "FAILED"
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    failed = next(c for c in run["checks"] if c["name"] == "python-tests")
    assert failed["status"] == "FAILED" and failed["exit_code"] != 0 and "assert" in failed["output"]
    testing = next(s for s in d["lifecycle"] if s["key"] == "testing")
    assert testing["status"] == "FAILED"
    # an MR needs an explicit, recorded acknowledgement
    assert post(client, users, tid, "merge-request", "DEVELOPER").status_code == 409
    action = next(a for a in d["allowed_actions"] if a["key"] == "create_merge_request")
    assert action["requires_acknowledgement"] is True


def test_qa_classification_and_verdicts(tmp_path):
    from app.models.workflow import CheckStatus as C, ValidationVerdict as V
    from app.workflow import qa
    R = lambda s: qa.CheckResult("x", "cmd", s)
    assert qa.classify(0, "") == C.PASSED and qa.classify(1, "boom") == C.FAILED
    assert qa.classify(1, "ModuleNotFoundError: No module named 'pytest'") == C.DEPENDENCY_MISSING
    assert qa.classify(127, "") == C.DEPENDENCY_MISSING and qa.classify(None, "", timed_out=True) == C.TIMED_OUT
    assert qa.compute_verdict([R(C.PASSED), R(C.PASSED)]) == V.PASSED
    assert qa.compute_verdict([R(C.PASSED), R(C.FAILED)]) == V.FAILED
    assert qa.compute_verdict([R(C.PASSED), R(C.DEPENDENCY_MISSING)]) == V.PARTIAL
    assert qa.compute_verdict([R(C.SKIPPED)]) == V.NOT_RUN
    assert qa.compute_verdict([R(C.BLOCKED), R(C.DEPENDENCY_MISSING)]) == V.NOT_RUN   # nothing executed is never a pass
    assert qa.compute_verdict([]) == V.NOT_RUN
    specs = qa.plan_checks(tmp_path)
    assert len(specs) == 1 and specs[0].argv is None   # no recognised config -> SKIPPED, not PASSED
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": 'echo "Error: no test specified" && exit 1', "build": "tsc"}}))
    names = {s.name: s for s in qa.plan_checks(tmp_path)}
    assert names["npm-test"].argv is None and names["npm-build"].argv == ["npm", "run", "build", "--silent"]


def test_docker_runner_reports_blocked_when_unavailable(tmp_path, monkeypatch):
    """Without a reachable Docker daemon a check must be BLOCKED, never PASSED."""
    from app.workflow import qa
    s = get_settings()
    root = Path(s.WORKSPACE_ROOT) / "_dev" / "unit"
    root.mkdir(parents=True, exist_ok=True)
    (root / "x.py").write_text("print(1)\n")
    monkeypatch.setattr(s, "QA_RUNNER", "docker")
    monkeypatch.setattr(s, "SANDBOX_ENABLED", True)
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    results = qa.run_checks(root)
    assert results and all(r.status.value in ("BLOCKED",) for r in results if r.command)
    assert "Docker sandbox unavailable" in (results[0].failure_details or "")
    assert "mkdir -p /tmp/work" in qa.build_docker_command(qa.CheckSpec("t", ["python", "-m", "pytest"]), "_dev/unit")[2]


def test_revalidation_endpoint_records_a_new_batch(client, env, users, provider):
    tid = implemented_task(client, env, users, provider)
    assert post(client, users, tid, "validation", "VIEWER").status_code == 403
    assert post(client, users, tid, "validation", "DEVELOPER").status_code == 202
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    assert run["check_batches"] == 2 and run["validation_verdict"] == "PASSED"


# ------------------------------------------------------------------ G. commit + MR + review
def test_commit_local_mr_and_architect_review(client, env, users, provider):
    tid = implemented_task(client, env, users, provider)
    assert post(client, users, tid, "merge-request", "ARCHITECT").status_code == 403
    assert post(client, users, tid, "merge-request", "VIEWER").status_code == 403
    r = post(client, users, tid, "merge-request", "DEVELOPER", {"title": "Add subtract", "description": "please review"})
    assert r.status_code == 201, r.text
    mr = r.json()
    assert mr["status"] == "OPEN" and mr["review_status"] == "MR_PENDING_REVIEW" and len(mr["commit_sha"]) == 40
    # honest remote status: a file:// remote has no GitHub/GitLab API, so no remote MR exists
    assert mr["remote_status"] == "REMOTE_UNAVAILABLE" and mr["remote_url"] is None and "no remote merge request" in mr["remote_error"].lower()
    assert mr["pushed"] is True
    branches = subprocess.run(["git", "branch", "--list", mr["source_branch"]], cwd=env["origin"], capture_output=True, text=True).stdout
    assert mr["source_branch"] in branches                                       # pushed to the (local) remote
    log = subprocess.run(["git", "log", "--format=%H %s", mr["source_branch"]], cwd=env["origin"], capture_output=True, text=True).stdout.splitlines()
    assert log[0].startswith(mr["commit_sha"]) and log[0].endswith("Add subtract") and len(log) == 2
    assert "+def subtract" in mr["run"]["diff"] and mr["run"]["checks"]
    # retry cannot create a second commit/MR
    assert post(client, users, tid, "merge-request", "DEVELOPER").status_code == 409
    assert len(subprocess.run(["git", "log", "--oneline", mr["source_branch"]], cwd=env["origin"], capture_output=True, text=True).stdout.splitlines()) == 2
    # plan approval is not MR approval: only the architect can review, nobody else
    for role in ("ADMIN", "DEVELOPER", "VIEWER"):
        assert post(client, users, tid, "merge-request/decision", role, {"decision": "APPROVED"}).status_code == 403
        assert post(client, users, tid, "merge-request/decision", role, {"decision": "REJECTED", "comment": "x"}).status_code == 403
    assert get(client, users, tid)["workflow_stage"] == "MR_PENDING_REVIEW"
    assert post(client, users, tid, "merge-request/decision", "ARCHITECT", {"decision": "REJECTED"}).status_code == 400  # comment needed
    ok = post(client, users, tid, "merge-request/decision", "ARCHITECT", {"decision": "APPROVED", "comment": "lgtm", "mr_id": mr["id"]})
    assert ok.status_code == 200 and ok.json()["review_status"] == "MR_APPROVED"
    assert client.get(f"/api/tasks/{tid}/merge-request", headers=users["VIEWER"]).json()["review_status"] == "MR_APPROVED"  # persisted
    rep = client.get(f"/api/tasks/{tid}/report", headers=users["VIEWER"]).json()
    decisions = [(d["subject"], d["decision"], d["by_role"]) for d in rep["verified"]["architect_decisions"]]
    assert ("MR", "APPROVED", "ARCHITECT") in decisions
    assert rep["verified"]["commit"]["sha"] == mr["commit_sha"] and rep["implementation_completed"] is True
    assert any("No remote merge request" in x for x in rep["unresolved_issues"])


def test_mr_rejection_returns_to_implementation_with_feedback(client, env, users, provider):
    tid = implemented_task(client, env, users, provider)
    assert post(client, users, tid, "merge-request", "DEVELOPER").status_code == 201
    assert post(client, users, tid, "merge-request/decision", "ARCHITECT", {"decision": "REJECTED", "comment": "use better naming"}).status_code == 200
    d = get(client, users, tid)
    assert d["workflow_stage"] == "MR_REJECTED" and d["mr_review_status"] == "MR_REJECTED"
    assert {a["key"] for a in d["allowed_actions"]} == {"start_implementation"}
    provider._responses.append(edit_json(calc_new="def add(a, b):\n    return a + b\n\n\ndef minus(a, b):\n    return a - b\n",
                                         test_new=TEST_CALC + "\n\ndef test_minus():\n    from calc import minus\n    assert minus(5, 3) == 2\n"))
    assert post(client, users, tid, "implementation", "DEVELOPER").status_code == 202
    assert "use better naming" in provider.requests[-1].user_prompt
    runs = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()
    assert [r["attempt"] for r in runs] == [2, 1] and runs[0]["branch_name"] != runs[1]["branch_name"]
    assert get(client, users, tid)["workflow_stage"] == "READY_FOR_MR"


def test_mr_with_acknowledged_failed_validation_is_flagged(client, env, users, provider):
    broken = edit_json(calc_new="def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a + b\n")
    tid = implemented_task(client, env, users, provider, edits=broken)
    r = post(client, users, tid, "merge-request", "DEVELOPER", {"acknowledge_validation_risk": True})
    assert r.status_code == 201
    mr = r.json()
    assert mr["validation_verdict"] == "FAILED" and mr["failed_validation_acknowledged"] is True


class _FakeGitHub(http.server.BaseHTTPRequestHandler):
    calls: list = []
    mode = "ok"

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeGitHub.calls.append((self.path, self.headers.get("Authorization"), body))
        if _FakeGitHub.mode == "ok":
            code, payload = 201, {"html_url": "https://github.example/o/r/pull/7", "number": 7}
        else:
            code, payload = 403, {"message": "Resource not accessible by personal access token"}
        out = json.dumps(payload).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture()
def fake_github(local_qa_runner, monkeypatch):
    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeGitHub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _FakeGitHub.calls, _FakeGitHub.mode = [], "ok"
    s = get_settings()
    monkeypatch.setattr(s, "GIT_PROVIDER_KIND", "github")
    monkeypatch.setattr(s, "GITHUB_API_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(s, "GIT_PROVIDER_TOKEN", "ghp_SECRETTOKEN123")
    yield _FakeGitHub
    server.shutdown()


def test_remote_pr_creation_against_fake_github_api(client, env, users, provider, fake_github):
    # NOTE: exercises our provider client against a local fake GitHub API + a real local git remote; real GitHub is not contacted.
    tid = implemented_task(client, env, users, provider)
    r = post(client, users, tid, "merge-request", "DEVELOPER")
    assert r.status_code == 201, r.text
    mr = r.json()
    assert mr["remote_status"] == "REMOTE_CREATED" and mr["remote_url"] == "https://github.example/o/r/pull/7" and mr["remote_identifier"] == "7"
    path, auth, body = fake_github.calls[0]
    assert path.endswith("/pulls") and auth == "Bearer ghp_SECRETTOKEN123"
    assert body["head"] == mr["source_branch"] and body["base"] == "main" and "subtract" in body["body"] and "Validation: PASSED" in body["body"]
    assert "ghp_SECRETTOKEN123" not in json.dumps(mr) and "ghp_SECRETTOKEN123" not in json.dumps(client.get(f"/api/tasks/{tid}/events", headers=users["VIEWER"]).json())


def test_remote_failure_is_reported_precisely_and_local_work_preserved(client, env, users, provider, fake_github):
    fake_github.mode = "deny"
    tid = implemented_task(client, env, users, provider)
    mr = post(client, users, tid, "merge-request", "DEVELOPER").json()
    assert mr["remote_status"] == "REMOTE_FAILED" and "403" in mr["remote_error"] and mr["remote_url"] is None
    assert mr["status"] == "OPEN" and mr["commit_sha"]    # the commit exists locally; nothing is pretended
    assert "ghp_SECRETTOKEN123" not in json.dumps(mr)


def test_no_token_means_no_remote_mr(client, env, users, provider, fake_github, monkeypatch):
    monkeypatch.setattr(get_settings(), "GIT_PROVIDER_TOKEN", None)
    tid = implemented_task(client, env, users, provider)
    mr = post(client, users, tid, "merge-request", "DEVELOPER").json()
    assert mr["remote_status"] == "REMOTE_UNAVAILABLE" and "GIT_PROVIDER_TOKEN" in mr["remote_error"] and not fake_github.calls


# ------------------------------------------------------------------ H. deployment
def _approved_mr_task(client, env, users, provider):
    tid = implemented_task(client, env, users, provider)
    assert post(client, users, tid, "merge-request", "DEVELOPER").status_code == 201
    assert post(client, users, tid, "merge-request/decision", "ARCHITECT", {"decision": "APPROVED"}).status_code == 200
    return tid


def test_deployment_blocked_until_mr_approved(client, env, users, provider):
    tid = implemented_task(client, env, users, provider)
    assert get(client, users, tid)["deployment_status"] == "BLOCKED_PENDING_APPROVAL"
    r = post(client, users, tid, "deployment", "DEVELOPER")
    assert r.status_code == 409 and "blocked" in r.json()["detail"].lower()
    assert post(client, users, tid, "merge-request", "DEVELOPER").status_code == 201
    assert post(client, users, tid, "deployment", "DEVELOPER").status_code == 409    # open but not approved
    dep = client.get(f"/api/tasks/{tid}/deployment", headers=users["VIEWER"]).json()
    assert dep["status"] == "BLOCKED_PENDING_APPROVAL"
    deploy_stage = next(s for s in get(client, users, tid)["lifecycle"] if s["key"] == "deployment")
    assert deploy_stage["status"] == "BLOCKED" and deploy_stage["blockers"]


def test_deployment_unavailable_when_no_target_configured(client, env, users, provider):
    s = get_settings(); s.DEPLOY_COMMAND = None
    tid = _approved_mr_task(client, env, users, provider)
    assert post(client, users, tid, "deployment", "VIEWER").status_code == 403
    assert post(client, users, tid, "deployment", "ARCHITECT").status_code == 403
    assert post(client, users, tid, "deployment", "DEVELOPER").status_code == 202
    d = get(client, users, tid)
    assert d["workflow_stage"] == "DEPLOYMENT_UNAVAILABLE"
    dep = client.get(f"/api/tasks/{tid}/deployment", headers=users["VIEWER"]).json()
    assert dep["status"] == "UNAVAILABLE" and "nothing was deployed" in dep["error"].lower()
    names = {st["name"]: st["status"] for st in dep["steps"]}
    assert names["artifact"] == "PASSED" and names["deploy"] == "SKIPPED" and "DEPLOYED" not in json.dumps(d["workflow_stage"])
    assert Path(dep["artifact_path"]).is_file() and len(dep["artifact_sha256"]) == 64


def _script(tmp_path, name, body):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


class _Health(http.server.BaseHTTPRequestHandler):
    code = 200
    def do_GET(self):
        self.send_response(_Health.code); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a):
        pass


def test_deployment_success_failure_and_retry_with_health_check(client, env, users, provider, tmp_path):
    s = get_settings()
    server = http.server.HTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    marker = tmp_path / "deployed.txt"
    s.DEPLOY_HEALTHCHECK_URL = f"http://127.0.0.1:{server.server_port}/health"
    s.DEPLOY_HEALTHCHECK_RETRIES, s.DEPLOY_HEALTHCHECK_INTERVAL_SECONDS = 2, 0.05
    try:
        tid = _approved_mr_task(client, env, users, provider)
        # 1) controlled failure: deploy command exits non-zero
        s.DEPLOY_COMMAND = _script(tmp_path, "bad.sh", "echo boom >&2\nexit 3\n")
        assert post(client, users, tid, "deployment", "ADMIN").status_code == 202
        dep = client.get(f"/api/tasks/{tid}/deployment", headers=users["VIEWER"]).json()
        assert get(client, users, tid)["workflow_stage"] == "DEPLOYMENT_FAILED" and dep["status"] == "DEPLOYMENT_FAILED"
        failed = next(st for st in dep["steps"] if st["name"] == "deploy")
        assert failed["status"] == "FAILED" and failed["exit_code"] == 3 and "boom" in failed["output"]
        # 2) health check failing is a failure even though the command succeeded
        s.DEPLOY_COMMAND = _script(tmp_path, "ok.sh", f'echo "$RAD_COMMIT_SHA" > {marker}\ntest -f calc.py\n')
        _Health.code = 503
        assert post(client, users, tid, "deployment", "DEVELOPER").status_code == 202
        dep = client.get(f"/api/tasks/{tid}/deployment", headers=users["VIEWER"]).json()
        assert dep["status"] == "DEPLOYMENT_FAILED" and dep["health_check"]["status"] == "FAILED" and dep["attempt"] == 2
        # 3) success with real evidence
        _Health.code = 200
        assert post(client, users, tid, "deployment", "DEVELOPER").status_code == 202
        dep = client.get(f"/api/tasks/{tid}/deployment", headers=users["VIEWER"]).json()
        mr = client.get(f"/api/tasks/{tid}/merge-request", headers=users["VIEWER"]).json()
        assert dep["status"] == "DEPLOYED" and dep["attempt"] == 3 and dep["health_check"]["status"] == "PASSED"
        assert marker.read_text().strip() == mr["commit_sha"]       # the command really ran against the approved commit
        assert all(st["status"] == "PASSED" for st in dep["steps"])
        # no duplicate deployment once deployed
        assert post(client, users, tid, "deployment", "DEVELOPER").status_code == 409
        rep = client.get(f"/api/tasks/{tid}/report", headers=users["ARCHITECT"]).json()
        assert [d["status"] for d in rep["verified"]["deployments"]] == ["DEPLOYMENT_FAILED", "DEPLOYMENT_FAILED", "DEPLOYED"]
    finally:
        server.shutdown()
        s.DEPLOY_COMMAND = None; s.DEPLOY_HEALTHCHECK_URL = None


def test_deploy_without_health_check_is_not_reported_deployed(client, env, users, provider, tmp_path):
    s = get_settings()
    s.DEPLOY_COMMAND = _script(tmp_path, "ok2.sh", "exit 0\n"); s.DEPLOY_HEALTHCHECK_URL = None
    try:
        tid = _approved_mr_task(client, env, users, provider)
        assert post(client, users, tid, "deployment", "DEVELOPER").status_code == 202
        dep = client.get(f"/api/tasks/{tid}/deployment", headers=users["VIEWER"]).json()
        assert dep["status"] != "DEPLOYED" and dep["health_check"]["status"] == "SKIPPED"
        assert get(client, users, tid)["workflow_stage"] != "DEPLOYED"
    finally:
        s.DEPLOY_COMMAND = None


def test_eligibility_requires_remote_pr_merged(monkeypatch):
    from types import SimpleNamespace as NS
    from app.workflow import deployment as dm, gitops
    s = get_settings(); monkeypatch.setattr(s, "GIT_PROVIDER_TOKEN", "t")
    ws = Path(__file__).parent
    from app.models.workflow import MrReviewStatus
    mr = NS(review_status=MrReviewStatus.APPROVED.value, commit_sha="a" * 40, source_branch="b", remote_status="REMOTE_CREATED",
            remote_identifier="7", remote_url="https://github.com/o/r/pull/7")
    repo = NS(workspace_path=str(ws), url="https://github.com/o/r")
    monkeypatch.setattr(gitops, "branch_head", lambda *_: "a" * 40)
    st = lambda merged, sha="a" * 40: gitops.RemoteMRState(merged, "closed" if merged else "open", sha, None)
    monkeypatch.setattr(gitops, "fetch_remote_mr_state", lambda *a, **k: st(False))
    ok, why = dm.eligibility(mr, NS(), repo); assert not ok and "merge it" in why
    monkeypatch.setattr(gitops, "fetch_remote_mr_state", lambda *a, **k: st(True, "c" * 40))
    ok, why = dm.eligibility(mr, NS(), repo); assert not ok and "not the approved commit" in why
    monkeypatch.setattr(gitops, "fetch_remote_mr_state", lambda *a, **k: st(True))
    assert dm.eligibility(mr, NS(), repo)[0]
    def boom(*a, **k): raise gitops.ProviderError("down")
    monkeypatch.setattr(gitops, "fetch_remote_mr_state", boom)
    ok, why = dm.eligibility(mr, NS(), repo); assert not ok and "Could not verify" in why


def test_approved_commit_tampering_blocks_deployment(client, env, users, provider):
    tid = _approved_mr_task(client, env, users, provider)
    wt = Path(get_settings().WORKSPACE_ROOT) / "_dev" / tid / "a1"
    (wt / "calc.py").write_text(CALC + "# sneaky\n")
    _git(wt, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-am", "tamper")
    r = post(client, users, tid, "deployment", "DEVELOPER")
    assert r.status_code == 409 and "altered" in r.json()["detail"]


# ------------------------------------------------------------------ I/J. views
def test_allowed_actions_and_lifecycle_per_role(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    keys = {r: {a["key"] for a in get(client, users, tid, r)["allowed_actions"]} for r in users}
    assert keys["ARCHITECT"] == {"approve_plan", "reject_plan", "request_plan_revision"}
    assert keys["DEVELOPER"] == keys["VIEWER"] == set() and keys["ADMIN"] == set()
    d = get(client, users, tid, "ARCHITECT")
    assert [s["key"] for s in d["lifecycle"]] == ["requirement", "architecture_plan", "plan_approval", "implementation", "testing", "merge_request", "architect_review", "deployment"]
    st = {s["key"]: s["status"] for s in d["lifecycle"]}
    assert st["architecture_plan"] == "COMPLETED" and st["plan_approval"] == "PENDING_HUMAN" and st["implementation"] == "BLOCKED" and st["deployment"] == "BLOCKED"
    assert d["creator"]["email"].startswith("developer-") and d["repository"]["name"]


def test_planning_only_task_is_not_reported_as_implemented(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    rep = client.get(f"/api/tasks/{tid}/report", headers=users["VIEWER"]).json()
    assert rep["implementation_completed"] is False and rep["verified"]["files_modified"] == []
    assert "No implementation has run yet" in rep["unavailable"]
    listing = next(r for r in client.get("/api/reports", headers=users["VIEWER"]).json() if r["taskId"] == tid)
    assert listing["status"] == "running" and "Implementation completed: no" in listing["finalOutcome"]


def test_events_history_records_actor_and_transitions(client, env, users, provider):
    tid = approved_task(client, env, users, provider)
    ev = client.get(f"/api/tasks/{tid}/events", headers=users["VIEWER"]).json()
    seq = [(e["from_stage"], e["to_stage"]) for e in ev if e["from_stage"]]
    assert seq == [("CREATED", "PLANNING"), ("PLANNING", "PLAN_PENDING_APPROVAL"), ("PLAN_PENDING_APPROVAL", "PLAN_APPROVED")]
    assert ev[-1]["actor"].startswith("architect-") and all(e["created_at"] for e in ev)


def test_tasks_visible_team_wide_and_unindexed_repo_blocks_planning(client, env, users, provider):
    tid = planned_task(client, env, users, provider)
    assert tid in {t["id"] for t in client.get("/api/tasks", headers=users["ARCHITECT"]).json()}
    assert env["repo"]["id"] in {r["id"] for r in client.get("/api/repositories", headers=users["ARCHITECT"]).json()}
    fresh = client.post("/api/repositories", json={"url": f"file://{make_origin(env['tmp'], 'fresh')}"}, headers=users["DEVELOPER"]).json()
    r = client.post("/api/tasks", json={"repository_id": fresh["id"], "request": "Add subtract"}, headers=users["DEVELOPER"])
    assert r.status_code == 201 and r.json()["planning_started"] is False and "onboard" in r.json()["planning_blocker"]
    detail = get(client, users, r.json()["task_id"])
    assert detail["workflow_stage"] == "CREATED" and not any(a["key"] == "start_planning" for a in detail["allowed_actions"])
    assert post(client, users, r.json()["task_id"], "plan", "DEVELOPER").status_code == 409


# ------------------------------------------------------------------ L. state machine
def test_state_machine_has_no_path_to_implementation_without_approval():
    from app.models.workflow import WorkflowStage as S
    from app.workflow.state import TRANSITIONS
    approved_reachable, frontier = set(), {S.PLAN_APPROVED}
    # stages reachable from CREATED without passing through PLAN_APPROVED
    seen, stack = set(), [S.CREATED]
    while stack:
        cur = stack.pop()
        if cur in seen or cur == S.PLAN_APPROVED:
            continue
        seen.add(cur)
        stack += list(TRANSITIONS[cur])
    assert S.IMPLEMENTING not in seen and S.DEPLOYING not in seen and S.MR_APPROVED not in seen
    assert S.MR_APPROVED in TRANSITIONS[S.MR_PENDING_REVIEW] and S.DEPLOYING not in TRANSITIONS[S.MR_PENDING_REVIEW]


def test_transition_is_compare_and_set(client, env, users, provider):
    from app.core.exceptions import WorkflowStateError
    from app.db.session import SessionLocal
    from app.models.workflow import WorkflowStage as S
    from app.workflow.state import transition
    tid = planned_task(client, env, users, provider)
    a, b = SessionLocal(), SessionLocal()
    try:
        transition(a, uuid.UUID(tid), expect=S.PLAN_PENDING_APPROVAL, to=S.PLAN_APPROVED, actor="t", event_type="x")
        with pytest.raises(WorkflowStateError):
            transition(b, uuid.UUID(tid), expect=S.PLAN_PENDING_APPROVAL, to=S.PLAN_REJECTED, actor="t", event_type="x")
        with pytest.raises(WorkflowStateError):
            transition(b, uuid.UUID(tid), expect=S.PLAN_APPROVED, to=S.DEPLOYED, actor="t", event_type="x")
    finally:
        a.close(); b.close()


def test_stale_worker_is_recovered(client, env, users, provider):
    from datetime import datetime, timedelta, timezone
    from app.db.session import SessionLocal
    from app.models.task import Task
    from app.workflow.state import recover_stale
    tid = planned_task(client, env, users, provider)
    db = SessionLocal()
    try:
        db.query(Task).filter(Task.id == uuid.UUID(tid)).update({"workflow_stage": "PLANNING", "updated_at": datetime.now(timezone.utc) - timedelta(hours=3)})
        db.commit()
        assert recover_stale(db, uuid.UUID(tid), max_age_seconds=60).workflow_stage == "PLAN_FAILED"
    finally:
        db.close()


# ------------------------------------------------------------------ G. explainable validation / dashboard summary / recovery
def test_validation_summary_is_persisted_and_explains_failure(client, env, users, provider):
    broken = edit_json(calc_new="def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a + b\n")
    tid = implemented_task(client, env, users, provider, edits=broken)
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    s = run["validation_summary"]
    assert s["verdict"] == "FAILED" and s["headline"] and s["reasons"]
    assert "python-tests" in [c["name"] for c in s["failed"]] or any("python-tests" in str(x) for x in s["failed"])
    assert all("required" in c for c in run["checks"])
    d = get(client, users, tid)


def test_passing_task_has_passed_summary_and_dashboard_counts(client, env, users, provider):
    tid = implemented_task(client, env, users, provider)
    run = client.get(f"/api/tasks/{tid}/development-runs", headers=users["DEVELOPER"]).json()[0]
    assert run["validation_summary"]["verdict"] in ("PASSED", "PARTIAL")
    summ = client.get("/api/tasks/summary", headers=users["DEVELOPER"])
    assert summ.status_code == 200, summ.text
    body = summ.json()
    assert body["total"] >= 1 and isinstance(body["needs_attention"], list)
    assert sum(body["validation"].values()) <= body["total"]


def test_partial_validation_requires_acknowledgement(client, env, users, provider):
    from app.db.session import SessionLocal
    from app.models.workflow import DevelopmentRun, ValidationVerdict
    tid = implemented_task(client, env, users, provider)
    db = SessionLocal()
    run = db.query(DevelopmentRun).filter(DevelopmentRun.task_id == tid).order_by(DevelopmentRun.attempt.desc()).first()
    run.validation_verdict = ValidationVerdict.PARTIAL
    db.commit(); db.close()
    assert post(client, users, tid, "merge-request", "DEVELOPER").status_code == 409
    r = post(client, users, tid, "merge-request", "DEVELOPER", {"acknowledge_validation_risk": True})
    assert r.status_code == 201 and r.json()["validation_verdict"] == "PARTIAL"


def test_stale_validating_task_is_recovered_not_stuck(client, env, users, provider):
    from datetime import datetime, timedelta, timezone
    from app.db.session import SessionLocal
    from app.models.task import Task
    from app.workflow import lifecycle
    tid = implemented_task(client, env, users, provider)
    db = SessionLocal()
    t = db.get(Task, tid)
    t.workflow_stage = "VALIDATING"
    t.updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    lifecycle.recover_all_stale(db)
    db.refresh(t)
    assert str(getattr(t.workflow_stage, "value", t.workflow_stage)) != "VALIDATING"
    db.close()
