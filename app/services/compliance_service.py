"""标书合规性校验。

对投标文件逐条应用标段的 ComplianceRule，返回校验结果字典。
"""

from datetime import date

from app.models.bid import ComplianceRule


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def check_bid_document(db, section_id: int, bid_doc) -> dict:
    """校验投标文件，返回 {"passed": bool, "errors": [str]}。"""
    rules = (
        db.query(ComplianceRule)
        .filter(ComplianceRule.section_id == section_id, ComplianceRule.enabled == 1)
        .all()
    )
    errors: list[str] = []
    for rule in rules:
        value = getattr(bid_doc, rule.field, None)
        if rule.rule_type == "required":
            if value is None or str(value).strip() == "":
                errors.append(rule.message or f"缺少必填项 {rule.field}")
        elif rule.rule_type == "date":
            expiry = _parse_date(str(value))
            today = date.today()
            # 校验证照有效期：过期即不满足要求
            if expiry is None:
                errors.append(rule.message or f"{rule.field} 日期格式无效")
            elif expiry < today:
                errors.append(rule.message or f"{rule.field} 已过期")
        elif rule.rule_type == "range":
            try:
                num = float(value)
            except (TypeError, ValueError):
                errors.append(rule.message or f"{rule.field} 数值无效")
                continue
            try:
                low, high = rule.param.split(",")
                if num < float(low) or num > float(high):
                    errors.append(rule.message or f"{rule.field} 超出范围")
            except (ValueError, AttributeError):
                pass
    return {"passed": len(errors) == 0, "errors": errors}
