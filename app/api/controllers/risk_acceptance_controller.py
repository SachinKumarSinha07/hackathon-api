"""Risk Acceptance Controller - API endpoints for risk acceptance"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.schemas.risk_acceptance_schema import (
    RiskAcceptanceRequest,
    RiskAcceptanceResponse
)
from app.api.services.risk_acceptance_service import RiskAcceptanceService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/risk-acceptance", tags=["Risk Acceptance"])


@router.post(
    "/",
    response_model=RiskAcceptanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Add risk acceptance for a vulnerability",
    description="""
    Register a risk acceptance request for a vulnerability.

    **Process:**
    Based on the provided vulnerability and justification, the following fields are updated:
    - `is_risk_registered`: Set to True
    - `acceptance_request_date`: Set to current timestamp
    - `comments_remarks`: Set to the provided justification

    **Required Fields:**
    - `vulnerability_id`: ID of the vulnerability
    - `justification`: Justification for accepting the risk
    - `requested_by`: User ID requesting the acceptance

    **Validations:**
    - Vulnerability must exist
    - Risk must not already be registered for this vulnerability
    """
)
def add_risk_acceptance(
    request: RiskAcceptanceRequest,
    db: Session = Depends(get_db)
):
    """
    Add risk acceptance for a vulnerability.

    Args:
        request: Risk acceptance request data
        db: Database session

    Returns:
        RiskAcceptanceResponse: Updated vulnerability risk acceptance data
    """
    logger.info(
        f"Adding risk acceptance: vulnerability_id={request.vulnerability_id}, "
        f"requested_by={request.requested_by}"
    )

    service = RiskAcceptanceService(db)
    vulnerability = service.add_risk_acceptance(
        vulnerability_id=request.vulnerability_id,
        justification=request.justification,
        requested_by=request.requested_by,
    )

    logger.info(f"Risk acceptance added successfully for vulnerability: {request.vulnerability_id}")
    return vulnerability
