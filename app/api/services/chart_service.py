"""Chart Service - Business logic for dashboard chart data"""

from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta

from app.api.repositories.vulnerability_repository import VulnerabilityRepository
from app.api.repositories.severity_sla_config_repository import SeveritySLAConfigRepository
from app.api.schemas.chart_schema import (
    ChartsResponse,
    SeverityBreakdownItem,
    SlaComplianceItem,
    StatusBreakdownItem,
    EscalationDistributionItem,
)
from app.core.logger import get_logger

logger = get_logger(__name__)


class ChartService:
    """Service to build dashboard chart datasets"""

    def __init__(self, db: Session):
        self.db = db
        self.vuln_repo = VulnerabilityRepository(db)
        self.severity_repo = SeveritySLAConfigRepository(db)

    def get_charts(
        self,
        project_id: Optional[int] = None,
        department: Optional[str] = None,
    ) -> ChartsResponse:
        """
        Build all chart datasets keyed by chart name.

        Args:
            project_id: Optional filter by project
            department: Optional filter by department (owning project)

        Returns:
            ChartsResponse: Object keyed by chart name with chart-ready data
        """
        return ChartsResponse(
            severity_breakdown=self._build_severity_breakdown(project_id, department),
            sla_compliance_by_severity=self._build_sla_compliance_by_severity(
                project_id, department
            ),
            status_breakdown=self._build_status_breakdown(project_id, department),
            escalation_distribution=self._build_escalation_distribution(
                project_id, department
            ),
        )

    def _build_severity_breakdown(
        self,
        project_id: Optional[int],
        department: Optional[str],
    ) -> list[SeverityBreakdownItem]:
        """
        Build the severity_breakdown chart.

        Severities are sourced from severity_sla_config (so every configured
        severity appears, even with a zero count) and counts come from the
        vulnerability table.
        
        Severity values are trimmed at the first space (e.g., "Critical - Level 5" -> "Critical").
        """
        severities = self.severity_repo.get_severities_ordered()
        counts = self.vuln_repo.get_severity_counts(
            project_id=project_id, department=department
        )

        logger.info(
            f"Building severity_breakdown - severities={len(severities)}, "
            f"project_id={project_id}, department={department}"
        )

        return [
            SeverityBreakdownItem(
                severity=severity.split()[0] if severity and ' ' in severity else severity,
                count=counts.get(severity, 0)
            )
            for severity in severities
        ]

    def _build_status_breakdown(
        self,
        project_id: Optional[int],
        department: Optional[str],
    ) -> list[StatusBreakdownItem]:
        """
        Build the status_breakdown chart.

        Returns every distinct status present in the (optionally filtered)
        vulnerability table with its record count, grouped by status.
        """
        counts = self.vuln_repo.get_status_counts(
            project_id=project_id, department=department
        )

        logger.info(
            f"Building status_breakdown - statuses={len(counts)}, "
            f"project_id={project_id}, department={department}"
        )

        return [
            StatusBreakdownItem(status=status, count=count)
            for status, count in counts.items()
        ]

    def _build_sla_compliance_by_severity(
        self,
        project_id: Optional[int],
        department: Optional[str],
    ) -> list[SlaComplianceItem]:
        """
        Build the sla_compliance_by_severity chart.

        Each vulnerability is classified into one of three SLA buckets
        (on_time / extended / breached) based on its status, risk_status and
        the relevant date columns, then grouped by normalized severity.

        Severity buckets are seeded from severity_sla_config so every configured
        severity appears (even with all-zero counts). Severity values are
        trimmed at the first space (e.g., "Critical - Level 5" -> "Critical").
        """
        severities = self.severity_repo.get_severities_ordered()
        rows = self.vuln_repo.get_sla_compliance_rows(
            project_id=project_id, department=department
        )

        buckets: dict[str, dict[str, int]] = {}
        order: list[str] = []

        def register(severity: Optional[str]) -> str:
            normalized = (
                severity.split()[0] if severity and ' ' in severity else severity
            )
            if normalized not in buckets:
                buckets[normalized] = {"on_time": 0, "extended": 0, "breached": 0}
                order.append(normalized)
            return normalized

        for severity in severities:
            register(severity)

        today = date.today()
        for severity, status, risk_status, target_date, acceptance_expiry_date, updated_at in rows:
            normalized = register(severity)
            bucket = self._classify_sla_bucket(
                status=status,
                risk_status=risk_status,
                target_date=target_date,
                acceptance_expiry_date=acceptance_expiry_date,
                updated_at=updated_at,
                today=today,
            )
            buckets[normalized][bucket] += 1

        logger.info(
            f"Building sla_compliance_by_severity - severities={len(order)}, "
            f"rows={len(rows)}, project_id={project_id}, department={department}"
        )

        return [
            SlaComplianceItem(severity=severity, **buckets[severity])
            for severity in order
        ]

    @staticmethod
    def _classify_sla_bucket(
        status: Optional[str],
        risk_status: Optional[str],
        target_date,
        acceptance_expiry_date,
        updated_at,
        today: date,
    ) -> str:
        """
        Classify a single vulnerability into an SLA-compliance bucket.

        Evaluation order (status alone is not enough - it is combined with the
        relevant dates):
          1. extended  - risk-accepted and still within a valid extension window
                         (expired extension falls through to breached)
          2. breached  - explicit "SLA Breached", resolved after the deadline,
                         or unresolved past the deadline
          3. on_time   - resolved by the deadline, or still open before it

        Returns:
            str: one of "on_time", "extended", "breached"
        """
        status_norm = (status or "").strip().lower()
        is_risk = (
            str(risk_status).strip().lower() == "true"
            or status_norm == "risk accepted"
        )

        # 1. Risk accepted -> extended while the acceptance window is still valid
        if is_risk:
            if acceptance_expiry_date is None or acceptance_expiry_date >= today:
                return "extended"
            return "breached"

        # 2. Explicitly flagged as breached
        if status_norm == "sla breached":
            return "breached"

        # 3. Resolved items -> on_time unless they were resolved after the deadline
        if status_norm in ("closed", "fixed submitted"):
            if target_date is None or updated_at is None:
                return "on_time"
            return "breached" if updated_at.date() > target_date else "on_time"

        # 4. Open / other unresolved -> breached once past the deadline
        if target_date is not None and target_date < today:
            return "breached"
        return "on_time"

    # Statuses that are no longer "open" and are excluded from escalation counts
    _NON_OPEN_STATUSES = {"closed", "fixed submitted", "risk accepted"}

    def _build_escalation_distribution(
        self,
        project_id: Optional[int],
        department: Optional[str],
    ) -> list[EscalationDistributionItem]:
        """
        Build the escalation_distribution stacked-bar chart.

        Only open findings are counted (status not in closed / fixed submitted /
        risk accepted). Each finding's escalation level is derived from how many
        days past its SLA due date it currently is:
            <= 0 days  -> no_escalation
            1-7 days   -> sla_breach
            8-14 days  -> plus_1_week
            >= 15 days -> plus_2_weeks

        The SLA due date is `target_date` when present, otherwise it is derived
        as `report_date + sla_days` (sla_days from severity_sla_config).
        Counts are grouped by normalized severity.
        """
        severities = self.severity_repo.get_severities_ordered()
        sla_days_map = self.severity_repo.get_sla_days_map()
        rows = self.vuln_repo.get_escalation_rows(
            project_id=project_id, department=department
        )

        buckets: dict[str, dict[str, int]] = {}
        order: list[str] = []

        def register(severity: Optional[str]) -> str:
            normalized = (
                severity.split()[0] if severity and ' ' in severity else severity
            )
            if normalized not in buckets:
                buckets[normalized] = {
                    "no_escalation": 0,
                    "sla_breach": 0,
                    "plus_1_week": 0,
                    "plus_2_weeks": 0,
                }
                order.append(normalized)
            return normalized

        for severity in severities:
            register(severity)

        today = date.today()
        open_count = 0
        for severity, status, target_date, report_date in rows:
            if (status or "").strip().lower() in self._NON_OPEN_STATUSES:
                continue
            open_count += 1
            normalized = register(severity)
            due_date = self._resolve_due_date(
                target_date, report_date, sla_days_map.get(severity)
            )
            level = self._classify_escalation_level(due_date, today)
            buckets[normalized][level] += 1

        logger.info(
            f"Building escalation_distribution - severities={len(order)}, "
            f"open_findings={open_count}, project_id={project_id}, department={department}"
        )

        return [
            EscalationDistributionItem(severity=severity, **buckets[severity])
            for severity in order
        ]

    @staticmethod
    def _resolve_due_date(target_date, report_date, sla_days: Optional[int]):
        """
        Resolve the SLA due date for a finding.

        Uses `target_date` when present, otherwise derives it as
        `report_date + sla_days`. Returns None when it cannot be determined.
        """
        if target_date is not None:
            return target_date
        if report_date is not None and sla_days is not None:
            return report_date + timedelta(days=sla_days)
        return None

    @staticmethod
    def _classify_escalation_level(due_date, today: date) -> str:
        """
        Map a finding to an escalation level from how many days past its SLA
        due date it is: <=0 no_escalation, 1-7 sla_breach, 8-14 plus_1_week,
        >=15 plus_2_weeks. Undeterminable due dates count as no_escalation.
        """
        if due_date is None:
            return "no_escalation"
        days_past = (today - due_date).days
        if days_past <= 0:
            return "no_escalation"
        if days_past <= 7:
            return "sla_breach"
        if days_past <= 14:
            return "plus_1_week"
        return "plus_2_weeks"
