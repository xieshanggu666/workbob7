"""投标保证金账务：缴纳 / 退还 / 没收。

- 缴纳：投标人按标段保证金比例足额缴纳
- 退还：未中标 / 异常低价排除 / 流标足额退还保证金
- 没收：中标后放弃中标 / 串通投标等情形没收保证金
"""

from datetime import datetime

from app.models.escrow import EscrowAccount, EscrowTransaction
from app.models.project import Project, TenderSection


def create_account(db, section_id: int, bid_document_id: int, bidder_id: int) -> EscrowAccount:
    section = db.get(TenderSection, section_id)
    project = db.get(Project, section.project_id) if section else None
    budget = float(project.budget or 0) if project else 0
    deposit_amount = float(section.deposit_ratio) * budget if section else 0
    account = EscrowAccount(
        section_id=section_id,
        bid_document_id=bid_document_id,
        bidder_id=bidder_id,
        amount=round(deposit_amount, 2),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def pay_deposit(db, account: EscrowAccount) -> EscrowAccount:
    """投标人缴纳保证金到账。"""
    if account.status != "unpaid":
        return account
    account.status = "paid"
    account.paid_at = datetime.utcnow()
    db.add(
        EscrowTransaction(
            account_id=account.id,
            tx_type="deposit",
            amount=account.amount,
            balance_after=account.amount,
            remark="保证金缴纳",
        )
    )
    db.commit()
    db.refresh(account)
    return account


def return_deposit(db, account: EscrowAccount, reason: str = "未中标保证金退还") -> EscrowAccount:
    """足额退还保证金。"""
    if account.status != "paid":
        return account
    refund = float(account.amount)
    account.status = "returned"
    account.returned_at = datetime.utcnow()
    db.add(
        EscrowTransaction(
            account_id=account.id,
            tx_type="return",
            amount=round(refund, 2),
            balance_after=0,
            remark=reason,
        )
    )
    db.commit()
    db.refresh(account)
    return account


def return_bid_deposit(db, section_id: int, bid_document_id: int, reason: str = "未中标保证金退还") -> list[EscrowAccount]:
    """退还某份投标对应且已缴纳的保证金。"""
    accounts = (
        db.query(EscrowAccount)
        .filter(
            EscrowAccount.section_id == section_id,
            EscrowAccount.bid_document_id == bid_document_id,
            EscrowAccount.status == "paid",
        )
        .all()
    )
    return [return_deposit(db, account, reason) for account in accounts]


def return_section_deposits(db, section_id: int, reason: str = "标段流标，保证金退还") -> list[EscrowAccount]:
    """退还标段下所有仍处于已缴纳状态的保证金。"""
    accounts = (
        db.query(EscrowAccount)
        .filter(EscrowAccount.section_id == section_id, EscrowAccount.status == "paid")
        .all()
    )
    return [return_deposit(db, account, reason) for account in accounts]


def forfeit_deposit(db, account: EscrowAccount, reason: str) -> EscrowAccount:
    """没收保证金（中标后放弃 / 违规）。"""
    if account.status != "paid":
        return account
    account.status = "forfeited"
    account.returned_at = datetime.utcnow()
    db.add(
        EscrowTransaction(
            account_id=account.id,
            tx_type="forfeit",
            amount=float(account.amount),
            balance_after=0,
            remark=f"保证金没收：{reason}",
        )
    )
    db.commit()
    db.refresh(account)
    return account
