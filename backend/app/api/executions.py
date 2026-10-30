import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.agent_execution import AgentExecution
from app.models.task import Task
from app.models.user import User
from app.rbac import Permission, require_permission
from app.schemas.execution import ExecutionListItem
from app.services.task_service import list_tasks
router=APIRouter(prefix="/api/executions",tags=["executions"])
@router.get("",response_model=list[ExecutionListItem])
def list_executions(limit:int=Query(default=50,ge=1,le=200),db:Session=Depends(get_db),current_user:User=Depends(require_permission(Permission.AGENT_READ))):
    task_ids=[t.id for t in db.query(Task).all()]
    if not task_ids: return []
    rows=(db.query(AgentExecution).filter(AgentExecution.task_id.in_(task_ids)).order_by(AgentExecution.created_at.desc()).limit(limit).all())
    return [ExecutionListItem.model_validate(r) for r in rows]
