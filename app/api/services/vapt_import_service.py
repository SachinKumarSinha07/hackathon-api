"""VAPT Import Service - Handles Excel import and processing"""

import json
import tempfile
import shutil
import re
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional
from datetime import datetime, date
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.s3_client import get_s3_client
from app.core.config import settings
from app.api.repositories.vulnerability_repository import VulnerabilityRepository
from app.api.repositories.project_repository import ProjectRepository
from app.api.repositories.round_repository import RoundRepository
from app.api.repositories.severity_sla_config_repository import SeveritySLAConfigRepository
from app.api.middleware.error_handler import APIException

# Deterministic VAPT parser (vapt_parser.py). It extracts findings + report
# metadata, cross-validates every number against an independent source in the
# workbook, and writes byte-exact POC images to a media directory.
from vapt_parser import parse_file

logger = get_logger(__name__)


class VAPTImportService:
    """Service for importing VAPT Excel files and processing vulnerabilities"""

    def __init__(self, db: Session):
        self.db = db
        self.vuln_repo = VulnerabilityRepository(db)
        self.project_repo = ProjectRepository(db)
        self.round_repo = RoundRepository(db)
        self.severity_sla_repo = SeveritySLAConfigRepository(db)
        self.s3_client = get_s3_client()
        
        # Cache valid severities from database
        self.valid_severities = self.severity_sla_repo.get_all_severities()
        logger.info(f"Loaded valid severities from database: {self.valid_severities}")

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for safe S3 usage.
        
        Args:
            filename: Original filename
            
        Returns:
            str: Sanitized filename
        """
        # Remove extension
        name_without_ext = Path(filename).stem
        # Replace spaces and special characters with underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name_without_ext)
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        return sanitized.lower()

    def _generate_report_folder_name(self, filename: str, project_id: int, round_id: int) -> str:
        """
        Generate a unique folder name for this VAPT report.
        Format: project_{project_id}_round_{round_id}_{sanitized_filename}_{timestamp}
        
        Args:
            filename: Original filename
            project_id: Project ID
            round_id: Round ID
            
        Returns:
            str: Unique folder name
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        sanitized_name = self._sanitize_filename(filename)
        folder_name = f"project_{project_id}_round_{round_id}_{sanitized_name}_{timestamp}"
        return folder_name

    def _parse_date(self, date_value) -> Optional[date]:
        """Parse various date formats to date object"""
        if date_value is None or date_value == "":
            return None
        if isinstance(date_value, date):
            return date_value
        if isinstance(date_value, datetime):
            return date_value.date()
        if isinstance(date_value, str):
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(date_value, fmt).date()
                except ValueError:
                    continue
        return None

    def _map_severity(self, severity_input: Optional[str]) -> Optional[str]:
        """
        Map input severity to valid database severity values.
        Uses database configuration instead of hardcoded values.

        Args:
            severity_input: Severity string from Excel

        Returns:
            Optional[str]: Valid severity from database or None
        """
        if not severity_input:
            logger.warning("Empty severity value in Excel, setting to None")
            return None
        
        # Try fuzzy matching against database severities
        matched_severity = self.severity_sla_repo.get_severity_by_fuzzy_match(severity_input)
        
        if matched_severity:
            logger.debug(f"Mapped severity '{severity_input}' -> '{matched_severity}'")
            return matched_severity
        else:
            logger.warning(
                f"Severity '{severity_input}' not found in database. "
                f"Valid severities: {self.valid_severities}. Setting to None."
            )
            return None

    async def import_vapt_excel(
        self,
        excel_file: BinaryIO,
        filename: str,
        project_id: int,
        created_by: int,
        round_id: int,
    ) -> Dict:
        """
        Import VAPT Excel file, extract data, upload to S3, and save to database.

        Args:
            excel_file: Excel file binary stream
            filename: Original filename
            project_id: Project ID to associate vulnerabilities with
            created_by: User ID who is importing
            round_id: Round ID (required)

        Returns:
            Dict: Summary of import results
        """
        temp_dir = None
        try:
            # Validate project exists
            project = self.project_repo.get_project_by_id(project_id)
            if not project:
                raise APIException(
                    status_code=404,
                    message=f"Project with ID {project_id} not found",
                    message_key="vapt.import.project_not_found"
                )
            
            # Validate round exists
            round_obj = self.round_repo.get_round_by_id(round_id)
            if not round_obj:
                raise APIException(
                    status_code=404,
                    message=f"Round with ID {round_id} not found",
                    message_key="vapt.import.round_not_found"
                )
            
            # Validate round belongs to the project
            if round_obj.project_id != project_id:
                raise APIException(
                    status_code=400,
                    message=f"Round {round_id} does not belong to project {project_id}",
                    message_key="vapt.import.round_project_mismatch"
                )
            
            # Create temporary directory for processing
            temp_dir = Path(tempfile.mkdtemp())
            excel_path = temp_dir / filename
            
            # Save uploaded file temporarily
            with open(excel_path, "wb") as f:
                excel_file.seek(0)
                f.write(excel_file.read())
            
            logger.info(f"Processing Excel file: {filename}")

            # Generate unique folder for this report
            report_folder = self._sanitize_filename(filename)
            logger.info(f"Report folder: {report_folder}")

            # Step 1: Upload original Excel to S3 (in dedicated folder)
            excel_file.seek(0)
            clean_filename = filename.replace(' ', '_')
            s3_excel_key = f"{settings.s3_vapt_folder}/{report_folder}/{clean_filename}"
            excel_s3_url = self.s3_client.upload_file(
                excel_file, s3_excel_key, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            logger.info(f"Excel uploaded to S3: {excel_s3_url}")

            # Step 2: Extract & validate data using the deterministic parser.
            # POC images are written byte-exact into poc_images_dir.
            poc_images_dir = temp_dir / "poc_images"
            poc_images_dir.mkdir(exist_ok=True)

            parsed = parse_file(str(excel_path), media_dir=str(poc_images_dir))

            validation = parsed.get("validation", {})
            findings = parsed.get("findings", [])
            report_meta = parsed.get("report", {})
            dashboard = parsed.get("dashboard", {})

            # The parser is designed to fail loudly rather than emit a wrong
            # record. Abort the import on hard validation failures.
            if validation.get("status") == "FAILED":
                error_details = "; ".join(
                    f"{e.get('check')}: {e.get('detail')}"
                    for e in validation.get("errors", [])
                ) or "unknown validation error"
                raise APIException(
                    status_code=422,
                    message=f"VAPT report failed validation and cannot be imported: {error_details}",
                    message_key="vapt.import.validation_failed",
                )

            n_images = sum(
                f.get("poc", {}).get("image_count", 0) for f in findings
            )
            logger.info(
                f"Parsed {len(findings)} findings and {n_images} POC images "
                f"(validation={validation.get('status')})"
            )

            # Step 3: Upload POC images to S3 and map each file -> S3 URL
            image_url_mapping = {}
            for finding in findings:
                for image in finding.get("poc", {}).get("images", []):
                    image_file = image["file"]
                    local_path = poc_images_dir / image_file
                    if local_path.exists():
                        # The parser always writes POC images as PNG
                        s3_key = (
                            f"{settings.s3_vapt_folder}/{report_folder}"
                            f"/poc_images/{image_file}"
                        )
                        s3_url = self.s3_client.upload_local_file(
                            local_path, s3_key, "image/png"
                        )
                        image_url_mapping[image_file] = s3_url
                        logger.debug(f"Uploaded POC image: {image_file}")
                    else:
                        logger.warning(
                            f"POC image referenced but not found on disk: {image_file}"
                        )

            # Step 4: Prepare vulnerability data for database insertion
            vulnerabilities_to_create = []
            for finding in findings:
                # Collect S3 URLs for this finding's POC images
                poc_links = [
                    image_url_mapping[img["file"]]
                    for img in finding.get("poc", {}).get("images", [])
                    if img["file"] in image_url_mapping
                ]
                poc_link_str = ", ".join(poc_links) if poc_links else None

                # Affected assets: prefer parsed URLs + notes, fall back to raw
                affected_assets = finding.get("affected_assets") or []
                affected_notes = finding.get("affected_notes") or []
                endpoint_value = (
                    "\n".join([*affected_assets, *affected_notes])
                    or finding.get("affected_raw")
                )

                severity_normalized = (finding.get("severity") or {}).get("normalized")

                # Map finding fields to database fields
                vuln_data = {
                    "vulnerability_name": finding.get("title") or "Unknown",
                    "severity": self._map_severity(severity_normalized),
                    "endpoint_url_list": endpoint_value,
                    "description": finding.get("description"),
                    "impact": finding.get("impact"),
                    "mitigation": finding.get("mitigation"),
                    "poc_link": poc_link_str,
                    "remarks": finding.get("remarks"),
                    "pic": finding.get("responsible_pic"),
                    "target_date": self._parse_date(finding.get("target_resolution_date")),
                    "project_id": project_id,
                    "round_id": round_id,
                    "created_by": created_by,
                    "created_at": datetime.utcnow(),
                }
                vulnerabilities_to_create.append(vuln_data)

            # Step 5: Bulk insert vulnerabilities into database
            created_vulns = self.vuln_repo.bulk_create_vulnerabilities(vulnerabilities_to_create)
            self.db.commit()

            logger.info(f"Successfully imported {len(created_vulns)} vulnerabilities")

            # Step 6: Clean up temporary files
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)

            return {
                "success": True,
                "message": "VAPT Excel imported successfully",
                "summary": {
                    "excel_file": filename,
                    "excel_s3_url": excel_s3_url,
                    "report_folder": report_folder,
                    "vulnerabilities_imported": len(created_vulns),
                    "poc_images_uploaded": n_images,
                    "project_id": project_id,
                    "round_id": round_id,
                    "validation_status": validation.get("status"),
                    "application_name": report_meta.get("application_name"),
                    "total_findings": dashboard.get("total_findings", len(findings)),
                },
                "vulnerabilities": [
                    {
                        "vulnerability_id": v.vulnerability_id,
                        "vulnerability_name": v.vulnerability_name,
                        "severity": v.severity,
                    }
                    for v in created_vulns
                ],
            }

        except Exception as e:
            # Rollback database changes on error
            self.db.rollback()
            logger.error(f"VAPT import failed: {str(e)}", exc_info=True)
            
            # Clean up temporary files
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            raise APIException(
                status_code=500,
                message=f"Failed to import VAPT Excel: {str(e)}",
                message_key="vapt.import.failed"
            )
