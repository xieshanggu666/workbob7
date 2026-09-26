"""标段状态机与中标公示生效。"""

from datetime import date, datetime, timedelta

from app.models.bid import Winner
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


def transition(db, section: TenderSection, to_status: str, operator_id: int | None, remark: str = "") -> bool:
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


def confirm_expired_publicity(db, winner: Winner) -> bool:
    """公示到期后确认中标生效。"""
    if winner.status != "pending":
        return False
    if not winner.publish_end:
        return False
    today = date.today()
    end_date = winner.publish_end.date()
    if today <= end_date:
        return False
    winner.status = "confirmed"
    db.commit()
    return True
