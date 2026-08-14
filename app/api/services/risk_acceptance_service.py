"""Risk Acceptance Service - Business logic for risk acceptance"""

from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from app.api.repositories.vulnerability_repository import VulnerabilityRepository
from app.api.repositories.project_repository import ProjectRepository
from app.api.repositories.user_repository import UserRepository
from app.api.models.vulnerability_master import VulnerabilityMaster
from app.api.models.user_master import UserMaster
from app.api.services.notification_service import NotificationService
from app.api.middleware.error_handler import APIException
from app.core.logger import get_logger

logger = get_logger(__name__)

# Role IDs used to resolve who approves a risk acceptance request.
PRACTICE_HEAD_ROLE_ID = 2  # resolved per-project via project_members
CTO_ROLE_ID = 7            # global role in user_master (fallback approver)

# Severity-based approval routing (reference mapping).
# Low / Medium severity  -> Practice Head (project-scoped, role_id 2)
# High / Critical severity -> CTO (global, role_id 7)
SEVERITY_APPROVER_ROLE = {
    "low": PRACTICE_HEAD_ROLE_ID,
    "medium": PRACTICE_HEAD_ROLE_ID,
    "high": CTO_ROLE_ID,
    "critical": CTO_ROLE_ID,
}

# Approver used when a vulnerability's severity is missing/unrecognised.
DEFAULT_APPROVER_ROLE_ID = PRACTICE_HEAD_ROLE_ID

# Template registered in email_gateway.py / templates/ folder.
RISK_ACCEPTANCE_TEMPLATE = "risk_acceptance_approval_request"


class RiskAcceptanceService:
    """Service for risk acceptance business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.vuln_repo = VulnerabilityRepository(db)
        self.project_repo = ProjectRepository(db)
        self.user_repo = UserRepository(db)
        self.notifier = NotificationService()

    def add_risk_acceptance(
        self,
        vulnerability_id: int,
        justification: str,
        requested_by: int,
        requested_days: Optional[int] = None,
    ) -> VulnerabilityMaster:
        """
        Add risk acceptance request for a vulnerability.

        Updates the vulnerability:
        - risk_status = "true"
        - acceptance_request_date = current date
        - comments_remarks = justification

        After a successful update, an approval-request email is sent to the
        project's Practice Head (or the CTO as a fallback). Email delivery is
        best-effort and never blocks or fails the risk acceptance.

        Args:
            vulnerability_id: ID of the vulnerability
            justification: Justification for accepting the risk
            requested_by: User ID requesting the acceptance
            requested_days: Optional number of extension days requested

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
            "risk_status": "true",
            "acceptance_request_date": datetime.utcnow().date(),
            "comments_remarks": justification,
            "updated_by": requested_by,
            "updated_at": datetime.utcnow(),
        }

        # Update vulnerability
        try:
            updated_vuln = self.vuln_repo.update_vulnerability(vulnerability_id, update_data)
            self.db.commit()
            logger.info(f"Risk acceptance added for vulnerability: {vulnerability_id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to add risk acceptance: {str(e)}", exc_info=True)
            raise APIException(
                status_code=500,
                message=f"Failed to add risk acceptance: {str(e)}",
                message_key="risk_acceptance.failed"
            )

        # Notify the approver (Practice Head / CTO). Best-effort, non-blocking.
        self._send_approval_request_email(
            vulnerability=updated_vuln,
            justification=justification,
            requested_days=requested_days,
        )

        return updated_vuln

    @staticmethod
    def _approver_role_for_severity(severity: Optional[str]) -> int:
        """
        Map a vulnerability severity to the approver role id.

        Severity values in the database are not always plain (e.g.
        "High - Level 4", "Medium - Level 3"), so we match on the severity
        keyword contained in the string rather than an exact value. Falls back
        to DEFAULT_APPROVER_ROLE_ID when no keyword is recognised.
        """
        severity_key = (severity or "").strip().lower()
        for keyword, role_id in SEVERITY_APPROVER_ROLE.items():
            if keyword in severity_key:
                return role_id
        return DEFAULT_APPROVER_ROLE_ID

    def _resolve_approver(self, project_id: int, severity: Optional[str]) -> Optional[UserMaster]:
        """
        Determine who should approve the risk acceptance, based on severity.

        Routing (see SEVERITY_APPROVER_ROLE):
        - Low / Medium    -> project's Practice Head (role_id 2 via project_members)
        - High / Critical -> CTO (role_id 7 in user_master)

        The CTO is used as a fallback whenever the primary (Practice Head)
        approver cannot be resolved for the project.

        Returns the resolved UserMaster, or None if no approver can be found.
        """
        target_role_id = self._approver_role_for_severity(severity)

        if target_role_id == PRACTICE_HEAD_ROLE_ID:
            approver = self.project_repo.get_user_details_by_project_and_role(
                project_id, PRACTICE_HEAD_ROLE_ID
            )
            if approver:
                logger.info(
                    f"Severity '{severity or 'N/A'}' -> Practice Head "
                    f"'{approver.username}' for project {project_id}"
                )
                return approver
            logger.info(
                f"Severity '{severity or 'N/A'}' routes to Practice Head but none "
                f"assigned to project {project_id}; falling back to CTO."
            )
        else:
            logger.info(
                f"Severity '{severity or 'N/A'}' -> CTO for project {project_id}"
            )

        approver = self.user_repo.get_user_by_role(CTO_ROLE_ID)
        if approver:
            logger.info(f"Risk acceptance approver resolved to CTO '{approver.username}'")
            return approver

        logger.warning(
            f"No approver could be resolved for project {project_id} "
            f"(severity '{severity or 'N/A'}'); approval email will not be sent."
        )
        return None

    def _send_approval_request_email(
        self,
        vulnerability: VulnerabilityMaster,
        justification: str,
        requested_days: Optional[int],
    ) -> None:
        """Resolve the approver and send the risk acceptance approval email."""
        approver = self._resolve_approver(vulnerability.project_id, vulnerability.severity)
        if not approver or not approver.email:
            return

        context = {
            "approver_name": approver.username,
            "vulnerability_id": vulnerability.vulnerability_id,
            "vulnerability_name": vulnerability.vulnerability_name,
            "severity": vulnerability.severity or "N/A",
            "requested_days": requested_days if requested_days is not None else "N/A",
            "reason": justification,
        }

        self.notifier.send_template(
            template_name=RISK_ACCEPTANCE_TEMPLATE,
            to_addresses=[approver.email],
            context=context,
        )

