import time, uuid
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.models.sandbox_run import SandboxRun, SandboxRunStatus
from app.models.user import User
from app.services.repository_service import get_repository
try: import docker
except ImportError: docker=None
ALLOWED={"auto","compile","test","lint","build"}
def _plan(root:Path, command:str):
    has_py=any(root.rglob("*.py")); has_js=(root/"package.json").exists(); has_java=any(root.rglob("*.java"))
    if command=="auto": command="compile" if has_py or has_java else ("build" if has_js else "compile")
    if has_py:
        if command=="test": return "python:3.12-slim","python -m pytest -q",{"language":"python","requires_dependencies":True}
        return "python:3.12-slim","python -m compileall -q .",{"language":"python","mode":command}
    if has_js:
        if command=="test": return "node:22-bookworm-slim","npm test -- --runInBand",{"language":"javascript","requires_dependencies":True}
        if command=="lint": return "node:22-bookworm-slim","npm run lint --if-present",{"language":"javascript"}
        if command=="build": return "node:22-bookworm-slim","npm run build --if-present",{"language":"javascript"}
        return "node:22-bookworm-slim","node --version",{"language":"javascript","mode":"environment-check"}
    if has_java: return "eclipse-temurin:21-jdk","find . -name '*.java' -print0 | xargs -0 javac -d /tmp/classes",{"language":"java"}
    return "alpine:3.20","find . -maxdepth 2 -type f | head -100",{"language":"unknown"}
def run_sandbox(db:Session,*,user:User,task_id:uuid.UUID,repository_id:uuid.UUID,command:str)->SandboxRun:
    settings=get_settings()
    if command not in ALLOWED: raise ValidationError(f"Unsupported sandbox command: {command}")
    repo=get_repository(db,user=user,repository_id=repository_id)
    if not repo.workspace_path or not Path(repo.workspace_path).exists(): raise ValidationError("Repository must be onboarded before sandbox execution")
    row=SandboxRun(id=uuid.uuid4(),task_id=task_id,repository_id=repository_id,command=command,status=SandboxRunStatus.QUEUED); db.add(row); db.commit(); db.refresh(row)
    if not settings.SANDBOX_ENABLED: row.status=SandboxRunStatus.BLOCKED; row.stderr="Sandbox execution is disabled"; db.commit(); return row
    if docker is None: row.status=SandboxRunStatus.BLOCKED; row.stderr="Docker SDK is unavailable"; db.commit(); return row
    client=container=None; started=time.monotonic()
    try:
        client=docker.from_env(); image,shell,meta=_plan(Path(repo.workspace_path),command); row.status=SandboxRunStatus.RUNNING; db.commit()
        container=client.containers.run(image=image,command=["sh","-lc",shell],detach=True,volumes={settings.SANDBOX_WORKSPACE_VOLUME:{"bind":"/workspace","mode":"ro"}},working_dir=f"/workspace/{repository_id}",network_disabled=True,mem_limit=settings.SANDBOX_MEMORY,nano_cpus=int(settings.SANDBOX_CPUS*1e9),pids_limit=settings.SANDBOX_PIDS_LIMIT,read_only=True,tmpfs={"/tmp":"rw,nosuid,nodev,size=256m"},labels={"com.rad.ai-agent":"sandbox","rad.task_id":str(task_id)})
        deadline=time.monotonic()+settings.SANDBOX_TIMEOUT_SECONDS
        timed=False
        while True:
            container.reload()
            if container.status in {"exited","dead"}: break
            if time.monotonic()>=deadline: container.kill(); timed=True; break
            time.sleep(.25)
        result=container.wait(timeout=10) if container.status!="running" else {"StatusCode":124}; code=int(result.get("StatusCode",124))
        out=container.logs(stdout=True,stderr=False).decode("utf-8","replace")[-settings.SANDBOX_MAX_OUTPUT_CHARS:]; err=container.logs(stdout=False,stderr=True).decode("utf-8","replace")[-settings.SANDBOX_MAX_OUTPUT_CHARS:]
        row.status=SandboxRunStatus.TIMED_OUT if timed else (SandboxRunStatus.PASSED if code==0 else SandboxRunStatus.FAILED); row.exit_code=code; row.stdout=out; row.stderr=err; row.duration_ms=int((time.monotonic()-started)*1000); row.metadata_json=meta; db.commit(); db.refresh(row); return row
    except Exception as exc:
        row.status=SandboxRunStatus.BLOCKED; row.stderr=str(exc)[:settings.SANDBOX_MAX_OUTPUT_CHARS]; row.duration_ms=int((time.monotonic()-started)*1000); db.commit(); return row
    finally:
        try:
            if container: container.remove(force=True)
        except Exception: pass
        try:
            if client: client.close()
        except Exception: pass
