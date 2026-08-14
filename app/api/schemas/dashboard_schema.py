"""Dashboard Schemas - aggregate metric contracts for the executive summary export.

PRIVACY CONSTRAINT: every field below is an aggregate count or label. Do NOT add
finding titles, URLs, assignee names, ticket ids or any other per-record/PII field
to these models - the payload is forwarded verbatim to an external LLM provider.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class SeverityBreakdown(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    total: int = 0


class SlaComplianceRow(BaseModel):
    severity: str
    breached: int = 0
    extended: int = 0
    on_time: int = Field(0, alias="onTime")

    class Config:
        populate_by_name = True


class EscalationRow(BaseModel):
    severity: str
    plus_1_week: int = Field(0, alias="plus1Week")
    plus_2_weeks: int = Field(0, alias="plus2Weeks")
    none: int = 0
    sla_breach: int = Field(0, alias="slaBreach")

    class Config:
        populate_by_name = True


class StatusOverview(BaseModel):
    open: int = 0
    in_progress: int = Field(0, alias="inProgress")
    fix_submitted: int = Field(0, alias="fixSubmitted")
    closed_verified: int = Field(0, alias="closedVerified")
    accepted_risk: int = Field(0, alias="acceptedRisk")
    total_in_scope: int = Field(0, alias="totalInScope")

    class Config:
        populate_by_name = True


class AgingBucket(BaseModel):
    bucket_label: str = Field(..., alias="bucketLabel")
    count: int = 0

    class Config:
        populate_by_name = True


class RepeatFindingsPoint(BaseModel):
    period: str
    new_findings: int = Field(0, alias="newFindings")
    reopened: int = 0
    recurring: int = 0

    class Config:
        populate_by_name = True


class DashboardMetrics(BaseModel):
    """Aggregate dashboard state. Aggregates only - see module docstring."""

    severity_breakdown: SeverityBreakdown = Field(..., alias="severityBreakdown")
    sla_compliance_by_severity: List[SlaComplianceRow] = Field(
        default_factory=list, alias="slaComplianceBySeverity"
    )
    escalation_distribution: List[EscalationRow] = Field(
        default_factory=list, alias="escalationDistribution"
    )
    status_overview: StatusOverview = Field(..., alias="statusOverview")
    vulnerability_aging: List[AgingBucket] = Field(
        default_factory=list, alias="vulnerabilityAging"
    )
    repeat_findings_trend: List[RepeatFindingsPoint] = Field(
        default_factory=list, alias="repeatFindingsTrend"
    )

    class Config:
        populate_by_name = True


class ExportSummaryRequest(BaseModel):
    """Request body for the executive summary export."""

    metrics: DashboardMetrics
    scope_label: Optional[str] = Field(
        None,
        alias="scopeLabel",
        max_length=200,
        description="Human-readable description of the active filters, e.g. 'All projects'",
    )

    class Config:
        populate_by_name = True


class ExportSummaryResponse(BaseModel):
    """Generated executive summary."""

    summary_text: str = Field(..., alias="summaryText")
    generated_at: str = Field(..., alias="generatedAt")
    cached: bool = False

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "summaryText": "The current security posture is moderately elevated...",
                "generatedAt": "2026-08-13T10:24:11.123456+00:00",
                "cached": False,
            }
        }
