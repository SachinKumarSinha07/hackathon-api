"""Chat Schemas for request/response validation"""

from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.api.schemas.vulnerability_schema import VulnerabilityFilterParams


class ChatRequest(BaseModel):
    """Schema for a chat message against vulnerability data"""

    session_id: str = Field(
        ...,
        alias="sessionId",
        min_length=1,
        max_length=200,
        description="Client conversation id",
    )
    message: str = Field(
        ..., min_length=1, max_length=4000, description="User question"
    )
    scope: Literal["global", "filtered"] = Field(
        "filtered",
        description="'global' = all vulnerabilities in scope for the user, 'filtered' = only records matching the active table filters",
    )
    filters: Optional[VulnerabilityFilterParams] = Field(
        None, description="Active table filters - only used when scope is 'filtered'"
    )

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "sessionId": "3f6c1c1e-1a2b-4d5e-9f00-0c1d2e3f4a5b",
                "message": "How many Critical severity vulnerabilities do we have?",
                "scope": "filtered",
                "filters": {
                    "project": "All Projects",
                    "round": "All Rounds",
                    "severity": "Critical",
                    "devStatus": "All Statuses",
                    "verification": "All Verification",
                },
            }
        }


class ChatResponse(BaseModel):
    """Schema for a chat reply"""

    reply: str

    class Config:
        json_schema_extra = {
            "example": {
                "reply": "Based on the current filtered view (Severity: Critical), there are 7 findings."
            }
        }


class VulnAssistRequest(BaseModel):
    """Schema for an AI mitigation/impact generation request for a single finding."""

    description: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The vulnerability/issue description to base the generation on",
    )
    name: Optional[str] = Field(
        None, max_length=300, description="Vulnerability name/title, if available"
    )
    severity: Optional[str] = Field(
        None, max_length=50, description="Severity (Critical/High/Medium/Low/Info)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "description": "User input on the login form is passed directly into a SQL query without sanitization.",
                "name": "SQL Injection on login form",
                "severity": "Critical",
            }
        }


class VulnAssistResponse(BaseModel):
    """Schema for an AI mitigation/impact generation reply."""

    text: str

    class Config:
        json_schema_extra = {
            "example": {
                "text": "1. Apply parameterized queries...\n2. Enforce input validation..."
            }
        }
