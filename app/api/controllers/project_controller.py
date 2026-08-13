"""Project Controller - API endpoints for project management"""

from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.api.schemas.project_schema import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectResponse,
    ProjectWithStatsResponse
)
from app.api.services.project_service import ProjectService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "/",
    response_model=List[ProjectWithStatsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get projects with vulnerability statistics",
    description="""
    Get a list of projects with vulnerability statistics for open issues.
    
    **Open issues** are vulnerabilities whose status is NOT 'RESOLVED' or 'RISK_ACCEPTED'.
    
    **Filters:**
    - `project_id`: Optional - Filter by specific project ID
    - `round_id`: Optional - Filter vulnerabilities by specific round ID
    
    **Vulnerability Statistics:**
    Statistics are aggregated by severity levels:
    - **critical**: Count of critical severity vulnerabilities
    - **high**: Count of high severity vulnerabilities
    - **medium**: Count of medium severity vulnerabilities
    - **low**: Count of low severity vulnerabilities
    - **info**: Count of informational severity vulnerabilities
    - **total**: Total count of all open vulnerabilities
    
    **Note:** If both filters are null, all projects are returned with their vulnerability counts across all rounds.
    """
)
def get_projects_with_stats(
    project_id: Optional[int] = Query(None, description="Filter by specific project ID", gt=0),
    round_id: Optional[int] = Query(None, description="Filter vulnerabilities by specific round ID", gt=0),
    db: Session = Depends(get_db)
):
    """Get projects with vulnerability statistics for open issues"""
    logger.info(f"Fetching projects with stats - project_id: {project_id}, round_id: {round_id}")
    service = ProjectService(db)
    return service.get_projects_with_stats(project_id=project_id, round_id=round_id)


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    description="""
    Create a new project with members.
    
    **Validations:**
    - Project name must be unique
    - Project URL must be unique (if provided)
    - All user IDs must exist in the database
    - All role IDs must exist in the database
    - No duplicate users in members list
    - Created by user must exist
    
    **Required fields:**
    - project_name: Project name (1-150 characters)
    - project_type: Type of project (web, mobile, api, desktop, embedded, other)
    - environment: Environment (dev, development, staging, uat, production, prod)
    - members: At least one member with user_id and role_id
    
    **Optional fields:**
    - project_description: Detailed description of the project
    - project_url: URL of the project (max 500 characters)
    """
)
def create_project(
    request: ProjectCreateRequest,
    created_by: int = Query(..., description="User ID of the creator", gt=0),
    db: Session = Depends(get_db)
):
    """Create a new project"""
    logger.info(f"Creating project: {request.project_name} by user {created_by}")
    service = ProjectService(db)
    return service.create_project(request, created_by)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a project",
    description="""
    Update an existing project. All fields are optional - only provided fields will be updated.
    
    **Validations:**
    - Project must exist
    - Project name must be unique (if changed)
    - Project URL must be unique (if changed)
    - All user IDs must exist (if members updated)
    - All role IDs must exist (if members updated)
    - No duplicate users in members list (if members updated)
    - Updated by user must exist
    
    **Note:** When updating members, the entire members list is replaced.
    """
)
def update_project(
    project_id: int,
    request: ProjectUpdateRequest,
    updated_by: int = Query(..., description="User ID of the updater", gt=0),
    db: Session = Depends(get_db)
):
    """Update a project"""
    logger.info(f"Updating project: {project_id} by user {updated_by}")
    service = ProjectService(db)
    return service.update_project(project_id, request, updated_by)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project details",
    description="Get detailed information about a project including all members with their roles"
)
def get_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Get a project by ID"""
    logger.info(f"Fetching project: {project_id}")
    service = ProjectService(db)
    return service.get_project(project_id)
