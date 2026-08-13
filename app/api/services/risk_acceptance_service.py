"""Risk Acceptance Service - Business logic for risk acceptance"""

from sqlalchemy.orm import Session
from datetime import datetime

from app.api.repositories.vulnerability_repository import VulnerabilityRepository
from app.api.models.vulnerability_master import VulnerabilityMaster
from app.api.middleware.error_handler import APIException
from app.core.logger import get_logger

logger = get_logger(__name__)


class RiskAcceptanceService:
    """Service for risk acceptance business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.vuln_repo = VulnerabilityRepository(db)

    def add_risk_acceptance(
        self,
        vulnerability_id: int,
        justification: str,
        requested_by: int,
    ) -> VulnerabilityMaster:
        """
        Add risk acceptance request for a vulnerability.

        Updates the vulnerability:
        - is_risk_registered = True
        - acceptance_request_date = current timestamp
        - comments_remarks = justification

        Args:
            vulnerability_id: ID of the vulnerability
            justification: Justification for accepting the risk
            requested_by: User ID requesting the acceptance

        Returns:
            VulnerabilityMaster: Updated vulnerability instance

        Raises:
            APIException: If vulnerability not found or already registered
        """
        # Validate vulnerability exists
        vulnerability = self.vuln_repo.get_vulnerability_by_id(vulnerability_id)
        if not vulnerability:
            raise APIException(
                status_code=404,
                message=f"Vulnerability with ID {vulnerability_id} not found",
                message_key="risk_acceptance.vulnerability_not_found"
            )

        # Check if risk is already registered
        if vulnerability.is_risk_registered:
            raise APIException(
                status_code=409,
                message=f"Risk acceptance already registered for vulnerability ID {vulnerability_id}",
                message_key="risk_acceptance.already_registered"
            )

        # Prepare update data
        update_data = {
            "is_risk_registered": True,
            "acceptance_request_date": datetime.utcnow(),
            "comments_remarks": justification,
            "updated_by": requested_by,
            "updated_at": datetime.utcnow(),
        }

        # Update vulnerability
        try:
            updated_vuln = self.vuln_repo.update_vulnerability(vulnerability_id, update_data)
            self.db.commit()
            logger.info(f"Risk acceptance added for vulnerability: {vulnerability_id}")
            return updated_vuln
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to add risk acceptance: {str(e)}", exc_info=True)
            raise APIException(
                status_code=500,
                message=f"Failed to add risk acceptance: {str(e)}",
                message_key="risk_acceptance.failed"
            )
