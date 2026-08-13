"""Round Schema - Request/Response models for round management"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class RoundCreateRequest(BaseModel):
    """Request model for creating a new round"""
    round_no: int = Field(..., description="Round number", gt=0)
    round_name: str = Field(..., description="Name of the round", min_length=1, max_length=255)
    version: Optional[str] = Field(None, description="Application version", max_length=50)
    project_id: int = Field(..., description="Project ID", gt=0)
    application_url: Optional[str] = Field(None, description="Application URL", max_length=500)
    environment: Optional[str] = Field(None, description="Environment (e.g., dev, staging, production)", max_length=50)
    is_mail_sent: bool = Field(False, description="Whether notification email has been sent")
    email_template_id: int = Field(..., description="Email template ID (required)", gt=0)
    created_by: int = Field(..., description="User ID creating the round", gt=0)

    class Config:
        json_schema_extra = {
            "example": {
                "round_no": 1,
                "round_name": "Initial Security Assessment",
                "version": "1.0.0",
                "project_id": 1,
                "application_url": "https://app.example.com",
                "environment": "production",
                "is_mail_sent": False,
                "email_template_id": 1,
                "created_by": 1
            }
        }


class RoundUpdateRequest(BaseModel):
    """Request model for updating an existing round"""
    round_no: Optional[int] = Field(None, description="Round number", gt=0)
    round_name: Optional[str] = Field(None, description="Name of the round", min_length=1, max_length=255)
    version: Optional[str] = Field(None, description="Application version", max_length=50)
    application_url: Optional[str] = Field(None, description="Application URL", max_length=500)
    environment: Optional[str] = Field(None, description="Environment", max_length=50)
    is_mail_sent: Optional[bool] = Field(None, description="Whether notification email has been sent")
    email_template_id: Optional[int] = Field(None, description="Email template ID (can update if needed)", gt=0)
    updated_by: int = Field(..., description="User ID performing the update", gt=0)

    class Config:
        json_schema_extra = {
            "example": {
                "round_name": "Updated Security Assessment",
                "version": "1.0.1",
                "application_url": "https://app-updated.example.com",
                "environment": "staging",
                "is_mail_sent": True,
                "updated_by": 1
            }
        }


class RoundResponse(BaseModel):
    """Response model for round data"""
    round_id: int
    round_no: int
    round_name: str
    version: Optional[str] = None
    project_id: int
    application_url: Optional[str] = None
    environment: Optional[str] = None
    is_mail_sent: bool
    email_template_id: int
    created_by: int
    created_at: datetime
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "round_id": 1,
                "round_no": 1,
                "round_name": "Initial Security Assessment",
                "version": "1.0.0",
                "project_id": 1,
                "application_url": "https://app.example.com",
                "environment": "production",
                "is_mail_sent": False,
                "email_template_id": 1,
                "created_by": 1,
                "created_at": "2026-08-13T10:30:00",
                "updated_by": None,
                "updated_at": None
            }
        }
