"""Round Service - Business logic for round management"""

from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.api.repositories.round_repository import RoundRepository
from app.api.repositories.project_repository import ProjectRepository
from app.api.models.round_master import RoundMaster
from app.api.middleware.error_handler import APIException
from app.core.logger import get_logger

logger = get_logger(__name__)


class RoundService:
    """Service for round business logic"""

    def __init__(self, db: Session):
        self.db = db
        self.round_repo = RoundRepository(db)
        self.project_repo = ProjectRepository(db)

    def create_round(
        self,
        round_no: int,
        round_name: str,
        project_id: int,
        created_by: int,
        email_template_id: int,
        version: Optional[str] = None,
        application_url: Optional[str] = None,
        environment: Optional[str] = None,
        round_status: Optional[str] = None,
        is_mail_sent: bool = False,
    ) -> RoundMaster:
        """
        Create a new round for a project.

        Args:
            round_no: Round number
            round_name: Name of the round
            project_id: ID of the project
            created_by: User ID creating the round
            email_template_id: Email template ID (required)
            version: Application version (optional)
            application_url: Application URL (optional)
            environment: Environment name (optional)
            round_status: Round status (optional, e.g., pending, in-progress, completed)
            is_mail_sent: Whether mail has been sent (default: False)

        Returns:
            RoundMaster: Created round instance

        Raises:
            APIException: If project doesn't exist or round number already exists
        """
        # Validate project exists
        project = self.project_repo.get_project_by_id(project_id)
        if not project:
            raise APIException(
                status_code=404,
                message=f"Project with ID {project_id} not found",
                message_key="round.project_not_found"
            )

        # Check if round number already exists for this project
        if self.round_repo.check_round_number_exists(project_id, round_no):
            raise APIException(
                status_code=409,
                message=f"Round number {round_no} already exists for project ID {project_id}",
                message_key="round.round_number_exists"
            )

        # Create round data
        round_data = {
            "round_no": round_no,
            "round_name": round_name,
            "version": version,
            "project_id": project_id,
            "application_url": application_url,
            "environment": environment,
            "round_status": round_status,
            "is_mail_sent": is_mail_sent,
            "email_template_id": email_template_id,
            "created_by": created_by,
            "created_at": datetime.utcnow(),
        }

        # Create round
        try:
            round_obj = self.round_repo.create_round(round_data)
            self.db.commit()
            logger.info(f"Round created successfully: {round_obj.round_id}")
            return round_obj
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create round: {str(e)}", exc_info=True)
            raise APIException(
                status_code=500,
                message=f"Failed to create round: {str(e)}",
                message_key="round.creation_failed"
            )

    def get_round_by_id(self, round_id: int) -> RoundMaster:
        """
        Get round by ID.

        Args:
            round_id: Round ID

        Returns:
            RoundMaster: Round instance

        Raises:
            APIException: If round not found
        """
        round_obj = self.round_repo.get_round_by_id(round_id)
        if not round_obj:
            raise APIException(
                status_code=404,
                message=f"Round with ID {round_id} not found",
                message_key="round.not_found"
            )
        return round_obj

    def get_rounds_by_project(self, project_id: int) -> List[RoundMaster]:
        """
        Get all rounds for a project.

        Args:
            project_id: Project ID

        Returns:
            List[RoundMaster]: List of rounds

        Raises:
            APIException: If project not found
        """
        # Validate project exists
        project = self.project_repo.get_project_by_id(project_id)
        if not project:
            raise APIException(
                status_code=404,
                message=f"Project with ID {project_id} not found",
                message_key="round.project_not_found"
            )

        rounds = self.round_repo.get_rounds_by_project(project_id)
        return rounds

    def update_round(
        self,
        round_id: int,
        updated_by: int,
        round_no: Optional[int] = None,
        round_name: Optional[str] = None,
        version: Optional[str] = None,
        application_url: Optional[str] = None,
        environment: Optional[str] = None,
        round_status: Optional[str] = None,
        is_mail_sent: Optional[bool] = None,
        email_template_id: Optional[int] = None,
    ) -> RoundMaster:
        """
        Update an existing round.

        Args:
            round_id: Round ID to update
            updated_by: User ID performing the update
            **kwargs: Fields to update

        Returns:
            RoundMaster: Updated round instance

        Raises:
            APIException: If round not found or update fails
        """
        # Check if round exists
        round_obj = self.round_repo.get_round_by_id(round_id)
        if not round_obj:
            raise APIException(
                status_code=404,
                message=f"Round with ID {round_id} not found",
                message_key="round.not_found"
            )

        # Check if round_no is being changed and if it conflicts
        if round_no is not None and round_no != round_obj.round_no:
            if self.round_repo.check_round_number_exists(round_obj.project_id, round_no):
                raise APIException(
                    status_code=409,
                    message=f"Round number {round_no} already exists for project ID {round_obj.project_id}",
                    message_key="round.round_number_exists"
                )

        # Prepare update data
        update_data = {
            "updated_by": updated_by,
            "updated_at": datetime.utcnow(),
        }

        if round_no is not None:
            update_data["round_no"] = round_no
        if round_name is not None:
            update_data["round_name"] = round_name
        if version is not None:
            update_data["version"] = version
        if application_url is not None:
            update_data["application_url"] = application_url
        if environment is not None:
            update_data["environment"] = environment
        if round_status is not None:
            update_data["round_status"] = round_status
        if is_mail_sent is not None:
            update_data["is_mail_sent"] = is_mail_sent
        if email_template_id is not None:
            update_data["email_template_id"] = email_template_id

        # Update round
        try:
            updated_round = self.round_repo.update_round(round_id, update_data)
            self.db.commit()
            logger.info(f"Round updated successfully: {round_id}")
            return updated_round
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update round: {str(e)}", exc_info=True)
            raise APIException(
                status_code=500,
                message=f"Failed to update round: {str(e)}",
                message_key="round.update_failed"
            )

    def delete_round(self, round_id: int) -> bool:
        """
        Delete a round.

        Args:
            round_id: Round ID to delete

        Returns:
            bool: True if deletion was successful

        Raises:
            APIException: If round not found or deletion fails
        """
        # Check if round exists
        round_obj = self.round_repo.get_round_by_id(round_id)
        if not round_obj:
            raise APIException(
                status_code=404,
                message=f"Round with ID {round_id} not found",
                message_key="round.not_found"
            )

        # Delete round
        try:
            success = self.round_repo.delete_round(round_id)
            self.db.commit()
            logger.info(f"Round deleted successfully: {round_id}")
            return success
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete round: {str(e)}", exc_info=True)
            raise APIException(
                status_code=500,
                message=f"Failed to delete round: {str(e)}",
                message_key="round.deletion_failed"
            )
