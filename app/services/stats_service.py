"""仪表盘统计。"""

from sqlalchemy import func

from app.models.bid import BidDocument
from app.models.escrow import EscrowAccount
from app.models.project import Project, TenderSection


def dashboard_stats(db) -> dict:
    total_projects = db.query(Project).count()
    projects_by_status = {
        status: db.query(Project).filter(Project.status == status).count()
        for status in ["draft", "published", "bidding", "evaluating", "awarded", "closed"]
    }
    total_sections = db.query(TenderSection).count()
    sections_by_status = {
        status: db.query(TenderSection).filter(TenderSection.status == status).count()
        for status in ["draft", "announced", "bidding", "evaluating", "awarded", "failed", "closed"]
    }
    total_bids = db.query(BidDocument).count()
    total_escrow = db.query(func.coalesce(func.sum(EscrowAccount.amount), 0)).scalar() or 0
    paid_escrow = db.query(func.coalesce(func.sum(EscrowAccount.amount), 0)).filter(
        EscrowAccount.status == "paid"
    ).scalar() or 0
    return {
        "total_projects": total_projects,
        "projects_by_status": projects_by_status,
        "total_sections": total_sections,
        "sections_by_status": sections_by_status,
        "total_bids": total_bids,
        "total_escrow": float(total_escrow),
        "paid_escrow": float(paid_escrow),
    }
