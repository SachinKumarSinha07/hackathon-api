"""Chart Controller - API endpoints for dashboard chart data"""

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.api.schemas.chart_schema import ChartsResponse
from app.api.services.chart_service import ChartService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/charts", tags=["Charts"])


@router.get(
    "/",
    response_model=ChartsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard chart data",
    description="""
    Returns chart-ready data as a key/value object where each **key** is a
    chart name and each **value** contains the data needed to render it.

    **Charts:**
    - `severity_breakdown`: List of `{ severity, count }` items. Severities are
      sourced from `severity_sla_config` (every configured severity is included,
      even with a count of 0) and counts come from the vulnerability table.
    - `sla_compliance_by_severity`: List of `{ severity, on_time, extended, breached }`
      items. Each vulnerability is classified using its `status`, `risk_status`
      and the relevant dates (`target_date`, `acceptance_expiry_date`,
      `updated_at`): `extended` = risk-accepted within a valid window,
      `breached` = SLA breached / resolved late / expired extension,
      `on_time` = resolved by (or still within) the SLA deadline.

    - `status_breakdown`: List of `{ status, count }` items. All records grouped
      by their `status` value (e.g., Open, Fixed Submitted, SLA Breached,
      Risk Accepted, Closed).

    - `escalation_distribution`: List of
      `{ severity, no_escalation, sla_breach, plus_1_week, plus_2_weeks }` items
      (stacked bar). Counts **open** findings per severity by escalation level,
      derived from days past the SLA due date (`target_date`, or
      `report_date + sla_days` from `severity_sla_config`):
      `<=0d` = no_escalation, `1-7d` = sla_breach, `8-14d` = plus_1_week,
      `15d+` = plus_2_weeks.

    **Filters (optional):**
    - `project_id`: Restrict counts to a specific project
    - `department`: Restrict counts to projects in a specific department
    """
)
def get_charts(
    project_id: Optional[int] = Query(None, description="Filter by specific project ID", gt=0),
    department: Optional[str] = Query(None, description="Filter by department of the owning project"),
    db: Session = Depends(get_db),
):
    """Get dashboard chart datasets keyed by chart name"""
    logger.info(f"Fetching charts - project_id: {project_id}, department: {department}")
    service = ChartService(db)
    return service.get_charts(project_id=project_id, department=department)
