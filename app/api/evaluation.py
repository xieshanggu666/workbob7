import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import (
    BidDocument,
    BidScore,
    EscrowAccount,
    EvaluationItem,
    EvaluationRule,
    TenderJudge,
    TenderSection,
    User,
    Winner,
)
from app.schemas import ClarifyIn, ItemIn, JudgeIn, RuleIn, ScoreIn
from app.services.audit_service import add_audit
from app.services.escrow_service import return_deposit
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
    if section.status == "awarded":
        raise HTTPException(status_code=400, detail="该标段已定标，请勿重复开标")
    rule = _get_rule(db, section_id)
    bids = db.query(BidDocument).filter(BidDocument.section_id == section_id).all()

    # 存在待澄清的异常低价投标时，阻断定标链路，须先完成澄清/排除处理
    pending = [b for b in bids if b.status == "clarifying"]
    if pending:
        raise HTTPException(status_code=400, detail="存在待澄清的异常低价投标，请先完成澄清或排除处理")

    # 已排除的投标不进入评标排名与定标链路
    qualified = [
        b for b in bids
        if b.status != "excluded" and json.loads(b.compliance_json or "{}").get("passed")
    ]
    if not qualified:
        raise HTTPException(status_code=400, detail="无合规通过的投标，无法开标")

    if section.method == "lowest_price":
        # 澄清通过的投标已经过评审，不再重复判异常
        candidates = [b for b in qualified if b.status == "qualified"]
        prices = [float(b.price) for b in candidates]
        abnormal = detect_abnormal_low(rule, prices) if prices else []
        abnormal_bids = [b for b in candidates if float(b.price) in abnormal]

        ranked = sorted(
            [
                {
                    "bid_document_id": b.id,
                    "company": b.company,
                    "price": float(b.price),
                    "price_score": 0,
                    "total": 0.0,
                    "status": b.status,
                    "abnormal": b in abnormal_bids,
                }
                for b in qualified
            ],
            key=lambda r: r["price"],
        )

        if abnormal_bids:
            # 检出异常低价：仅标记待澄清，不生成中标记录、不启动公示、不流转标段状态
            for b in abnormal_bids:
                b.status = "clarifying"
            db.commit()
            for r in ranked:
                if r["abnormal"]:
                    r["status"] = "clarifying"
            add_audit(
                db, user.id, "ABNORMAL_LOW_PRICE",
                f"标段 {section.code} 检出异常低价 {len(abnormal_bids)} 笔（{abnormal}），转入澄清程序",
            )
            return {
                "ranked": ranked,
                "abnormal_prices": abnormal,
                "pending_clarification": [
                    {"bid_document_id": b.id, "company": b.company, "price": float(b.price)}
                    for b in abnormal_bids
                ],
                "winner_bid_id": None,
                "winner_company": None,
                "winner_price": None,
                "publish_end": None,
                "section_status": section.status,
                "message": "检测到异常低价投标，已进入澄清程序，澄清/排除处理完成前不得定标",
            }
        winner_bid = min(qualified, key=lambda b: float(b.price))
    else:
        ranked = evaluate_section(db, section_id, rule, qualified)
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
        "abnormal_prices": [],
        "pending_clarification": [],
        "winner_bid_id": winner_bid.id,
        "winner_company": winner_bid.company,
        "winner_price": float(winner_bid.price),
        "publish_end": winner.publish_end,
        "section_status": section.status,
        "message": "",
    }


@router.post("/sections/{section_id}/evaluation/clarify")
def resolve_clarification(
    section_id: int, data: ClarifyIn, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))
):
    """异常低价澄清处理：接受澄清（恢复有效）或排除投标（退还保证金）。"""
    section = db.get(TenderSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="标段不存在")
    bid = db.get(BidDocument, data.bid_document_id)
    if not bid or bid.section_id != section_id:
        raise HTTPException(status_code=404, detail="投标文件不存在")
    if bid.status != "clarifying":
        raise HTTPException(status_code=400, detail="该投标不在待澄清状态")
    if data.action not in ("accept", "exclude"):
        raise HTTPException(status_code=400, detail="无效的处理动作，仅支持 accept / exclude")

    escrow_status = None
    if data.action == "accept":
        bid.status = "clarified"
        db.commit()
        add_audit(db, user.id, "CLARIFY_ACCEPT", f"标段 {section.code} 投标 {bid.company} 澄清通过：{data.reason or '无说明'}")
    else:
        bid.status = "excluded"
        db.commit()
        # 联动保证金：被排除的投标退还其保证金
        account = db.query(EscrowAccount).filter(EscrowAccount.bid_document_id == bid.id).first()
        if account:
            return_deposit(db, account)
            escrow_status = account.status
        add_audit(db, user.id, "CLARIFY_EXCLUDE", f"标段 {section.code} 投标 {bid.company} 异常低价被排除：{data.reason or '无说明'}")

    remaining = db.query(BidDocument).filter(
        BidDocument.section_id == section_id, BidDocument.status == "clarifying"
    ).count()
    return {
        "id": bid.id,
        "status": bid.status,
        "escrow_status": escrow_status,
        "remaining_clarifications": remaining,
    }
