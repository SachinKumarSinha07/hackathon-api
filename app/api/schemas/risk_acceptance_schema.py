"""Risk Acceptance Schema - Request/Response models for risk acceptance"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class RiskAcceptanceRequest(BaseModel):
    """Request model for adding risk acceptance"""
    vulnerability_id: int = Field(..., description="Vulnerability ID", gt=0)
    justification: str = Field(..., description="Justification for risk acceptance", min_length=1)
    requested_by: int = Field(..., description="User ID requesting the risk acceptance", gt=0)

    class Config:
        json_schema_extra = {
            "example": {
                "vulnerability_id": 1,
                "justification": "Risk accepted as the affected component is behind a firewall and not publicly accessible.",
                "requested_by": 1
            }
        }


class RiskAcceptanceResponse(BaseModel):
    """Response model for risk acceptance"""
    vulnerability_id: int
    vulnerability_name: str
    is_risk_registered: bool
    acceptance_request_date: Optional[date] = None
    comments_remarks: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "vulnerability_id": 1,
                "vulnerability_name": "SQL Injection in Login Form",
                "is_risk_registered": True,
                "acceptance_request_date": "2026-08-13",
                "comments_remarks": "Risk accepted as the affected component is behind a firewall."
            }
        }
