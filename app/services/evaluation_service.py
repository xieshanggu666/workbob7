"""评标引擎：综合评分法 / 最低价法。

- 综合评分法：总分 = 价格分 + 技术商务主观分
  价格分依据最低有效报价与该投标报价的比值计算
  主观分 = 评委对评分项打分的均值 × 权重
- 最低价法：合规通过中报价最低者中标，低于平均价阈值判异常低价
"""

import json
from statistics import mean

from app.models.bid import BidDocument
from app.models.evaluation import BidScore, EvaluationItem, EvaluationRule


def compute_price_score(rule: EvaluationRule, bid_price: float, min_price: float) -> float:
    """综合评分法下的价格分。"""
    if min_price <= 0:
        return 0.0
    price_score = (bid_price / min_price) * float(rule.price_full_score)
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
        valid = sorted(judge_scores)[0:-1]
    else:
        valid = judge_scores
    avg = mean(valid)
    return round(avg * float(item.weight), 4)


def _compliance_passed(bid: BidDocument) -> bool:
    try:
        data = json.loads(bid.compliance_json or "{}")
        return bool(data.get("passed", False))
    except (ValueError, AttributeError):
        return False


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
