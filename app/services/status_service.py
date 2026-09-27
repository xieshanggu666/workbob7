"""标段状态机与中标公示生效。"""

from datetime import date, datetime, timedelta

from app.models.bid import BidDocument, Winner
from app.models.evaluation import AbnormalPriceClarification
from app.models.project import TenderSection, TenderStatusLog

ALLOWED = {
    "draft": {"announced", "closed"},
    "announced": {"bidding", "closed"},
    "bidding": {"evaluating", "failed", "closed"},
    "evaluating": {"awarded", "failed", "closed"},
    "awarded": {"closed"},
    "failed": {"announced", "closed"},
    "closed": set(),
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in ALLOWED.get(from_status, set())


def _has_unresolved_abnormal_price(db, section_id: int) -> bool:
    return (
        db.query(AbnormalPriceClarification)
        .filter(
            AbnormalPriceClarification.section_id == section_id,
            AbnormalPriceClarification.status.in_(["pending", "responded"]),
        )
        .first()
        is not None
    )


def transition(db, section: TenderSection, to_status: str, operator_id: int | None, remark: str = "") -> bool:
    if to_status == "awarded" and _has_unresolved_abnormal_price(db, section.id):
        return False
    if not can_transition(section.status, to_status):
        return False
    db.add(
        TenderStatusLog(
            section_id=section.id,
            from_status=section.status,
            to_status=to_status,
            operator_id=operator_id,
            remark=remark,
        )
    )
    section.status = to_status
    db.commit()
    return True


def start_publicity(db, section: TenderSection, winner: Winner) -> Winner:
    """发布中标公示：公示期从今日起 notice_days 天。"""
    winner.publish_start = datetime.now()
    winner.publish_end = datetime.now() + timedelta(days=section.notice_days)
    db.commit()
    db.refresh(winner)
    return winner


def winner_bid_eligible(db, winner: Winner) -> bool:
    """中标候选人对应的投标仍须有效，且不存在未完成的异常低价澄清。"""
    bid = db.get(BidDocument, winner.bid_document_id)
    if not bid or bid.section_id != winner.section_id or bid.status in {"abn_excluded", "disqualified", "submitted", "clarifying"}:
        return False
    active = (
        db.query(AbnormalPriceClarification)
        .filter(
            AbnormalPriceClarification.section_id == winner.section_id,
            AbnormalPriceClarification.bid_document_id == winner.bid_document_id,
            AbnormalPriceClarification.status.in_(["pending", "responded", "excluded"]),
        )
        .first()
    )
    return active is None


def confirm_expired_publicity(db, winner: Winner) -> bool:
    """公示到期后确认中标生效。"""
    if winner.status != "pending":
        return False
    if not winner.publish_end:
        return False
    if not winner_bid_eligible(db, winner):
        winner.status = "cancelled"
        db.commit()
        return False
    today = date.today()
    end_date = winner.publish_end.date()
    if today < end_date:
        return False
    winner.status = "confirmed"
    db.commit()
    return True
