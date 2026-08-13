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
from app.api.models.vulnerability_master import VulnerabilityMaster
from app.api.middleware.error_handler import APIException
from app.api.schemas.vapt_import_schema import (
    VAPTImportResponse,
    VulnerabilitySummary
)

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
            for fmt in [
                "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
                "%d-%m-%Y", "%m-%d-%Y", "%d-%m-%y",
            ]:
                try:
                    return datetime.strptime(date_value.strip(), fmt).date()
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

    def _calculate_target_date(self, severity: Optional[str], report_date: Optional[date]) -> Optional[date]:
        """
        Calculate target date by adding SLA days to report date.

        Args:
            severity: Severity level (e.g., "Critical - Level 5")
            report_date: The report date to add SLA days to

        Returns:
            Optional[date]: Calculated target date or None
        """
        if not severity or not report_date:
            return None

        sla_days = self.severity_sla_repo.get_sla_days_for_severity(severity)
        if sla_days is None:
            logger.warning(f"No SLA days found for severity '{severity}', cannot calculate target_date")
            return None

        from datetime import timedelta
        target_date = report_date + timedelta(days=sla_days)
        logger.debug(f"Calculated target_date: {target_date} (report_date={report_date} + {sla_days} days)")
        return target_date

    def _parse_poc_link(self, poc_link) -> List[str]:
        """
        Normalize a stored poc_link value into a list of URLs.

        Handles new JSON-encoded lists as well as legacy formats
        (a raw URL string or a comma-separated string).
        """
        if not poc_link:
            return []
        if isinstance(poc_link, list):
            return poc_link
        if isinstance(poc_link, str):
            value = poc_link.strip()
            if not value:
                return []
            # Try JSON first (new format)
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
                return [str(parsed)]
            except (json.JSONDecodeError, ValueError):
                # Legacy format: comma-separated or single URL
                return [part.strip() for part in value.split(",") if part.strip()]
        return []

    def _to_vulnerability_summary(self, v: VulnerabilityMaster) -> VulnerabilitySummary:
        """Map a VulnerabilityMaster ORM object to a VulnerabilitySummary schema."""
        return VulnerabilitySummary(
            vulnerability_id=v.vulnerability_id,
            vulnerability_name=v.vulnerability_name,
            severity=v.severity,
            endpoint_url_list=v.endpoint_url_list,
            description=v.description,
            impact=v.impact,
            mitigation=v.mitigation,
            poc_link=self._parse_poc_link(v.poc_link),
            remarks=v.remarks,
            pic=v.pic,
            status=v.status,
            risk_status=v.risk_status,
            report_date=v.report_date,
            target_date=v.target_date,
            project_id=v.project_id,
            round_id=v.round_id,
            created_by=v.created_by,
            created_at=v.created_at,
        )

    def get_vulnerabilities(
        self,
        project_id: Optional[int] = None,
        round_id: Optional[int] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
    ) -> VAPTImportResponse:
        """
        Retrieve vulnerabilities filtered by project, round, severity and status.
        Returns the same response shape as the VAPT import endpoint.

        Args:
            project_id: Optional project ID filter
            round_id: Optional round ID filter
            severity: Optional severity filter
            status: Optional status filter

        Returns:
            VAPTImportResponse: Matching vulnerabilities
        """
        vulns = self.vuln_repo.get_vulnerabilities_filtered(
            project_id=project_id,
            round_id=round_id,
            severity=severity,
            status=status,
        )

        logger.info(
            f"Retrieved {len(vulns)} vulnerabilities "
            f"(project_id={project_id}, round_id={round_id}, "
            f"severity={severity}, status={status})"
        )

        return VAPTImportResponse(
            success=True,
            message=f"Retrieved {len(vulns)} vulnerabilities",
            vulnerabilities=[self._to_vulnerability_summary(v) for v in vulns],
        )

    async def import_vapt_excel(
        self,
        excel_file: BinaryIO,
        filename: str,
        project_id: int,
        created_by: int,
        round_id: int,
    ) -> VAPTImportResponse:
        """
        Import VAPT Excel file, extract data, upload to S3, and save to database.

        Args:
            excel_file: Excel file binary stream
            filename: Original filename
            project_id: Project ID to associate vulnerabilities with
            created_by: User ID who is importing
            round_id: Round ID (required)

        Returns:
            VAPTImportResponse: Import response with summary and vulnerability details
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
            
            # Create temporary directory for processing.
            # Kept inside the application working directory (EC2-safe & writable)
            # and always removed in the `finally` block below.
            local_tmp_base = Path.cwd() / "tmp_vapt"
            local_tmp_base.mkdir(parents=True, exist_ok=True)
            temp_dir = Path(tempfile.mkdtemp(prefix="import_", dir=str(local_tmp_base)))
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

            # Step 3: Upload POC images to S3 and map each file -> viewable URL.
            # We store a presigned GET URL (view/download) in poc_link so the
            # image can be opened directly without the bucket being public.
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
                        # Presigned view/download URL (falls back to raw URL)
                        view_url = self.s3_client.generate_presigned_url(
                            s3_key, expiration=settings.s3_presigned_url_expiry
                        ) or s3_url
                        image_url_mapping[image_file] = view_url
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
                # Store as JSON string in database
                poc_link_str = json.dumps(poc_links) if poc_links else None

                # Affected assets: prefer parsed URLs + notes, fall back to raw
                affected_assets = finding.get("affected_assets") or []
                affected_notes = finding.get("affected_notes") or []
                endpoint_value = (
                    "\n".join([*affected_assets, *affected_notes])
                    or finding.get("affected_raw")
                )

                severity_normalized = (finding.get("severity") or {}).get("normalized")
                mapped_severity = self._map_severity(severity_normalized)
                report_date = self._parse_date(report_meta.get("report_date"))

                # Calculate target_date: use parsed value if present, otherwise calculate from SLA
                parsed_target_date = self._parse_date(finding.get("target_resolution_date"))
                if parsed_target_date is None:
                    target_date = self._calculate_target_date(mapped_severity, report_date)
                else:
                    target_date = parsed_target_date

                # Determine pic: try finding PIC, then report metadata, then project default (role_id 6)
                pic = finding.get("responsible_pic")
                if not pic:
                    pic = self.project_repo.get_user_by_project_and_role(project_id, role_id=6) or ""

                # Map finding fields to database fields
                vuln_data = {
                    "vulnerability_name": finding.get("title") or "Unknown",
                    "severity": mapped_severity,
                    "endpoint_url_list": endpoint_value,
                    "description": finding.get("description"),
                    "impact": finding.get("impact"),
                    "mitigation": finding.get("mitigation"),
                    "poc_link": poc_link_str,
                    "remarks": finding.get("remarks"),
                    "pic": pic,
                    "status": finding.get("status") or "OPEN",
                    "risk_status": "false",
                    "report_date": report_date,
                    "target_date": target_date,
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

            # Build response using Pydantic models (same mapping as retrieve)
            vulnerabilities = [
                self._to_vulnerability_summary(v) for v in created_vulns
            ]

            return VAPTImportResponse(
                success=True,
                message="VAPT Excel imported successfully",
                vulnerabilities=vulnerabilities,
            )

        except APIException:
            # Known/handled errors (validation, not-found, mismatch) must keep
            # their original status code and message.
            self.db.rollback()
            raise
        except Exception as e:
            # Rollback database changes on unexpected error
            self.db.rollback()
            logger.error(f"VAPT import failed: {str(e)}", exc_info=True)
            raise APIException(
                status_code=500,
                message=f"Failed to import VAPT Excel: {str(e)}",
                message_key="vapt.import.failed"
            )
        finally:
            # Always remove the local temp directory (EC2-safe cleanup)
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
