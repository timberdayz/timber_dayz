"""
Data pipeline observability routes.

These endpoints are intentionally lightweight at bootstrap time. They provide
stable inspection surfaces before the refresh runner and metadata persistence
layer are fully wired into production execution paths.
"""

from fastapi import APIRouter

from backend.utils.api_response import success_response

router = APIRouter(prefix="/api/data-pipeline", tags=["data-pipeline"])


@router.get("/status")
async def get_pipeline_status():
    return success_response(
        data={
            "phase": "bootstrap",
            "status": "not_started",
        }
    )


@router.get("/freshness")
async def get_pipeline_freshness():
    return success_response(
        data={
            "phase": "bootstrap",
            "targets": [],
        }
    )


@router.get("/lineage")
async def get_pipeline_lineage():
    return success_response(
        data={
            "phase": "bootstrap",
            "edges": [],
        }
    )
