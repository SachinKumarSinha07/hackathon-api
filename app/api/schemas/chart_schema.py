"""Chart Schemas - Response models for dashboard chart data"""

from pydantic import BaseModel, Field
from typing import List


class SeverityBreakdownItem(BaseModel):
    """A single severity slice for the severity_breakdown chart"""
    severity: str = Field(..., description="Severity level (trimmed at first space)")
    count: int = Field(..., description="Number of vulnerabilities with this severity")

    class Config:
        json_schema_extra = {
            "example": {
                "severity": "Critical",
                "count": 10
            }
        }


class SlaComplianceItem(BaseModel):
    """SLA compliance buckets for a single severity (sla_compliance_by_severity chart)"""
    severity: str = Field(..., description="Severity level (trimmed at first space)")
    on_time: int = Field(0, description="Resolved within SLA or still inside the SLA window")
    extended: int = Field(0, description="Risk-accepted items within a valid extension window")
    breached: int = Field(0, description="SLA breached, resolved late, or extension expired")

    class Config:
        json_schema_extra = {
            "example": {
                "severity": "Critical",
                "on_time": 6,
                "extended": 2,
                "breached": 3
            }
        }


class StatusBreakdownItem(BaseModel):
    """A single status slice for the status_breakdown chart"""
    status: str = Field(..., description="Vulnerability status value")
    count: int = Field(..., description="Number of vulnerabilities with this status")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "Open",
                "count": 14
            }
        }


class EscalationDistributionItem(BaseModel):
    """Escalation-level counts for a single severity (escalation_distribution chart)"""
    severity: str = Field(..., description="Severity level (trimmed at first space)")
    no_escalation: int = Field(0, description="Open findings not yet past the SLA due date (0 days overdue)")
    sla_breach: int = Field(0, description="Open findings 1-7 days past the SLA due date")
    plus_1_week: int = Field(0, description="Open findings 8-14 days past the SLA due date")
    plus_2_weeks: int = Field(0, description="Open findings 15+ days past the SLA due date")

    class Config:
        json_schema_extra = {
            "example": {
                "severity": "Critical",
                "no_escalation": 4,
                "sla_breach": 3,
                "plus_1_week": 2,
                "plus_2_weeks": 1
            }
        }


class ChartsResponse(BaseModel):
    """
    Chart data keyed by chart name. Each key is a chart identifier and its
    value holds the data required to render that chart.
    """
    severity_breakdown: List[SeverityBreakdownItem] = Field(
        default_factory=list,
        description="Vulnerability counts grouped by severity",
    )
    sla_compliance_by_severity: List[SlaComplianceItem] = Field(
        default_factory=list,
        description="SLA compliance (on_time / extended / breached) grouped by severity",
    )
    status_breakdown: List[StatusBreakdownItem] = Field(
        default_factory=list,
        description="Vulnerability counts grouped by status",
    )
    escalation_distribution: List[EscalationDistributionItem] = Field(
        default_factory=list,
        description="Open-finding counts grouped by severity and escalation level",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "severity_breakdown": [
                    {"severity": "Critical", "count": 10},
                    {"severity": "High", "count": 5},
                    {"severity": "Medium", "count": 12},
                    {"severity": "Low", "count": 8},
                    {"severity": "Info", "count": 3}
                ],
                "sla_compliance_by_severity": [
                    {"severity": "Critical", "on_time": 6, "extended": 2, "breached": 2},
                    {"severity": "High", "on_time": 3, "extended": 1, "breached": 1},
                    {"severity": "Medium", "on_time": 9, "extended": 1, "breached": 2},
                    {"severity": "Low", "on_time": 7, "extended": 0, "breached": 1},
                    {"severity": "Info", "on_time": 3, "extended": 0, "breached": 0}
                ],
                "status_breakdown": [
                    {"status": "Open", "count": 14},
                    {"status": "Fixed Submitted", "count": 6},
                    {"status": "SLA Breached", "count": 4},
                    {"status": "Risk Accepted", "count": 3},
                    {"status": "Closed", "count": 11}
                ],
                "escalation_distribution": [
                    {"severity": "Critical", "no_escalation": 4, "sla_breach": 3, "plus_1_week": 2, "plus_2_weeks": 1},
                    {"severity": "High", "no_escalation": 5, "sla_breach": 2, "plus_1_week": 1, "plus_2_weeks": 0},
                    {"severity": "Medium", "no_escalation": 8, "sla_breach": 2, "plus_1_week": 0, "plus_2_weeks": 0},
                    {"severity": "Low", "no_escalation": 6, "sla_breach": 1, "plus_1_week": 0, "plus_2_weeks": 0},
                    {"severity": "Info", "no_escalation": 3, "sla_breach": 0, "plus_1_week": 0, "plus_2_weeks": 0}
                ]
            }
        }
