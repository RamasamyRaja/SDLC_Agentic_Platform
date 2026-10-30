"""
FastAPI application entrypoint.

FastAPI is the HTTP/API layer only: it receives requests, validates them,
and (starting in later milestones) creates task records and kicks off the
LangGraph agent workflow. It is NOT the reasoning engine.
"""
from fastapi import FastAPI

from app.api.agent import router as agent_router
from app.api.auth import router as auth_router, users_router
from app.api.errors import register_exception_handlers
from app.api.executions import router as executions_router
from app.api.health import router as health_router
from app.api.onboarding import router as onboarding_router
from app.api.repositories import router as repositories_router
from app.api.sandbox import router as sandbox_router
from app.api.reports import router as reports_router
from app.api.retrieval import router as retrieval_router
from app.api.task_analysis import router as task_analysis_router
from app.api.task_artifacts import router as task_artifacts_router
from app.api.tasks import router as tasks_router
from app.api.workflow import router as workflow_router
from app.api.tools import router as tools_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(executions_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(repositories_router)
app.include_router(onboarding_router)
app.include_router(retrieval_router)
app.include_router(tasks_router)
app.include_router(workflow_router)
app.include_router(task_artifacts_router)
app.include_router(task_analysis_router)
app.include_router(agent_router)
app.include_router(tools_router)
app.include_router(sandbox_router)
app.include_router(reports_router)


@app.on_event("startup")
def _recover_interrupted_work() -> None:
    """Background work lives in this process; after a restart anything still 'working' is orphaned. Stale ones are failed so
    the normal retry actions appear (thresholds: *_STALE_AFTER_SECONDS)."""
    if not settings.STARTUP_RECOVERY_ENABLED:
        return
    import logging
    from app.db.session import SessionLocal
    from app.workflow import lifecycle
    db = SessionLocal()
    try:
        n = lifecycle.recover_all_stale(db)
        if n:
            logging.getLogger(__name__).warning("Recovered %d interrupted task(s) at startup", n)
    except Exception:  # noqa: BLE001 - recovery is best effort and must never stop the API from starting
        logging.getLogger(__name__).exception("Startup recovery failed")
    finally:
        db.close()


@app.get("/", tags=["root"])
def root() -> dict:
    return {
        "service": settings.APP_NAME,
        "status": "running",
        "docs": "/docs",
    }
