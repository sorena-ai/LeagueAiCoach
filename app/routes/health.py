"""Liveness and readiness probes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.assistant.data import (
    CHAMPION_BUILDS,
    CHAMPION_COMBOS,
    CHAMPION_GUIDES,
    PLAYBOOK,
)
from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring and load balancers.

    Returns a simple health status indicating the service is running.
    This endpoint always returns 200 OK if the service is operational.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "sensei-lol-coach",
        },
    )


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint for monitoring and orchestration.

    Verifies that champion data is loaded and the service can serve requests.
    Returns 503 when a required data directory or the guide set is missing.
    """
    required_dirs = {
        "combos": settings.champion_combos_dir,
        "builds": settings.champion_builds_dir,
        "guides": settings.champion_guide_dir,
        "playbook": settings.playbook_dir,
    }
    for label, directory in required_dirs.items():
        if not directory.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Champion {label} data directory not found",
            )

    if not CHAMPION_GUIDES:
        raise HTTPException(
            status_code=503,
            detail="No champion guide data loaded",
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "service": "sensei-lol-coach",
            "champions_loaded": len(CHAMPION_GUIDES),
            "combos_loaded": len(CHAMPION_COMBOS),
            "builds_loaded": len(CHAMPION_BUILDS),
            "playbook_files": len(PLAYBOOK),
        },
    )
