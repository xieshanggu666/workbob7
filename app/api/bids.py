import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import BidDocument, ComplianceRule, EscrowAccount, TenderSection, User
from app.schemas import BidIn
from app.services.audit_service import add_audit
from app.services.compliance_service import check_bid_document
from app.services.escrow_service import create_account

router = APIRouter(prefix="/api", tags=["bids"])


@router.get("/sections/{section_id}/bids")
def list_bids(section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bids = db.query(BidDocument).filter(BidDocument.section_id == section_id).order_by(BidDocument.submitted_at.asc()).all()
    return [
        {
            "id": b.id,
            "bidder_id": b.bidder_id,
            "company": b.company,
            "price": float(b.price),
            "license_expiry": b.license_expiry,
            "status": b.status,
            "compliance_json": json.loads(b.compliance_json or "{}"),
            "submitted_at": b.submitted_at,
        }
        for b in bids
    ]


@router.post("/sections/{section_id}/bids")
def submit_bid(
    section_id: int, data: BidIn, db: Session = Depends(get_db), user: User = Depends(require_roles("bidder"))
):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    if section.status not in ("announced", "bidding"):
        raise HTTPException(status_code=400, detail="当前标段不接受投标")
    if db.query(BidDocument).filter(BidDocument.section_id == section_id, BidDocument.bidder_id == user.id).first():
        raise HTTPException(status_code=400, detail="已提交过投标文件")

    bid = BidDocument(
        section_id=section_id,
        bidder_id=user.id,
        company=user.company or user.display_name,
        price=data.price,
        license_expiry=data.license_expiry,
        tech_material=data.tech_material,
    )
    db.add(bid)
    db.flush()

    result = check_bid_document(db, section_id, bid)
    bid.compliance_json = json.dumps(result)
    bid.status = "qualified" if result["passed"] else "submitted"
    db.add(bid)
    db.flush()

    create_account(db, section_id, bid.id, user.id)

    if section.status == "announced":
        section.status = "bidding"
        db.commit()
    db.commit()
    db.refresh(bid)
    add_audit(db, user.id, "SUBMIT_BID", f"标段 {section.code} 提交投标 {bid.company}")
    return {"id": bid.id, "compliance": result}


@router.post("/bids/{bid_id}/recheck")
def recheck_bid(bid_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    bid = db.get(BidDocument, bid_id)
    if not bid:
        raise HTTPException(status_code=404, detail="投标文件不存在")
    result = check_bid_document(db, bid.section_id, bid)
    bid.compliance_json = json.dumps(result)
    bid.status = "qualified" if result["passed"] else "submitted"
    db.commit()
    return {"id": bid.id, "compliance": result}
