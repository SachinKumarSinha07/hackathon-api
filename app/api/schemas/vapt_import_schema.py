"""VAPT Import Schema - Request/Response models for VAPT Excel import"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime


class VulnerabilitySummary(BaseModel):
    """Summary of an imported vulnerability"""
    vulnerability_id: int
    vulnerability_name: str
    severity: Optional[str] = None
    endpoint_url_list: Optional[str] = None
    description: Optional[str] = None
    impact: Optional[str] = None
    mitigation: Optional[str] = None
    poc_link: List[str] = Field(default_factory=list, description="List of presigned POC image URLs")
    remarks: Optional[str] = None
    security_analyst: Optional[str] = None
    status: Optional[str] = None
    risk_status: str = "false"
    report_date: Optional[date] = None
    target_date: Optional[date] = None
    project_id: int
    round_id: int
    created_by: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VAPTImportSummary(BaseModel):
    """Summary information about the import operation"""
    excel_file: str
    excel_s3_url: str
    report_folder: str
    vulnerabilities_imported: int
    poc_images_uploaded: int
    project_id: int
    round_id: int
    validation_status: Optional[str] = None
    application_name: Optional[str] = None
    total_findings: Optional[int] = None


class VAPTImportResponse(BaseModel):
    """Response model for VAPT Excel import"""
    success: bool
    message: str
    vulnerabilities: List[VulnerabilitySummary]

    class Config:
        from_attributes = True
