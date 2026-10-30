import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.models.sandbox_run import SandboxRun
from app.rbac import Permission, require_permission
from app.sandbox.models import SandboxRequest, SandboxResponse
from app.sandbox.service import run_sandbox
from app.services.task_service import get_task
from app.core.exceptions import NotFoundError
router=APIRouter(prefix="/api/tasks/{task_id}/sandbox",tags=["sandbox"])
def out(r:SandboxRun)->SandboxResponse: return SandboxResponse(id=str(r.id),task_id=str(r.task_id),repository_id=str(r.repository_id),command=r.command,status=r.status.value,exit_code=r.exit_code,stdout=r.stdout or "",stderr=r.stderr or "",duration_ms=r.duration_ms,metadata=r.metadata_json or {})
@router.post("/validate",response_model=SandboxResponse,status_code=201)
def validate(task_id:uuid.UUID,payload:SandboxRequest=SandboxRequest(),db:Session=Depends(get_db),current_user:User=Depends(require_permission(Permission.SANDBOX_EXECUTE))):
    task=get_task(db,user=current_user,task_id=task_id); return out(run_sandbox(db,user=current_user,task_id=task_id,repository_id=task.repository_id,command=payload.command.value))
@router.get("/{run_id}",response_model=SandboxResponse)
def get_run(task_id:uuid.UUID,run_id:uuid.UUID,db:Session=Depends(get_db),current_user:User=Depends(require_permission(Permission.AGENT_READ))):
    get_task(db,user=current_user,task_id=task_id); r=db.get(SandboxRun,run_id)
    if not r or r.task_id!=task_id: raise NotFoundError("Sandbox run not found")
    return out(r)
