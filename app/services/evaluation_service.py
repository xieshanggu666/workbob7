"""评标引擎：综合评分法 / 最低价法。

- 综合评分法：总分 = 价格分 + 技术商务主观分
  价格分依据最低有效报价与该投标报价的比值计算
  主观分 = 评委对评分项打分的均值 × 权重
- 最低价法：合规通过中报价最低者中标，低于平均价阈值判异常低价
"""

import json
from datetime import datetime, timedelta
from statistics import mean

from app.models.bid import BidDocument, Winner
from app.models.evaluation import AbnormalPriceClarification, BidScore, EvaluationItem, EvaluationRule
from app.services.escrow_service import return_bid_deposit
from app.services.status_service import start_publicity, transition


def compute_price_score(rule: EvaluationRule, bid_price: float, min_price: float) -> float:
    """综合评分法下的价格分。"""
    if min_price <= 0 or bid_price <= 0:
        return 0.0
    price_score = (min_price / bid_price) * float(rule.price_full_score)
    return round(price_score, 2)


def detect_abnormal_low(rule: EvaluationRule, prices: list[float]) -> list[float]:
    """检测异常低价：报价低于平均价 * 阈值的报价。"""
    avg = mean(prices)
    threshold = avg * float(rule.abnormal_price_ratio)
    return [p for p in prices if p < threshold]


def _aggregate_item_score(item: EvaluationItem, judge_scores: list[float], drop_extreme: bool) -> float:
    """聚合评委打分，取均值并加权。"""
    if not judge_scores:
        return 0.0
    if drop_extreme and len(judge_scores) >= 3:
        valid = sorted(judge_scores)[1:-1]
    else:
        valid = judge_scores
    avg = mean(valid)
    return round(avg * float(item.weight), 4)


def _compliance_passed(bid: BidDocument) -> bool:
    try:
        data = json.loads(bid.compliance_json or "{}")
        return bool(data.get("passed", False))
    except (TypeError, ValueError, AttributeError):
        return False


ACTIVE_CLARIFICATION_STATUSES = {"pending", "responded"}
CLARIFICATION_DEADLINE_HOURS = 24


def clarification_dict(item: AbnormalPriceClarification) -> dict:
    return {
        "id": item.id,
        "section_id": item.section_id,
        "bid_document_id": item.bid_document_id,
        "bidder_id": item.bidder_id,
        "suspected_price": float(item.suspected_price),
        "threshold_price": float(item.threshold_price),
        "status": item.status,
        "request_remark": item.request_remark,
        "response_content": item.response_content,
        "response_at": item.response_at,
        "review_remark": item.review_remark,
        "reviewed_by": item.reviewed_by,
        "reviewed_at": item.reviewed_at,
        "deadline": item.deadline,
        "created_at": item.created_at,
    }


def list_section_clarifications(db, section_id: int) -> list[AbnormalPriceClarification]:
    return (
        db.query(AbnormalPriceClarification)
        .filter(AbnormalPriceClarification.section_id == section_id)
        .order_by(AbnormalPriceClarification.created_at.asc())
        .all()
    )


def _rank_lowest_candidates(bids: list[BidDocument]) -> list[dict]:
    ranked = [
        {
            "bid_document_id": bid.id,
            "company": bid.company,
            "price": float(bid.price),
            "price_score": 0,
            "total": 0.0,
            "status": bid.status,
        }
        for bid in bids
    ]
    return sorted(ranked, key=lambda r: r["price"])


def _find_abnormal_low_bids(rule: EvaluationRule, bids: list[BidDocument]) -> list[tuple[BidDocument, float]]:
    """返回低于平均价阈值的投标及对应阈值。"""
    if not bids:
        return []
    avg = mean(float(b.price) for b in bids)
    threshold = avg * float(rule.abnormal_price_ratio)
    return [(bid, threshold) for bid in bids if float(bid.price) < threshold]


def expire_pending_clarifications(db, section_id: int) -> list[AbnormalPriceClarification]:
    """澄清期限届满仍未说明的，视为不能合理说明并排除。"""
    now = datetime.utcnow()
    expired = (
        db.query(AbnormalPriceClarification)
        .filter(
            AbnormalPriceClarification.section_id == section_id,
            AbnormalPriceClarification.status == "pending",
            AbnormalPriceClarification.deadline < now,
        )
        .all()
    )
    for item in expired:
        item.status = "excluded"
        item.review_remark = "澄清期限届满未作出说明"
        item.reviewed_at = now
        bid = db.get(BidDocument, item.bid_document_id)
        if bid:
            bid.status = "abn_excluded"
        return_bid_deposit(db, section_id, item.bid_document_id, "异常低价未在期限内澄清，保证金退还")
    if expired:
        db.commit()
    return expired


def prepare_lowest_price_evaluation(db, section, rule: EvaluationRule, bids: list[BidDocument]) -> dict:
    """发起最低价法澄清；待澄清/已排除报价均不进入排名和定标。"""
    expire_pending_clarifications(db, section.id)
    clarifications = list_section_clarifications(db, section.id)
    records_by_bid = {item.bid_document_id: item for item in clarifications}
    active_by_bid = {bid_id: item for bid_id, item in records_by_bid.items() if item.status in ACTIVE_CLARIFICATION_STATUSES}

    qualified = []
    for bid in bids:
        if not _compliance_passed(bid) or bid.status == "abn_excluded" or bid.id in active_by_bid:
            continue
        record = records_by_bid.get(bid.id)
        if record is None or record.status == "accepted":
            qualified.append(bid)

    flagged = _find_abnormal_low_bids(rule, qualified)
    now = datetime.utcnow()
    created = False
    for bid, threshold in flagged:
        if bid.id in records_by_bid:
            continue
        item = AbnormalPriceClarification(
            section_id=section.id,
            bid_document_id=bid.id,
            bidder_id=bid.bidder_id,
            suspected_price=bid.price,
            threshold_price=round(threshold, 2),
            status="pending",
            request_remark="报价低于平均价阈值，需书面说明报价合理性",
            deadline=now + timedelta(hours=CLARIFICATION_DEADLINE_HOURS),
        )
        db.add(item)
        bid.status = "clarifying"
        created = True
    if created:
        db.commit()

    clarifications = list_section_clarifications(db, section.id)
    active = [item for item in clarifications if item.status in ACTIVE_CLARIFICATION_STATUSES]
    accepted_ids = {item.bid_document_id for item in clarifications if item.status == "accepted"}
    excluded_ids = {item.bid_document_id for item in clarifications if item.status == "excluded"}
    clarification_ids = {item.bid_document_id for item in clarifications}
    candidates = [
        bid
        for bid in bids
        if _compliance_passed(bid)
        and bid.id not in {item.bid_document_id for item in active}
        and bid.id not in excluded_ids
        and (bid.id in accepted_ids or bid.id not in clarification_ids)
    ]
    return {
        "ranked": _rank_lowest_candidates(candidates),
        "clarifications": [clarification_dict(item) for item in clarifications],
        "active_clarifications": [clarification_dict(item) for item in active],
        "abnormal_prices": [float(item.suspected_price) for item in clarifications],
        "active_abnormal_prices": [float(item.suspected_price) for item in active],
        "needs_clarification": bool(active),
        "section_status": section.status,
        "candidate_bids": candidates,
    }


def _cancel_pending_winners(db, section_id: int) -> None:
    winners = db.query(Winner).filter(Winner.section_id == section_id, Winner.status == "pending").all()
    for winner in winners:
        winner.status = "cancelled"
    if winners:
        db.commit()


def finalize_lowest_price_evaluation(db, section, user, bids: list[BidDocument] | None = None) -> dict:
    """全部异常低价处理完成后才允许最低价排名定标和公示。"""
    if bids is None:
        bids = db.query(BidDocument).filter(BidDocument.section_id == section.id).all()
    expire_pending_clarifications(db, section.id)
    clarifications = list_section_clarifications(db, section.id)
    active = [item for item in clarifications if item.status in ACTIVE_CLARIFICATION_STATUSES]
    if active:
        return {
            "ranked": [],
            "clarifications": [clarification_dict(item) for item in clarifications],
            "active_clarifications": [clarification_dict(item) for item in active],
            "abnormal_prices": [float(item.suspected_price) for item in active],
            "active_abnormal_prices": [float(item.suspected_price) for item in active],
            "needs_clarification": True,
            "section_status": section.status,
            "winner_bid_id": None,
            "winner_company": None,
            "winner_price": None,
            "publish_end": None,
            "awarded": False,
        }

    accepted_ids = {item.bid_document_id for item in clarifications if item.status == "accepted"}
    excluded_ids = {item.bid_document_id for item in clarifications if item.status == "excluded"}
    candidates = [
        bid
        for bid in bids
        if _compliance_passed(bid)
        and bid.id not in excluded_ids
        and (bid.id in accepted_ids or bid.id not in {item.bid_document_id for item in clarifications})
    ]
    ranked = _rank_lowest_candidates(candidates)
    if not candidates:
        _cancel_pending_winners(db, section.id)
        for bid in bids:
            return_bid_deposit(db, section.id, bid.id, "有效投标不足导致流标，保证金退还")
        transition(db, section, "failed", user.id, "异常低价排除后无有效投标，标段流标")
        return {
            "ranked": ranked,
            "clarifications": [clarification_dict(item) for item in clarifications],
            "active_clarifications": [],
            "abnormal_prices": [],
            "needs_clarification": False,
            "section_status": section.status,
            "winner_bid_id": None,
            "winner_company": None,
            "winner_price": None,
            "publish_end": None,
            "awarded": False,
            "failed": True,
            "message": "异常低价排除后无有效投标，已流转为流标",
        }

    winner_bid = min(candidates, key=lambda bid: float(bid.price))
    _cancel_pending_winners(db, section.id)
    winner = Winner(
        section_id=section.id,
        bid_document_id=winner_bid.id,
        bidder_id=winner_bid.bidder_id,
        win_price=float(winner_bid.price),
        status="pending",
    )
    db.add(winner)
    db.commit()
    db.refresh(winner)

    winner_bid.status = "won"
    for bid in candidates:
        if bid.id != winner_bid.id:
            bid.status = "lost"
            return_bid_deposit(db, section.id, bid.id, "未中标保证金退还")
    db.commit()

    start_publicity(db, section, winner)
    transition(db, section, "awarded", user.id, "异常低价澄清完成，开标并产生中标候选人")
    return {
        "ranked": _rank_lowest_candidates(candidates),
        "clarifications": [clarification_dict(item) for item in clarifications],
        "active_clarifications": [],
        "abnormal_prices": [],
        "needs_clarification": False,
        "section_status": section.status,
        "winner_id": winner.id,
        "winner_bid_id": winner_bid.id,
        "winner_company": winner_bid.company,
        "winner_price": float(winner_bid.price),
        "publish_end": winner.publish_end,
        "awarded": True,
    }


def submit_clarification(db, item: AbnormalPriceClarification, content: str) -> AbnormalPriceClarification:
    """投标人提交异常低价澄清说明。"""
    if item.status != "pending":
        raise ValueError("该澄清已处理，不能重复提交")
    if item.deadline < datetime.utcnow():
        raise ValueError("澄清期限已届满，不能提交说明")
    item.response_content = content
    item.status = "responded"
    item.response_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return item


def review_clarification(db, section, item: AbnormalPriceClarification, action: str, reviewer, remark: str = "") -> dict:
    """评审澄清结果；accepted 恢复有效性，excluded 永久排除出定标链路。"""
    if item.status not in ACTIVE_CLARIFICATION_STATUSES:
        raise ValueError("该澄清已处理")
    if action not in {"accepted", "excluded"}:
        raise ValueError("澄清处理结果无效")

    bid = db.get(BidDocument, item.bid_document_id)
    item.review_remark = remark
    item.reviewed_by = reviewer.id
    item.reviewed_at = datetime.utcnow()
    if action == "accepted":
        item.status = "accepted"
        if bid:
            bid.status = "qualified"
    else:
        item.status = "excluded"
        if bid:
            bid.status = "abn_excluded"
        return_bid_deposit(db, section.id, item.bid_document_id, "异常低价澄清不成立，保证金退还")
    db.commit()
    return finalize_lowest_price_evaluation(db, section, reviewer)


def evaluate_section(db, section_id: int, rule: EvaluationRule, bids: list[BidDocument]) -> list[dict]:
    """对合规通过的投标进行综合评分，返回按总分排序的排名列表。"""
    items = (
        db.query(EvaluationItem)
        .filter(EvaluationItem.section_id == section_id)
        .all()
    )
    valid_prices = [float(b.price) for b in bids if _compliance_passed(b)]
    if not valid_prices:
        return []
    min_price = min(valid_prices)

    results: list[dict] = []
    for bid in bids:
        if not _compliance_passed(bid):
            continue
        total = compute_price_score(rule, float(bid.price), min_price)
        breakdown = {"price": compute_price_score(rule, float(bid.price), min_price)}
        for item in items:
            scores = []
            for score in db.query(BidScore).filter(
                BidScore.bid_document_id == bid.id, BidScore.section_id == section_id
            ):
                item_map = json.loads(score.scores_json or "{}")
                if str(item.id) in item_map:
                    scores.append(float(item_map[str(item.id)]))
            item_score = _aggregate_item_score(item, scores, bool(rule.drop_highest_lowest))
            breakdown[f"item_{item.id}"] = item_score
            total += item_score
        results.append(
            {
                "bid_document_id": bid.id,
                "company": bid.company,
                "price": float(bid.price),
                "price_score": breakdown["price"],
                "total": round(total, 2),
            }
        )
    results.sort(key=lambda r: r["total"], reverse=True)
    return results
