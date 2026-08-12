"""Project Member Model"""

from sqlalchemy import Column, Integer, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class ProjectMember(Base):
    """Project Members table model (many-to-many relationship)"""

    __tablename__ = "project_members"

    project_id = Column(Integer, ForeignKey("projects.project_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user_master.user_id"), nullable=False)
    role_id = Column(Integer, ForeignKey("role_master.role_id"), nullable=False)

    # Composite primary key
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "user_id", name="pk_project_members"),
    )

    # Relationships
    project = relationship("Project", backref="members")
    user = relationship("UserMaster", backref="project_memberships")
    role = relationship("RoleMaster", backref="project_assignments")

    def __repr__(self):
        return f"<ProjectMember(project_id={self.project_id}, user_id={self.user_id}, role_id={self.role_id})>"
