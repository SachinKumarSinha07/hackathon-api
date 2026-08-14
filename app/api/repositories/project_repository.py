"""Project Repository for database operations"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.api.models.project import Project
from app.api.models.project_member import ProjectMember
from app.api.models.user_master import UserMaster
from app.api.models.role_master import RoleMaster
from app.core.logger import get_logger

logger = get_logger(__name__)


class ProjectRepository:
    """Repository for Project database operations"""

    def __init__(self, db: Session):
        self.db = db

    def check_project_name_exists(self, project_name: str, exclude_project_id: Optional[int] = None) -> bool:
        """Check if a project name already exists"""
        query = self.db.query(Project).filter(Project.project_name == project_name)
        if exclude_project_id:
            query = query.filter(Project.project_id != exclude_project_id)
        return query.first() is not None

    def check_project_url_exists(self, project_url: str, exclude_project_id: Optional[int] = None) -> bool:
        """Check if a project URL already exists"""
        if not project_url:
            return False
        query = self.db.query(Project).filter(Project.project_url == project_url)
        if exclude_project_id:
            query = query.filter(Project.project_id != exclude_project_id)
        return query.first() is not None

    def check_user_exists(self, user_id: int) -> bool:
        """Check if a user exists"""
        return self.db.query(UserMaster).filter(UserMaster.user_id == user_id).first() is not None

    def check_role_exists(self, role_id: int) -> bool:
        """Check if a role exists"""
        return self.db.query(RoleMaster).filter(RoleMaster.role_id == role_id).first() is not None

    def create_project(self, project_data: Dict[str, Any]) -> Project:
        """Create a new project"""
        project = Project(**project_data)
        self.db.add(project)
        self.db.flush()  # Flush to get the project_id
        logger.info(f"Created project: {project.project_id} - {project.project_name}")
        return project

    def add_project_members(self, project_id: int, members: List[Dict[str, int]]) -> None:
        """Add members to a project"""
        for member_data in members:
            project_member = ProjectMember(
                project_id=project_id,
                user_id=member_data['user_id'],
                role_id=member_data['role_id']
            )
            self.db.add(project_member)
        logger.info(f"Added {len(members)} members to project {project_id}")

    def delete_project_members(self, project_id: int) -> None:
        """Delete all members of a project"""
        deleted_count = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id
        ).delete()
        logger.info(f"Deleted {deleted_count} members from project {project_id}")

    def get_project_by_id(self, project_id: int) -> Optional[Project]:
        """Get a project by ID with members"""
        project = self.db.query(Project).filter(Project.project_id == project_id).first()
        return project

    def get_project_with_members(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get a project with full member details"""
        project = self.db.query(Project).filter(Project.project_id == project_id).first()
        
        if not project:
            return None

        # Get members with user and role details
        members = self.db.query(
            ProjectMember.user_id,
            UserMaster.username,
            UserMaster.email,
            ProjectMember.role_id,
            RoleMaster.role_name
        ).join(
            UserMaster, ProjectMember.user_id == UserMaster.user_id
        ).join(
            RoleMaster, ProjectMember.role_id == RoleMaster.role_id
        ).filter(
            ProjectMember.project_id == project_id
        ).all()

        # Convert to dict
        result = {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "project_description": project.project_description,
            "project_type": project.project_type,
            "department": project.department,
            "environment": project.environment,
            "project_url": project.project_url,
            "created_at": project.created_at,
            "created_by": project.created_by,
            "updated_at": project.updated_at,
            "updated_by": project.updated_by,
            "members": [
                {
                    "user_id": member.user_id,
                    "username": member.username,
                    "email": member.email,
                    "role_id": member.role_id,
                    "role_name": member.role_name
                }
                for member in members
            ]
        }
        
        return result

    def get_user_by_project_and_role(self, project_id: int, role_id: int) -> Optional[str]:
        """
        Get a username for a user with a specific role in a project.
        Returns the first matching user's username.

        Args:
            project_id: Project ID
            role_id: Role ID (e.g., 6 for security analyst)

        Returns:
            Optional[str]: Username or None if not found
        """
        result = self.db.query(UserMaster.username).join(
            ProjectMember, UserMaster.user_id == ProjectMember.user_id
        ).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.role_id == role_id
        ).first()

        return result[0] if result else None

    def update_project(self, project_id: int, update_data: Dict[str, Any]) -> Optional[Project]:
        """Update a project"""
        project = self.get_project_by_id(project_id)
        if not project:
            return None

        for key, value in update_data.items():
            if value is not None:
                setattr(project, key, value)
        
        project.updated_at = datetime.utcnow()
        self.db.flush()
        logger.info(f"Updated project: {project_id} - {project.project_name}")
        return project

    def get_all_projects(self, skip: int = 0, limit: int = 100) -> List[Project]:
        """Get all projects with pagination"""
        return self.db.query(Project).offset(skip).limit(limit).all()

    def get_projects_with_vulnerability_stats(
        self,
        project_id: Optional[int] = None,
        round_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get projects with vulnerability statistics for open issues only.
        Open issues are those whose status is not RESOLVED or RISK_ACCEPTED
        (a NULL status is treated as open).
        
        Args:
            project_id: Optional filter by specific project
            round_id: Optional filter by specific round
        
        Returns:
            List of projects with vulnerability counts by severity
        """
        from app.api.models.vulnerability_master import VulnerabilityMaster
        from sqlalchemy import func, case
        
        # Base query for projects
        query = self.db.query(Project)
        
        # Apply filters
        if project_id is not None:
            query = query.filter(Project.project_id == project_id)
        
        projects = query.all()
        
        result = []
        for project in projects:
            # Query vulnerability stats for this project
            vuln_query = self.db.query(
                func.count(case((VulnerabilityMaster.severity.ilike('Critical - Level 5'), 1), else_=None)).label('critical'),
                func.count(case((VulnerabilityMaster.severity.ilike('High - Level 4'), 1), else_=None)).label('high'),
                func.count(case((VulnerabilityMaster.severity.ilike('Medium - Level 3'), 1), else_=None)).label('medium'),
                func.count(case((VulnerabilityMaster.severity.ilike('Low - Level 2'), 1), else_=None)).label('low'),
                func.count(VulnerabilityMaster.vulnerability_id).label('total')
            ).filter(
                VulnerabilityMaster.project_id == project.project_id,
                func.coalesce(VulnerabilityMaster.status, 'OPEN').notin_(['RESOLVED', 'RISK_ACCEPTED'])
            )
            
            # Apply round filter if provided
            if round_id is not None:
                vuln_query = vuln_query.filter(VulnerabilityMaster.round_id == round_id)
            
            stats = vuln_query.first()
            
            result.append({
                "project_id": project.project_id,
                "project_name": project.project_name,
                "project_description": project.project_description,
                "project_type": project.project_type,
                "department": project.department,
                "environment": project.environment,
                "project_url": project.project_url,
                "created_at": project.created_at,
                "vulnerability_stats": {
                    "critical": stats.critical or 0,
                    "high": stats.high or 0,
                    "medium": stats.medium or 0,
                    "low": stats.low or 0,
                    "total": stats.total or 0
                }
            })
        
        return result
