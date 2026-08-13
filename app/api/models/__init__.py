"""Models package. Import all models here so they register on Base.metadata."""

from app.api.models.role_master import RoleMaster
from app.api.models.user_master import UserMaster
from app.api.models.project import Project
from app.api.models.project_member import ProjectMember
from app.api.models.vulnerability_master import VulnerabilityMaster
from app.api.models.round_master import RoundMaster
from app.api.models.email_template import EmailTemplate
from app.api.models.severity_sla_config import SeveritySLAConfig

__all__ = [
    "RoleMaster",
    "UserMaster",
    "Project",
    "ProjectMember",
    "VulnerabilityMaster",
    "RoundMaster",
    "EmailTemplate",
    "SeveritySLAConfig",
]
