from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from app.core.database import Base


class EscrowAccount(Base):
    """投标保证金账户。"""

    __tablename__ = "escrow_accounts"

    id = Column(Integer, primary_key=True)
    section_id = Column(Integer, ForeignKey("tender_sections.id"), nullable=False, index=True)
    bid_document_id = Column(Integer, ForeignKey("bid_documents.id"), nullable=False, index=True)
    bidder_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    paid_at = Column(DateTime, nullable=True)
    returned_at = Column(DateTime, nullable=True)
    status = Column(String(16), nullable=False, default="unpaid")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class EscrowTransaction(Base):
    __tablename__ = "escrow_transactions"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("escrow_accounts.id"), nullable=False, index=True)
    tx_type = Column(String(16), nullable=False)  # deposit/return/forfeit
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    balance_after = Column(Numeric(18, 2), nullable=False, default=0)
    remark = Column(String(256), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
