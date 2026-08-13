"""VAPT Import Schema - Request/Response models for VAPT Excel import"""

from pydantic import BaseModel, Field
from typing import List, Optional


class VulnerabilitySummary(BaseModel):
    """Summary of an imported vulnerability"""
    vulnerability_id: int
    vulnerability_name: str
    severity: str


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
    summary: VAPTImportSummary
    vulnerabilities: List[VulnerabilitySummary]

    class Config:
        from_attributes = True
