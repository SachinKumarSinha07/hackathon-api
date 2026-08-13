"""Round Controller - API endpoints for round management"""

from fastapi import APIRouter, Depends, status, Path, Query
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.api.schemas.round_schema import (
    RoundCreateRequest,
    RoundUpdateRequest,
    RoundResponse
)
from app.api.services.round_service import RoundService
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/rounds", tags=["Rounds"])


@router.post(
    "/",
    response_model=RoundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new round",
    description="""
    Create a new round for a project.
    
    **Round** represents a testing cycle or phase for a project.
    
    **Required Fields:**
    - `round_no`: Round number (must be unique within the project)
    - `round_name`: Descriptive name for the round
    - `project_id`: ID of the project this round belongs to
    - `created_by`: User ID creating the round
    - `email_template_id`: Email template ID for notifications
    
    **Optional Fields:**
    - `version`: Application version being tested
    - `application_url`: URL of the application for this round
    - `environment`: Environment name (e.g., dev, staging, production)
    - `is_mail_sent`: Whether notification email has been sent (default: False)
    
    **Validations:**
    - Project must exist
    - Round number must be unique within the project
    - All positive integers must be > 0
    """
)
def create_round(
    request: RoundCreateRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new round for a project.
    
    Args:
        request: Round creation request data
        db: Database session
        
    Returns:
        RoundResponse: Created round data
    """
    logger.info(
        f"Creating round: project_id={request.project_id}, "
        f"round_no={request.round_no}, round_name={request.round_name}"
    )
    
    service = RoundService(db)
    round_obj = service.create_round(
        round_no=request.round_no,
        round_name=request.round_name,
        project_id=request.project_id,
        created_by=request.created_by,
        email_template_id=request.email_template_id,
        version=request.version,
        application_url=request.application_url,
        environment=request.environment,
        is_mail_sent=request.is_mail_sent,
    )
    
    logger.info(f"Round created successfully: {round_obj.round_id}")
    return round_obj


@router.get(
    "/{round_id}",
    response_model=RoundResponse,
    status_code=status.HTTP_200_OK,
    summary="Get round by ID",
    description="Retrieve a specific round by its ID."
)
def get_round(
    round_id: int = Path(..., description="Round ID", gt=0),
    db: Session = Depends(get_db)
):
    """
    Get round by ID.
    
    Args:
        round_id: Round ID
        db: Database session
        
    Returns:
        RoundResponse: Round data
    """
    logger.info(f"Fetching round: {round_id}")
    
    service = RoundService(db)
    round_obj = service.get_round_by_id(round_id)
    
    return round_obj


@router.get(
    "/project/{project_id}",
    response_model=List[RoundResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all rounds for a project",
    description="""
    Retrieve all rounds for a specific project.
    
    Rounds are returned ordered by round number (ascending).
    """
)
def get_rounds_by_project(
    project_id: int = Path(..., description="Project ID", gt=0),
    db: Session = Depends(get_db)
):
    """
    Get all rounds for a project.
    
    Args:
        project_id: Project ID
        db: Database session
        
    Returns:
        List[RoundResponse]: List of rounds
    """
    logger.info(f"Fetching rounds for project: {project_id}")
    
    service = RoundService(db)
    rounds = service.get_rounds_by_project(project_id)
    
    return rounds


@router.put(
    "/{round_id}",
    response_model=RoundResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a round",
    description="""
    Update an existing round.
    
    **Updatable Fields:**
    - `round_no`: Round number (must remain unique within the project)
    - `round_name`: Round name
    - `version`: Application version
    - `application_url`: Application URL
    - `environment`: Environment name
    - `is_mail_sent`: Mail sent status
    - `email_template_id`: Email template ID
    
    **Note:** Only provide fields you want to update. Omitted fields will remain unchanged.
    """
)
def update_round(
    round_id: int = Path(..., description="Round ID to update", gt=0),
    request: RoundUpdateRequest = ...,
    db: Session = Depends(get_db)
):
    """
    Update an existing round.
    
    Args:
        round_id: Round ID to update
        request: Update request data
        db: Database session
        
    Returns:
        RoundResponse: Updated round data
    """
    logger.info(f"Updating round: {round_id}")
    
    service = RoundService(db)
    round_obj = service.update_round(
        round_id=round_id,
        updated_by=request.updated_by,
        round_no=request.round_no,
        round_name=request.round_name,
        version=request.version,
        application_url=request.application_url,
        environment=request.environment,
        is_mail_sent=request.is_mail_sent,
        email_template_id=request.email_template_id,
    )
    
    logger.info(f"Round updated successfully: {round_id}")
    return round_obj


@router.delete(
    "/{round_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a round",
    description="""
    Delete a round by ID.
    
    **Warning:** This will permanently delete the round.
    Consider the impact on related vulnerabilities before deletion.
    """
)
def delete_round(
    round_id: int = Path(..., description="Round ID to delete", gt=0),
    db: Session = Depends(get_db)
):
    """
    Delete a round.
    
    Args:
        round_id: Round ID to delete
        db: Database session
        
    Returns:
        No content (204)
    """
    logger.info(f"Deleting round: {round_id}")
    
    service = RoundService(db)
    service.delete_round(round_id)
    
    logger.info(f"Round deleted successfully: {round_id}")
    return None
