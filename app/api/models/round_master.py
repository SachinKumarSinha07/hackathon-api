"""Round Master Model"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class RoundMaster(Base):
    """Round Master table model"""

    __tablename__ = "round_master"

    round_id = Column(Integer, primary_key=True, autoincrement=True)
    round_no = Column(Integer, nullable=False)
    round_name = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.project_id"), nullable=False)
    application_url = Column(String, nullable=True)
    environment = Column(String, nullable=True)
    is_mail_sent = Column(Boolean, nullable=False, default=False)

    created_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", backref="rounds")
    creator = relationship("UserMaster", foreign_keys=[created_by], backref="created_rounds")
    updater = relationship("UserMaster", foreign_keys=[updated_by], backref="updated_rounds")

    def __repr__(self):
        return f"<RoundMaster(round_id={self.round_id}, round_no={self.round_no}, round_name='{self.round_name}')>"
