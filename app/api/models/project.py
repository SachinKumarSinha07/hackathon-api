"""Project Model"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Project(Base):
    """Projects table model"""

    __tablename__ = "projects"

    project_id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String(150), nullable=False)
    project_description = Column(Text, nullable=True)
    project_type = Column(String(20), nullable=False)
    environment = Column(String(20), nullable=True)
    project_url = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=False)

    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=True)

    # Relationships
    creator = relationship("UserMaster", foreign_keys=[created_by], backref="created_projects")
    updater = relationship("UserMaster", foreign_keys=[updated_by], backref="updated_projects")

    def __repr__(self):
        return f"<Project(project_id={self.project_id}, project_name='{self.project_name}')>"
