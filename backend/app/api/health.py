"""
Health check endpoint.

Reports overall service health plus a database connectivity check. Kept
dependency-light on purpose: this endpoint must keep working even if other
subsystems (Milvus, Mistral, Docker sandbox) are unavailable, since it's the
first thing used to verify the deployment.
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()

    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - we want to report *any* failure
        logger.exception("Database health check failed")
        database_status = f"error: {exc.__class__.__name__}"

    overall_status = "ok" if database_status == "ok" else "degraded"

    return HealthResponse(
        status=overall_status,
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        database=database_status,
    )
