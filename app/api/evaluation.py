import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import (
    AbnormalPriceClarification,
    BidDocument,
    BidScore,
    EvaluationItem,
    EvaluationRule,
    TenderJudge,
    TenderSection,
    User,
    Winner,
)
from app.schemas import ClarificationResponseIn, ClarificationReviewIn, ItemIn, JudgeIn, RuleIn, ScoreIn
from app.services.audit_service import add_audit
from app.services.escrow_service import return_bid_deposit
from app.services.evaluation_service import (
    clarification_dict,
    evaluate_section,
    finalize_lowest_price_evaluation,
    list_section_clarifications,
    prepare_lowest_price_evaluation,
    review_clarification,
    submit_clarification,
    expire_pending_clarifications,
)
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


def _compliance_passed(bid: BidDocument) -> bool:
    try:
        return bool(json.loads(bid.compliance_json or "{}").get("passed"))
    except (TypeError, ValueError):
        return False


@router.get("/sections/{section_id}/evaluation/clarifications")
def list_clarifications(section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    return [clarification_dict(item) for item in list_section_clarifications(db, section_id)]


@router.post("/clarifications/{clarification_id}/response")
def respond_clarification(
    clarification_id: int,
    data: ClarificationResponseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("bidder")),
):
    item = db.get(AbnormalPriceClarification, clarification_id)
    if not item:
        raise HTTPException(status_code=404, detail="澄清记录不存在")
    if item.bidder_id != user.id:
        raise HTTPException(status_code=403, detail="只能提交本企业投标的澄清说明")
    expire_pending_clarifications(db, item.section_id)
    db.refresh(item)
    try:
        item = submit_clarification(db, item, data.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_audit(db, user.id, "ABNORMAL_PRICE_RESPONSE", f"投标 {item.bid_document_id} 提交异常低价澄清")
    return clarification_dict(item)


@router.post("/clarifications/{clarification_id}/review")
def review_abnormal_clarification(
    clarification_id: int,
    data: ClarificationReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "operator")),
):
    item = db.get(AbnormalPriceClarification, clarification_id)
    if not item:
        raise HTTPException(status_code=404, detail="澄清记录不存在")
    section = db.get(TenderSection, item.section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    expire_pending_clarifications(db, section.id)
    db.refresh(item)
    if item.status == "excluded":
        bids = db.query(BidDocument).filter(BidDocument.section_id == section.id).all()
        result = finalize_lowest_price_evaluation(db, section, user, bids)
        if result.get("failed"):
            add_audit(db, user.id, "OPEN_EVALUATION", f"标段 {section.code} 异常低价逾期排除后流标")
        return result
    try:
        result = review_clarification(db, section, item, data.action, user, data.remark)
        if result.get("needs_clarification"):
            rule = _get_rule(db, section.id)
            bids = db.query(BidDocument).filter(BidDocument.section_id == section.id).all()
            result = prepare_lowest_price_evaluation(db, section, rule, bids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_audit(
        db,
        user.id,
        "ABNORMAL_PRICE_REVIEW",
        f"投标 {item.bid_document_id} 异常低价澄清处理为 {data.action}",
    )
    return result


@router.post("/sections/{section_id}/evaluation/open")
def open_evaluation(section_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    if section.status == "awarded":
        raise HTTPException(status_code=400, detail="标段已定标，不能重复开标")

    rule = _get_rule(db, section_id)
    bids = db.query(BidDocument).filter(BidDocument.section_id == section_id).all()
    qualified = [b for b in bids if _compliance_passed(b) and b.status != "abn_excluded"]
    if not qualified:
        raise HTTPException(status_code=400, detail="无合规通过的投标，无法开标")
    if section.status not in {"bidding", "evaluating"}:
        raise HTTPException(status_code=400, detail="当前标段状态不能开标")

    if section.status == "bidding":
        if not transition(db, section, "evaluating", user.id, "开标进入评标"):
            raise HTTPException(status_code=400, detail="当前标段状态不能开标")

    if section.method == "lowest_price":
        result = prepare_lowest_price_evaluation(db, section, rule, bids)
        if result["needs_clarification"]:
            add_audit(db, user.id, "OPEN_EVALUATION", f"标段 {section.code} 开标，存在异常低价待澄清")
            return result
        result = finalize_lowest_price_evaluation(db, section, user, bids)
        if result.get("failed"):
            add_audit(db, user.id, "OPEN_EVALUATION", f"标段 {section.code} 异常低价排除后流标")
            return result
        add_audit(db, user.id, "OPEN_EVALUATION", f"标段 {section.code} 开标")
        return result

    ranked = evaluate_section(db, section_id, rule, bids)
    if not ranked:
        raise HTTPException(status_code=400, detail="无有效评分结果，无法定标")
    winner_bid = db.get(BidDocument, ranked[0]["bid_document_id"])
    existing = db.query(Winner).filter(Winner.section_id == section_id, Winner.status != "cancelled").first()
    if existing:
        raise HTTPException(status_code=400, detail="标段已存在中标记录")

    winner = Winner(
        section_id=section_id,
        bid_document_id=winner_bid.id,
        bidder_id=winner_bid.bidder_id,
        win_price=float(winner_bid.price),
        status="pending",
    )
    db.add(winner)
    winner_bid.status = "won"
    for bid in qualified:
        if bid.id != winner_bid.id:
            bid.status = "lost"
            return_bid_deposit(db, section_id, bid.id, "未中标保证金退还")
    db.commit()
    db.refresh(winner)
    start_publicity(db, section, winner)

    if not transition(db, section, "awarded", user.id, "开标并产生中标候选人"):
        raise HTTPException(status_code=400, detail="标段状态流转失败")
    add_audit(db, user.id, "OPEN_EVALUATION", f"标段 {section.code} 开标")
    return {
        "ranked": ranked,
        "abnormal_prices": [],
        "clarifications": [],
        "active_clarifications": [],
        "needs_clarification": False,
        "winner_id": winner.id,
        "winner_bid_id": winner_bid.id,
        "winner_company": winner_bid.company,
        "winner_price": float(winner_bid.price),
        "publish_end": winner.publish_end,
        "awarded": True,
    }
