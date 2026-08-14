"""Project Service for business logic"""

from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from app.api.repositories.project_repository import ProjectRepository
from app.api.schemas.project_schema import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectResponse,
    ProjectMemberResponse,
    ProjectWithStatsResponse,
    VulnerabilityStats
)
from app.core.logger import get_logger

logger = get_logger(__name__)


class ProjectService:
    """Service for Project business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.repository = ProjectRepository(db)

    def create_project(self, request: ProjectCreateRequest, created_by_user_id: int) -> ProjectResponse:
        """
        Create a new project with validations
        
        Validations:
        - Project name must be unique
        - Project URL must be unique (if provided)
        - All users must exist
        - All roles must exist
        """
        # Validate project name uniqueness
        if self.repository.check_project_name_exists(request.project_name):
            logger.warning(f"Duplicate project name: {request.project_name}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{request.project_name}' already exists"
            )

        # Validate project URL uniqueness
        if request.project_url and self.repository.check_project_url_exists(request.project_url):
            logger.warning(f"Duplicate project URL: {request.project_url}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with URL '{request.project_url}' already exists"
            )

        # Validate all users exist
        for member in request.members:
            if not self.repository.check_user_exists(member.user_id):
                logger.warning(f"User not found: {member.user_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {member.user_id} not found"
                )

        # Validate all roles exist
        for member in request.members:
            if not self.repository.check_role_exists(member.role_id):
                logger.warning(f"Role not found: {member.role_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Role with ID {member.role_id} not found"
                )

        # Validate created_by user exists
        if not self.repository.check_user_exists(created_by_user_id):
            logger.warning(f"Created by user not found: {created_by_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Creator user with ID {created_by_user_id} not found"
            )

        # Create project
        project_data = {
            "project_name": request.project_name,
            "project_description": request.project_description,
            "project_type": request.project_type,
            "department": request.department,
            "environment": request.environment,
            "project_url": request.project_url,
            "created_by": created_by_user_id
        }

        try:
            project = self.repository.create_project(project_data)

            # Add project members
            members_data = [
                {"user_id": member.user_id, "role_id": member.role_id}
                for member in request.members
            ]
            self.repository.add_project_members(project.project_id, members_data)

            # Commit the transaction
            self.db.commit()

            logger.info(f"Project created successfully: {project.project_id}")

            # Return full project with members
            return self.get_project(project.project_id)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating project: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create project"
            )

    def update_project(
        self,
        project_id: int,
        request: ProjectUpdateRequest,
        updated_by_user_id: int
    ) -> ProjectResponse:
        """
        Update a project with validations
        
        Validations:
        - Project must exist
        - Project name must be unique (if changed)
        - Project URL must be unique (if changed)
        - All users must exist (if members updated)
        - All roles must exist (if members updated)
        """
        # Check if project exists
        existing_project = self.repository.get_project_by_id(project_id)
        if not existing_project:
            logger.warning(f"Project not found: {project_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID {project_id} not found"
            )

        # Validate project name uniqueness (if changed)
        if request.project_name and self.repository.check_project_name_exists(
            request.project_name, exclude_project_id=project_id
        ):
            logger.warning(f"Duplicate project name: {request.project_name}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{request.project_name}' already exists"
            )

        # Validate project URL uniqueness (if changed)
        if request.project_url and self.repository.check_project_url_exists(
            request.project_url, exclude_project_id=project_id
        ):
            logger.warning(f"Duplicate project URL: {request.project_url}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with URL '{request.project_url}' already exists"
            )

        # Validate members if provided
        if request.members is not None:
            # Validate all users exist
            for member in request.members:
                if not self.repository.check_user_exists(member.user_id):
                    logger.warning(f"User not found: {member.user_id}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"User with ID {member.user_id} not found"
                    )

            # Validate all roles exist
            for member in request.members:
                if not self.repository.check_role_exists(member.role_id):
                    logger.warning(f"Role not found: {member.role_id}")
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Role with ID {member.role_id} not found"
                    )

        # Validate updated_by user exists
        if not self.repository.check_user_exists(updated_by_user_id):
            logger.warning(f"Updated by user not found: {updated_by_user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Updater user with ID {updated_by_user_id} not found"
            )

        try:
            # Prepare update data
            update_data = {
                "updated_by": updated_by_user_id
            }
            
            if request.project_name is not None:
                update_data["project_name"] = request.project_name
            if request.project_description is not None:
                update_data["project_description"] = request.project_description
            if request.project_type is not None:
                update_data["project_type"] = request.project_type
            if request.department is not None:
                update_data["department"] = request.department
            if request.environment is not None:
                update_data["environment"] = request.environment
            if request.project_url is not None:
                update_data["project_url"] = request.project_url

            # Update project
            self.repository.update_project(project_id, update_data)

            # Update members if provided
            if request.members is not None:
                # Delete existing members
                self.repository.delete_project_members(project_id)
                
                # Add new members
                members_data = [
                    {"user_id": member.user_id, "role_id": member.role_id}
                    for member in request.members
                ]
                self.repository.add_project_members(project_id, members_data)

            # Commit the transaction
            self.db.commit()

            logger.info(f"Project updated successfully: {project_id}")

            # Return updated project with members
            return self.get_project(project_id)

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating project: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update project"
            )

    def get_project(self, project_id: int) -> ProjectResponse:
        """Get a project by ID with members"""
        project_data = self.repository.get_project_with_members(project_id)
        
        if not project_data:
            logger.warning(f"Project not found: {project_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID {project_id} not found"
            )

        # Convert members to response schema
        members = [
            ProjectMemberResponse(**member)
            for member in project_data["members"]
        ]

        return ProjectResponse(
            project_id=project_data["project_id"],
            project_name=project_data["project_name"],
            project_description=project_data["project_description"],
            project_type=project_data["project_type"],
            department=project_data["department"],
            environment=project_data["environment"],
            project_url=project_data["project_url"],
            members=members
        )

    def get_projects_with_stats(
        self,
        project_id: Optional[int] = None,
        round_id: Optional[int] = None
    ) -> list[ProjectWithStatsResponse]:
        """
        Get projects with vulnerability statistics for open issues.
        
        Args:
            project_id: Optional filter by specific project
            round_id: Optional filter by specific round
        
        Returns:
            List of projects with vulnerability counts by severity for open issues
        """
        try:
            projects_data = self.repository.get_projects_with_vulnerability_stats(
                project_id=project_id,
                round_id=round_id
            )
            
            result = []
            for project_data in projects_data:
                result.append(
                    ProjectWithStatsResponse(
                        project_id=project_data["project_id"],
                        project_name=project_data["project_name"],
                        project_description=project_data["project_description"],
                        project_type=project_data["project_type"],
                        department=project_data["department"],
                        environment=project_data["environment"],
                        project_url=project_data["project_url"],
                        vulnerability_stats=VulnerabilityStats(**project_data["vulnerability_stats"])
                    )
                )
            
            logger.info(f"Retrieved {len(result)} projects with vulnerability stats")
            return result
            
        except Exception as e:
            logger.error(f"Error getting projects with stats: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve projects with statistics"
            )
