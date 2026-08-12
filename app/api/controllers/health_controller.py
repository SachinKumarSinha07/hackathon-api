"""
Health Controller

Endpoints for health checks and system status.
"""

from fastapi import APIRouter, status
from datetime import datetime
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/health",
    tags=["Health"],
    responses={200: {"description": "Service is healthy"}},
)


@router.get("/", status_code=status.HTTP_200_OK, summary="Basic health check")
async def health_check():
    logger.debug("Health check requested")
    return {
        "status": "healthy",
        "message": "Service is up and running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/status", status_code=status.HTTP_200_OK, summary="Detailed status check")
async def status_check():
    logger.debug("Status check requested")
    return {
        "status": "healthy",
        "application": {
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/ping", status_code=status.HTTP_200_OK, summary="Simple ping endpoint")
async def ping():
    return {"ping": "pong"}
