"""Severity SLA Config Model"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class SeveritySLAConfig(Base):
    """Severity SLA Configuration table model"""

    __tablename__ = "severity_sla_config"

    sla_config_id = Column(Integer, primary_key=True, autoincrement=True)
    severity = Column(String(20), nullable=False)
    exposure = Column(String(20), nullable=False)
    sla_days = Column(Integer, nullable=False)
    escalation_2_days = Column(Integer, nullable=False)
    escalation_final_days = Column(Integer, nullable=False)

    created_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=False)
    created_at = Column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("user_master.user_id"), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True, onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("UserMaster", foreign_keys=[created_by], backref="created_sla_configs")
    updater = relationship("UserMaster", foreign_keys=[updated_by], backref="updated_sla_configs")

    def __repr__(self):
        return f"<SeveritySLAConfig(sla_config_id={self.sla_config_id}, severity='{self.severity}', exposure='{self.exposure}')>"
