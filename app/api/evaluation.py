import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import (
    BidDocument,
    BidScore,
    EvaluationItem,
    EvaluationRule,
    TenderJudge,
    TenderSection,
    User,
    Winner,
)
from app.schemas import ItemIn, JudgeIn, RuleIn, ScoreIn
from app.services.audit_service import add_audit
from app.services.evaluation_service import detect_abnormal_low, evaluate_section
from app.services.status_service import start_publicity, transition

router = APIRouter(prefix="/api", tags=["evaluation"])


def _get_rule(db, section_id: int) -> EvaluationRule:
    rule = db.query(EvaluationRule).filter(EvaluationRule.section_id == section_id).first()
    if not rule:
        rule = EvaluationRule(section_id=section_id)
        db.add(rule)
        db.commit()
        db.refresh(rule)
    return rule


@router.get("/sections/{section_id}/evaluation")
def evaluation_config(section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    rule = _get_rule(db, section_id)
    items = db.query(EvaluationItem).filter(EvaluationItem.section_id == section_id).all()
    judges = db.query(TenderJudge).filter(TenderJudge.section_id == section_id).all()
    return {
        "rule": {
            "method": rule.method,
            "price_weight": float(rule.price_weight),
            "price_full_score": float(rule.price_full_score),
            "abnormal_price_ratio": float(rule.abnormal_price_ratio),
            "drop_highest_lowest": rule.drop_highest_lowest,
        },
        "items": [{"id": i.id, "name": i.name, "category": i.category, "weight": float(i.weight), "full_score": float(i.full_score)} for i in items],
        "judges": [{"id": j.id, "user_id": j.user_id} for j in judges],
    }


@router.post("/sections/{section_id}/evaluation/rule")
def update_rule(
    section_id: int, data: RuleIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))
):
    rule = _get_rule(db, section_id)
    rule.method = data.method
    rule.price_weight = data.price_weight
    rule.price_full_score = data.price_full_score
    rule.abnormal_price_ratio = data.abnormal_price_ratio
    rule.drop_highest_lowest = data.drop_highest_lowest
    db.commit()
    return {"ok": True}


@router.post("/sections/{section_id}/evaluation/items")
def add_item(section_id: int, data: ItemIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    item = EvaluationItem(section_id=section_id, name=data.name, category=data.category, weight=data.weight, full_score=data.full_score)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "name": item.name}


@router.post("/sections/{section_id}/evaluation/judges")
def add_judge(section_id: int, data: JudgeIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    judge_user = db.get(User, data.user_id)
    if not judge_user or judge_user.role != "judge":
        raise HTTPException(status_code=400, detail="评委用户不存在或角色不符")
    if db.query(TenderJudge).filter(TenderJudge.section_id == section_id, TenderJudge.user_id == data.user_id).first():
        raise HTTPException(status_code=400, detail="评委已存在")
    judge = TenderJudge(section_id=section_id, user_id=data.user_id)
    db.add(judge)
    db.commit()
    return {"id": judge.id}


@router.post("/sections/{section_id}/evaluation/scores")
def submit_scores(
    section_id: int, data: ScoreIn, db: Session = Depends(get_db), user: User = Depends(require_roles("judge", "admin", "operator"))
):
    if not db.query(TenderJudge).filter(TenderJudge.section_id == section_id, TenderJudge.user_id == user.id).first():
        raise HTTPException(status_code=403, detail="您不是该标段评委")
    bid = db.get(BidDocument, data.bid_document_id)
    if not bid or bid.section_id != section_id:
        raise HTTPException(status_code=404, detail="投标文件不存在")
    existing = db.query(BidScore).filter(
        BidScore.section_id == section_id, BidScore.bid_document_id == bid.id, BidScore.judge_id == user.id
    ).first()
    if existing:
        existing.scores_json = json.dumps(data.scores)
        db.commit()
        return {"id": existing.id, "updated": True}
    score = BidScore(section_id=section_id, bid_document_id=bid.id, judge_id=user.id, scores_json=json.dumps(data.scores))
    db.add(score)
    db.commit()
    db.refresh(score)
    return {"id": score.id, "updated": False}


@router.post("/sections/{section_id}/evaluation/open")
def open_evaluation(section_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    rule = _get_rule(db, section_id)
    bids = db.query(BidDocument).filter(BidDocument.section_id == section_id).all()
    qualified = [b for b in bids if json.loads(b.compliance_json or "{}").get("passed")]
    if not qualified:
        raise HTTPException(status_code=400, detail="无合规通过的投标，无法开标")

    prices = [float(b.price) for b in qualified]
    abnormal = detect_abnormal_low(rule, prices) if section.method == "lowest_price" else []

    if section.method == "lowest_price":
        ranked = sorted(
            [{"bid_document_id": b.id, "company": b.company, "price": float(b.price), "price_score": 0, "total": 0.0} for b in qualified],
            key=lambda r: r["price"],
        )
        winner_bid = qualified[min(range(len(qualified)), key=lambda i: float(qualified[i].price))]
    else:
        ranked = evaluate_section(db, section_id, rule, bids)
        winner_bid = db.get(BidDocument, ranked[0]["bid_document_id"])

    winner = db.query(Winner).filter(Winner.section_id == section_id).first()
    if not winner:
        winner = Winner(
            section_id=section_id,
            bid_document_id=winner_bid.id,
            bidder_id=winner_bid.bidder_id,
            win_price=float(winner_bid.price),
            status="pending",
        )
        db.add(winner)
        db.commit()
        db.refresh(winner)
    start_publicity(db, section, winner)

    transition(db, section, "awarded", user.id, "开标并产生中标候选人")
    add_audit(db, user.id, "OPEN_EVALUATION", f"标段 {section.code} 开标")
    return {
        "ranked": ranked,
        "abnormal_prices": abnormal,
        "winner_bid_id": winner_bid.id,
        "winner_company": winner_bid.company,
        "winner_price": float(winner_bid.price),
        "publish_end": winner.publish_end,
    }
