from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from app.core.database import Base


class BidDocument(Base):
    """投标文件。"""

    __tablename__ = "bid_documents"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    bidder_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company = Column(String(128), nullable=False)
    price = Column(Numeric(18, 2), nullable=False)          # 投标报价
    license_expiry = Column(String(10), nullable=False, default="")  # 营业执照有效期 YYYY-MM-DD
    tech_material = Column(Text, nullable=False, default="")         # 技术方案材料
    status = Column(String(16), nullable=False, default="submitted")
    compliance_json = Column(Text, nullable=False, default="{}")     # 合规校验结果
    submitted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Winner(Base):
    """中标结果与公示。"""

    __tablename__ = "winners"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    bid_document_id = Column(Integer, ForeignKey("bid_documents.id"), nullable=False)
    bidder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    win_price = Column(Numeric(18, 2), nullable=False)
    publish_start = Column(DateTime, nullable=True)
    publish_end = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, default="pending")  # pending/confirmed/cancelled
    notice_path = Column(String(256), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    content = Column(Text, nullable=False, default="")
    announce_type = Column(String(16), nullable=False, default="notice")  # notice/result/correction
    published_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ComplianceRule(Base):
    """标段合规校验规则：投标文件必须满足的条件。"""

    __tablename__ = "compliance_rules"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    field = Column(String(64), nullable=False)   # price/license_expiry/tech_material...
    rule_type = Column(String(16), nullable=False)  # required/date/range
    param = Column(String(128), nullable=False, default="")
    message = Column(String(256), nullable=False, default="")
    enabled = Column(Integer, nullable=False, default=1)
