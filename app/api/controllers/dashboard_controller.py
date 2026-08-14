"""Dashboard Controller - AI-generated executive summary for leadership."""

from fastapi import APIRouter, HTTPException, status

from app.api.llm import LLMError
from app.api.schemas.dashboard_schema import (
    ExportSummaryRequest,
    ExportSummaryResponse,
)
from app.api.services.dashboard_service import DashboardService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.post(
    "/export-summary",
    response_model=ExportSummaryResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Generate an executive summary from dashboard metrics",
    description="""
    Turns the current dashboard widget state into a plain-language executive summary
    for non-technical leadership (under 2200 characters).

    **Input:** aggregate metrics only - severity breakdown, SLA compliance, escalation
    distribution, status overview, aging buckets and repeat-findings trend.
    No per-finding data or PII is accepted or expected.

    **Caching:** responses are cached by a hash of the metrics payload, so repeating an
    export with unchanged dashboard state does not re-invoke the model.
    """,
)
def export_summary(request: ExportSummaryRequest):
    """Generate an executive summary from the submitted dashboard metrics"""
    if request.metrics.status_overview.total_in_scope <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="There are no findings in scope to summarize.",
        )

    service = DashboardService()
    try:
        return service.export_summary(request)
    except LLMError as exc:
        logger.warning(f"Executive summary unavailable: {exc.message}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.retryable
            else status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        )
