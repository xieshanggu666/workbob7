from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from app.core.database import Base


class Project(Base):
    """招标项目。"""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=False, default="货物")  # 货物/服务/工程
    budget = Column(Numeric(18, 2), nullable=False, default=0)
    description = Column(Text, nullable=False, default="")
    status = Column(String(16), nullable=False, default="draft")
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenderSection(Base):
    """标段：实际招标与评标的基本单位。"""

    __tablename__ = "tender_sections"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, default="draft")
    announce_at = Column(DateTime, nullable=True)       # 公告时间
    bid_deadline = Column(DateTime, nullable=True)      # 投标截止
    open_at = Column(DateTime, nullable=True)           # 开标时间
    method = Column(String(32), nullable=False, default="comprehensive")  # comprehensive / lowest_price
    deposit_ratio = Column(Numeric(6, 4), nullable=False, default=0.02)   # 保证金比例
    qualification_req = Column(Text, nullable=False, default="")          # 资格要求
    notice_days = Column(Integer, nullable=False, default=3)              # 中标公示天数
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenderStatusLog(Base):
    __tablename__ = "tender_status_logs"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    from_status = Column(String(16), nullable=False, default="")
    to_status = Column(String(16), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    remark = Column(String(256), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
