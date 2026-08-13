"""Severity SLA Config Repository - Database operations for severity SLA configuration"""

from sqlalchemy.orm import Session
from typing import List, Optional
from app.api.models.severity_sla_config import SeveritySLAConfig
from app.core.logger import get_logger

logger = get_logger(__name__)


class SeveritySLAConfigRepository:
    """Repository for severity SLA configuration database operations"""

    def __init__(self, db: Session):
        self.db = db

    def get_all_severities(self) -> List[str]:
        """
        Get all distinct severity values from configuration.

        Returns:
            List[str]: List of unique severity values
        """
        results = self.db.query(SeveritySLAConfig.severity).distinct().all()
        return [row[0] for row in results]

    def get_all_sla_configs(self) -> List[SeveritySLAConfig]:
        """Get all SLA configurations"""
        return self.db.query(SeveritySLAConfig).all()

    def get_sla_config_by_severity_exposure(
        self, severity: str, exposure: str
    ) -> Optional[SeveritySLAConfig]:
        """
        Get SLA configuration by severity and exposure.

        Args:
            severity: Severity level
            exposure: Exposure level

        Returns:
            Optional[SeveritySLAConfig]: SLA config or None
        """
        return self.db.query(SeveritySLAConfig).filter(
            SeveritySLAConfig.severity == severity,
            SeveritySLAConfig.exposure == exposure
        ).first()

    def validate_severity(self, severity: str) -> bool:
        """
        Check if a severity value exists in the configuration.

        Args:
            severity: Severity value to validate

        Returns:
            bool: True if severity exists
        """
        return self.db.query(SeveritySLAConfig).filter(
            SeveritySLAConfig.severity == severity
        ).first() is not None

    def get_severity_by_fuzzy_match(self, severity_input: str) -> Optional[str]:
        """
        Try to match input severity to configured severity (case-insensitive).

        Args:
            severity_input: Input severity string

        Returns:
            Optional[str]: Matched severity or None
        """
        if not severity_input:
            return None
        
        severity_lower = severity_input.lower().strip()
        
        # Get all severities
        all_severities = self.db.query(SeveritySLAConfig.severity).distinct().all()
        
        # Try exact match (case-insensitive)
        for (sev,) in all_severities:
            if sev.lower() == severity_lower:
                return sev
        
        # Try partial match
        for (sev,) in all_severities:
            if severity_lower in sev.lower() or sev.lower() in severity_lower:
                return sev
        
        return None
