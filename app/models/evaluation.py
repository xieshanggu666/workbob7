from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from app.core.database import Base


class EvaluationRule(Base):
    """标段评标规则：评标方法 + 价格权重等参数。"""

    __tablename__ = "evaluation_rules"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    method = Column(String(32), nullable=False, default="comprehensive")
    price_weight = Column(Numeric(5, 4), nullable=False, default=0.4)   # 价格权重（综合评分法）
    price_full_score = Column(Numeric(8, 2), nullable=False, default=100)
    abnormal_price_ratio = Column(Numeric(6, 4), nullable=False, default=0.6)  # 低于平均价该比例判异常
    drop_highest_lowest = Column(Integer, nullable=False, default=1)    # 是否去掉最高最低分
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvaluationItem(Base):
    """评分项（技术/商务主观项，由评委打分）。"""

    __tablename__ = "evaluation_items"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    category = Column(String(16), nullable=False, default="tech")  # tech / business
    weight = Column(Numeric(5, 4), nullable=False, default=0.1)
    full_score = Column(Numeric(8, 2), nullable=False, default=10)


class TenderJudge(Base):
    """标段评标委员会成员。"""

    __tablename__ = "tender_judges"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class BidScore(Base):
    """评委对某投标文件的打分记录。"""

    __tablename__ = "bid_scores"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    bid_document_id = Column(Integer, ForeignKey("bid_documents.id"), nullable=False, index=True)
    judge_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scores_json = Column(Text, nullable=False, default="{}")   # {"item_id": score}
    total_score = Column(Numeric(8, 2), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
