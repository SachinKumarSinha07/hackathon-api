"""Email Templates Model"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class EmailTemplate(Base):
    """Email Templates table model"""

    __tablename__ = "email_templates"

    template_id = Column(Integer, primary_key=True, autoincrement=True)
    template_name = Column(String(150), nullable=False)
    trigger_type = Column(String(20), nullable=False)
    subject = Column(String(255), nullable=False)
    body_html = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    updated_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=datetime.utcnow)

    # Relationships
    updater = relationship("UserMaster", foreign_keys=[updated_by], backref="updated_email_templates")

    def __repr__(self):
        return f"<EmailTemplate(template_id={self.template_id}, template_name='{self.template_name}')>"
