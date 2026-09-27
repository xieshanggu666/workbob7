from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Announcement, Project, TenderSection, TenderStatusLog, User
from app.schemas import AnnouncementIn, ProjectIn, SectionIn, TransitionIn
from app.services.audit_service import add_audit
from app.services.escrow_service import return_section_deposits
from app.services.status_service import transition

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    result = []
    for p in projects:
        sections = db.query(TenderSection).filter(TenderSection.project_id == p.id).count()
        result.append(_project_dict(p, sections))
    return result


@router.post("/projects")
def create_project(data: ProjectIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    if db.query(Project).filter(Project.code == data.code).first():
        raise HTTPException(status_code=400, detail="项目编号已存在")
    project = Project(
        code=data.code,
        name=data.name,
        category=data.category,
        budget=data.budget,
        description=data.description,
        status="draft",
        creator_id=user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    add_audit(db, user.id, "CREATE_PROJECT", f"创建招标项目 {project.code} {project.name}")
    return _project_dict(project, 0)


@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    sections = db.query(TenderSection).filter(TenderSection.project_id == project.id).all()
    return {
        **_project_dict(project, len(sections)),
        "sections": [_section_dict(s) for s in sections],
    }


@router.post("/projects/{project_id}/sections")
def create_section(
    project_id: int, data: SectionIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    section = TenderSection(
        project_id=project.id,
        code=data.code,
        name=data.name,
        method=data.method,
        deposit_ratio=data.deposit_ratio,
        qualification_req=data.qualification_req,
        notice_days=data.notice_days,
        status="draft",
    )
    db.add(section)
    db.commit()
    db.refresh(section)
    if project.status == "draft":
        project.status = "published"
        db.commit()
    add_audit(db, user.id, "CREATE_SECTION", f"创建标段 {section.code} {section.name}")
    return _section_dict(section)


@router.get("/sections/{section_id}")
def get_section(section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    return _section_detail(db, section)


@router.post("/sections/{section_id}/transition")
def section_transition(
    section_id: int,
    data: TransitionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "operator")),
):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    if not transition(db, section, data.to_status, user.id, data.remark):
        raise HTTPException(status_code=400, detail=f"不允许从 {section.status} 流转到 {data.to_status}")
    if data.to_status == "failed":
        return_section_deposits(db, section.id, "标段流标，保证金退还")
    add_audit(db, user.id, "SECTION_TRANSITION", f"标段 {section.code} {section.status}→{data.to_status}")
    return _section_dict(section)


@router.post("/sections/{section_id}/announcements")
def create_announcement(
    section_id: int, data: AnnouncementIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))
):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    ann = Announcement(
        section_id=section.id,
        title=data.title,
        content=data.content,
        announce_type=data.announce_type,
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return {"id": ann.id, "title": ann.title, "content": ann.content, "announce_type": ann.announce_type, "published_at": ann.published_at}


def _project_dict(p: Project, sections: int) -> dict:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "category": p.category,
        "budget": float(p.budget),
        "status": p.status,
        "sections": sections,
        "created_at": p.created_at,
    }


def _section_dict(s: TenderSection) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "code": s.code,
        "name": s.name,
        "status": s.status,
        "method": s.method,
        "deposit_ratio": float(s.deposit_ratio),
        "notice_days": s.notice_days,
        "announce_at": s.announce_at,
        "bid_deadline": s.bid_deadline,
        "open_at": s.open_at,
        "qualification_req": s.qualification_req,
    }


def _section_detail(db: Session, s: TenderSection) -> dict:
    from app.models import AbnormalPriceClarification, BidDocument, EscrowAccount, TenderJudge, Winner

    bids = db.query(BidDocument).filter(BidDocument.section_id == s.id).all()
    escrows = db.query(EscrowAccount).filter(EscrowAccount.section_id == s.id).all()
    judges = db.query(TenderJudge).filter(TenderJudge.section_id == s.id).all()
    clarifications = db.query(AbnormalPriceClarification).filter(AbnormalPriceClarification.section_id == s.id).order_by(AbnormalPriceClarification.created_at.asc()).all()
    winner = (
        db.query(Winner)
        .filter(Winner.section_id == s.id, Winner.status != "cancelled")
        .order_by(Winner.created_at.desc())
        .first()
    )
    logs = db.query(TenderStatusLog).filter(TenderStatusLog.section_id == s.id).order_by(TenderStatusLog.created_at.asc()).all()
    return {
        **_section_dict(s),
        "bids": [
            {
                "id": b.id,
                "bidder_id": b.bidder_id,
                "company": b.company,
                "price": float(b.price),
                "license_expiry": b.license_expiry,
                "status": b.status,
                "compliance_json": b.compliance_json,
                "submitted_at": b.submitted_at,
            }
            for b in bids
        ],
        "escrows": [
            {"id": e.id, "bid_document_id": e.bid_document_id, "amount": float(e.amount), "status": e.status, "paid_at": e.paid_at}
            for e in escrows
        ],
        "judges": [{"id": j.id, "user_id": j.user_id} for j in judges],
        "clarifications": [
            {
                "id": c.id,
                "bid_document_id": c.bid_document_id,
                "bidder_id": c.bidder_id,
                "suspected_price": float(c.suspected_price),
                "threshold_price": float(c.threshold_price),
                "status": c.status,
                "response_content": c.response_content,
                "review_remark": c.review_remark,
                "deadline": c.deadline,
                "response_at": c.response_at,
                "reviewed_at": c.reviewed_at,
            }
            for c in clarifications
        ],
        "winner": (
            {
                "id": w.id,
                "bid_document_id": w.bid_document_id,
                "bidder_id": w.bidder_id,
                "win_price": float(w.win_price),
                "publish_start": w.publish_start,
                "publish_end": w.publish_end,
                "status": w.status,
            }
            if winner
            else None
        ),
        "status_logs": [{"from": l.from_status, "to": l.to_status, "remark": l.remark, "created_at": l.created_at} for l in logs],
    }
