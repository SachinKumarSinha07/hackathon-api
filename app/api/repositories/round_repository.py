"""Round Repository - Database operations for rounds"""

from sqlalchemy.orm import Session
from typing import List, Optional
from app.api.models.round_master import RoundMaster
from app.core.logger import get_logger

logger = get_logger(__name__)


class RoundRepository:
    """Repository for round database operations"""

    def __init__(self, db: Session):
        self.db = db

    def create_round(self, round_data: dict) -> RoundMaster:
        """
        Create a new round record.

        Args:
            round_data: Dictionary containing round data

        Returns:
            RoundMaster: Created round instance
        """
        round_obj = RoundMaster(**round_data)
        self.db.add(round_obj)
        self.db.flush()
        logger.info(f"Created round: {round_obj.round_id}")
        return round_obj

    def get_round_by_id(self, round_id: int) -> Optional[RoundMaster]:
        """Get a round by ID"""
        return self.db.query(RoundMaster).filter(
            RoundMaster.round_id == round_id
        ).first()

    def get_rounds_by_project(self, project_id: int) -> List[RoundMaster]:
        """Get all rounds for a specific project"""
        return self.db.query(RoundMaster).filter(
            RoundMaster.project_id == project_id
        ).order_by(RoundMaster.round_no.asc()).all()

    def get_round_by_project_and_number(self, project_id: int, round_no: int) -> Optional[RoundMaster]:
        """Get a specific round by project ID and round number"""
        return self.db.query(RoundMaster).filter(
            RoundMaster.project_id == project_id,
            RoundMaster.round_no == round_no
        ).first()

    def update_round(self, round_id: int, update_data: dict) -> Optional[RoundMaster]:
        """Update a round record"""
        round_obj = self.get_round_by_id(round_id)
        if round_obj:
            for key, value in update_data.items():
                setattr(round_obj, key, value)
            self.db.flush()
            logger.info(f"Updated round: {round_id}")
        return round_obj

    def delete_round(self, round_id: int) -> bool:
        """Delete a round record"""
        round_obj = self.get_round_by_id(round_id)
        if round_obj:
            self.db.delete(round_obj)
            self.db.flush()
            logger.info(f"Deleted round: {round_id}")
            return True
        return False

    def check_round_number_exists(self, project_id: int, round_no: int) -> bool:
        """Check if a round number already exists for a project"""
        existing = self.get_round_by_project_and_number(project_id, round_no)
        return existing is not None
