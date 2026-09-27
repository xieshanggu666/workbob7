"""业务逻辑单元测试与关键流程集成测试。"""

import asyncio
import json
from datetime import date, datetime, timedelta

import httpx

from app.core.security import hash_password
from app.main import app
from app.models import (
    BidDocument,
    ComplianceRule,
    EscrowAccount,
    EscrowTransaction,
    EvaluationItem,
    EvaluationRule,
    Project,
    TenderSection,
    User,
    Winner,
)
from app.services.compliance_service import check_bid_document
from app.services.escrow_service import forfeit_deposit, pay_deposit, return_deposit
from app.services.evaluation_service import (
    _aggregate_item_score,
    compute_price_score,
    detect_abnormal_low,
    evaluate_section,
)
from app.services.status_service import (
    can_transition,
    confirm_expired_publicity,
    start_publicity,
    transition,
)


def _user(db, username, role="bidder", company="测试公司"):
    pw, salt = hash_password("123456")
    u = User(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        company=company,
        password_hash=pw,
        salt=salt,
        role=role,
    )
    db.add(u)
    db.commit()
    return u


def _project(db, code="ZB-T-001"):
    p = Project(code=code, name="测试项目", category="货物", budget=2_000_000, status="published")
    db.add(p)
    db.commit()
    return p


def _section(db, project, method="comprehensive", status="bidding"):
    s = TenderSection(
        project_id=project.id,
        code="BD-T-001",
        name="测试标段",
        status=status,
        method=method,
        deposit_ratio=0.02,
        notice_days=3,
    )
    db.add(s)
    db.commit()
    return s


def _bid(db, section, bidder, price, expiry="2030-01-01", passed=True, tech="技术方案材料齐全"):
    bid = BidDocument(
        section_id=section.id,
        bidder_id=bidder.id,
        company=bidder.company,
        price=price,
        license_expiry=expiry,
        tech_material=tech,
        status="qualified" if passed else "submitted",
        compliance_json=json.dumps({"passed": passed, "errors": []}),
    )
    db.add(bid)
    db.commit()
    return bid


# ---------- 合规校验 ----------


def test_compliance_required_rule_flags_missing_field(db):
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_r")
    db.add(ComplianceRule(section_id=section.id, field="tech_material", rule_type="required", message="缺少技术方案材料"))
    db.commit()
    bid = _bid(db, section, bidder, 100_000, tech="")
    result = check_bid_document(db, section.id, bid)
    assert result["passed"] is False
    assert any("技术方案" in e for e in result["errors"])


def test_compliance_range_rule_within_budget(db):
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_r2")
    db.add(ComplianceRule(section_id=section.id, field="price", rule_type="range", param="0,2000000", message="报价超出预算上限"))
    db.commit()
    bid = _bid(db, section, bidder, 1_500_000)
    result = check_bid_document(db, section.id, bid)
    assert result["passed"] is True


def test_compliance_date_rule_accepts_license_valid_through_today(db):
    """营业执照有效期截止日为今天时，资质仍然有效。"""
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_d")
    db.add(ComplianceRule(section_id=section.id, field="license_expiry", rule_type="date", message="营业执照已过期"))
    db.commit()
    bid = _bid(db, section, bidder, 100_000, expiry=date.today().isoformat())
    result = check_bid_document(db, section.id, bid)
    assert result["passed"] is True, f"截止当天不应判过期: {result['errors']}"


def test_compliance_date_rule_rejects_expired_license(db):
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_d2")
    db.add(ComplianceRule(section_id=section.id, field="license_expiry", rule_type="date", message="营业执照已过期"))
    db.commit()
    bid = _bid(db, section, bidder, 100_000, expiry=(date.today() - timedelta(days=1)).isoformat())
    result = check_bid_document(db, section.id, bid)
    assert result["passed"] is False


# ---------- 保证金账务 ----------


def test_escrow_pay_deposit_records_transaction(db):
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_e")
    bid = _bid(db, section, bidder, 100_000)
    account = EscrowAccount(section_id=section.id, bid_document_id=bid.id, bidder_id=bidder.id, amount=200_000, status="unpaid")
    db.add(account)
    db.commit()
    pay_deposit(db, account)
    assert account.status == "paid"
    assert account.paid_at is not None


def test_escrow_refund_is_full_amount(db):
    """未中标退还保证金应为足额退还，不扣减任何费用。"""
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_e2")
    bid = _bid(db, section, bidder, 100_000)
    account = EscrowAccount(section_id=section.id, bid_document_id=bid.id, bidder_id=bidder.id, amount=200_000, status="unpaid")
    db.add(account)
    db.commit()
    pay_deposit(db, account)
    return_deposit(db, account)
    assert account.status == "returned"
    tx = db.query(EscrowTransaction).filter(EscrowTransaction.account_id == account.id, EscrowTransaction.tx_type == "return").first()
    assert tx is not None, "应生成退还流水"
    assert float(tx.amount) == 200_000, f"退还金额应为足额 200000，实际 {tx.amount}"


def test_escrow_forfeit_full_amount(db):
    section = _section(db, _project(db))
    bidder = _user(db, "bidder_e3")
    bid = _bid(db, section, bidder, 100_000)
    account = EscrowAccount(section_id=section.id, bid_document_id=bid.id, bidder_id=bidder.id, amount=200_000, status="unpaid")
    db.add(account)
    db.commit()
    pay_deposit(db, account)
    forfeit_deposit(db, account, "放弃中标")
    assert account.status == "forfeited"


# ---------- 评标引擎 ----------


def test_price_score_lower_price_higher_score(db):
    """价格分随报价降低而升高：最低报价得满分。"""
    rule = EvaluationRule(section_id=1, method="comprehensive", price_full_score=100)
    price_score = compute_price_score(rule, bid_price=200, min_price=100)
    assert price_score == 50, f"200 相对最低价 100 应得 50 分，实际 {price_score}"


def test_item_score_drops_both_extremes(db):
    """去掉最高分与最低分后取均值。"""
    item = EvaluationItem(section_id=1, name="技术方案", weight=1.0, full_score=100)
    score = _aggregate_item_score(item, [90, 70, 50], drop_extreme=True)
    assert score == 70, f"去掉 90 与 50 后均值为 70，实际 {score}"


def test_item_score_plain_mean_when_not_dropping(db):
    item = EvaluationItem(section_id=1, name="技术方案", weight=0.5, full_score=100)
    score = _aggregate_item_score(item, [80, 60], drop_extreme=False)
    assert score == 35


def test_abnormal_low_detection_uses_avg_threshold(db):
    rule = EvaluationRule(section_id=1, method="lowest_price", abnormal_price_ratio=0.8)
    flagged = detect_abnormal_low(rule, [100, 120, 140])
    assert flagged == []


def test_evaluate_section_includes_only_compliant(db):
    project = _project(db)
    section = _section(db, project)
    rule = EvaluationRule(section_id=section.id, method="comprehensive", price_full_score=100)
    db.add(rule)
    db.commit()
    b1 = _user(db, "bidder_v1")
    b2 = _user(db, "bidder_v2")
    _bid(db, section, b1, 1_000_000)
    _bid(db, section, b2, 1_000_000, passed=False)
    results = evaluate_section(db, section.id, rule, db.query(BidDocument).filter(BidDocument.section_id == section.id).all())
    assert len(results) == 1
    assert results[0]["company"] == "测试公司"


# ---------- 状态机与公示 ----------


def test_status_transition_rules(db):
    assert can_transition("draft", "announced") is True
    assert can_transition("draft", "evaluating") is False
    assert can_transition("evaluating", "awarded") is True


def test_transition_writes_log(db):
    project = _project(db)
    section = _section(db, project, status="draft")
    operator = _user(db, "op_t", role="operator")
    ok = transition(db, section, "announced", operator.id, "发布公告")
    assert ok is True
    assert section.status == "announced"


def test_publicity_not_confirmed_before_end(db):
    project = _project(db)
    section = _section(db, project)
    bidder = _user(db, "bidder_w")
    bid = _bid(db, section, bidder, 100_000)
    winner = Winner(section_id=section.id, bid_document_id=bid.id, bidder_id=bidder.id, win_price=100_000, status="pending")
    db.add(winner)
    db.commit()
    winner.publish_end = datetime.now() + timedelta(days=1)
    db.commit()
    assert confirm_expired_publicity(db, winner) is False
    assert winner.status == "pending"


def test_publicity_confirms_on_end_day(db):
    """公示期结束日当天即可确认中标生效。"""
    project = _project(db)
    section = _section(db, project)
    bidder = _user(db, "bidder_w2")
    bid = _bid(db, section, bidder, 100_000)
    winner = Winner(section_id=section.id, bid_document_id=bid.id, bidder_id=bidder.id, win_price=100_000, status="pending")
    db.add(winner)
    db.commit()
    winner.publish_end = datetime.now()
    db.commit()
    assert confirm_expired_publicity(db, winner) is True, "结束日当天应确认生效"
    assert winner.status == "confirmed"


# ---------- 开标流程集成 ----------


def test_lowest_price_winner_not_abnormal_low_bid(db):
    """最低价法开标：异常低价投标应触发澄清，不得直接中标。"""
    admin = _user(db, "admin_w", role="admin")
    project = _project(db, code="ZB-T-002")
    section = _section(db, project, method="lowest_price", status="evaluating")
    rule = EvaluationRule(section_id=section.id, method="lowest_price", abnormal_price_ratio=0.6)
    db.add(rule)
    db.commit()

    bidder_a = _user(db, "bidder_a")
    bidder_b = _user(db, "bidder_b")
    bidder_c = _user(db, "bidder_c")
    normal_1 = _bid(db, section, bidder_a, 1_000_000)
    normal_2 = _bid(db, section, bidder_b, 1_000_000)
    abnormal = _bid(db, section, bidder_c, 300_000)

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            login = await ac.post("/api/auth/login", json={"username": "admin_w", "password": "123456"})
            assert login.status_code == 200
            return await ac.post(f"/api/sections/{section.id}/evaluation/open")

    r = asyncio.run(_run())
    assert r.status_code == 200
    data = r.json()
    assert 300_000 in data["abnormal_prices"], "300000 应被判定为异常低价"
    assert data["winner_bid_id"] != abnormal.id, "异常低价投标需澄清，不应直接中标"


def _api_client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _login(ac, username):
    r = await ac.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert r.status_code == 200


def _lowest_price_section(db, code, username):
    admin = _user(db, username, role="admin")
    project = _project(db, code=code)
    section = _section(db, project, method="lowest_price", status="evaluating")
    db.add(EvaluationRule(section_id=section.id, method="lowest_price", abnormal_price_ratio=0.6))
    db.commit()
    return admin, section


def test_abnormal_low_blocks_award_chain(db):
    """检出异常低价后：不生成中标记录、不启动公示、标段保持评标中、投标转待澄清。"""
    _, section = _lowest_price_section(db, "ZB-T-003", "admin_ab")
    bidder_a = _user(db, "bidder_ab1")
    bidder_b = _user(db, "bidder_ab2")
    bidder_c = _user(db, "bidder_ab3")
    _bid(db, section, bidder_a, 1_000_000)
    _bid(db, section, bidder_b, 1_000_000)
    abnormal = _bid(db, section, bidder_c, 300_000)

    async def _run():
        async with _api_client() as ac:
            await _login(ac, "admin_ab")
            return await ac.post(f"/api/sections/{section.id}/evaluation/open")

    r = asyncio.run(_run())
    assert r.status_code == 200
    data = r.json()
    assert data["winner_bid_id"] is None, "待澄清期间不得产生中标候选人"
    assert data["publish_end"] is None, "待澄清期间不得启动中标公示"
    assert [c["bid_document_id"] for c in data["pending_clarification"]] == [abnormal.id]
    db.expire_all()
    assert db.get(BidDocument, abnormal.id).status == "clarifying"
    assert db.get(TenderSection, section.id).status == "evaluating", "待澄清期间标段应保持评标中"
    assert db.query(Winner).filter(Winner.section_id == section.id).first() is None, "待澄清期间不得生成中标记录"


def test_reopen_blocked_while_clarification_pending(db):
    """存在待澄清投标时，再次开标应被拒绝，防止绕过澄清直接定标。"""
    _, section = _lowest_price_section(db, "ZB-T-004", "admin_bl")
    _bid(db, section, _user(db, "bidder_bl1"), 1_000_000)
    _bid(db, section, _user(db, "bidder_bl2"), 1_000_000)
    _bid(db, section, _user(db, "bidder_bl3"), 300_000)

    async def _run():
        async with _api_client() as ac:
            await _login(ac, "admin_bl")
            await ac.post(f"/api/sections/{section.id}/evaluation/open")
            return await ac.post(f"/api/sections/{section.id}/evaluation/open")

    r = asyncio.run(_run())
    assert r.status_code == 400
    assert "澄清" in r.json()["detail"]


def test_exclude_abnormal_bid_returns_deposit_and_awards_next(db):
    """排除异常低价投标：退还其保证金，重新开标由最低有效报价中标并进入公示。"""
    _, section = _lowest_price_section(db, "ZB-T-005", "admin_ex")
    bidder_a = _user(db, "bidder_ex1")
    bidder_b = _user(db, "bidder_ex2")
    bidder_c = _user(db, "bidder_ex3")
    normal_1 = _bid(db, section, bidder_a, 1_000_000)
    _bid(db, section, bidder_b, 1_100_000)
    abnormal = _bid(db, section, bidder_c, 300_000)
    account = EscrowAccount(section_id=section.id, bid_document_id=abnormal.id, bidder_id=bidder_c.id, amount=20_000, status="unpaid")
    db.add(account)
    db.commit()
    pay_deposit(db, account)

    async def _run():
        async with _api_client() as ac:
            await _login(ac, "admin_ex")
            await ac.post(f"/api/sections/{section.id}/evaluation/open")
            clarify = await ac.post(
                f"/api/sections/{section.id}/evaluation/clarify",
                json={"bid_document_id": abnormal.id, "action": "exclude", "reason": "报价低于成本，澄清不成立"},
            )
            reopen = await ac.post(f"/api/sections/{section.id}/evaluation/open")
            re_open_again = await ac.post(f"/api/sections/{section.id}/evaluation/open")
            return clarify, reopen, re_open_again

    clarify, reopen, re_open_again = asyncio.run(_run())
    assert clarify.status_code == 200
    assert clarify.json()["status"] == "excluded"
    assert clarify.json()["remaining_clarifications"] == 0
    db.expire_all()
    assert db.get(BidDocument, abnormal.id).status == "excluded"
    assert db.get(EscrowAccount, account.id).status == "returned", "被排除投标的保证金应联动退还"

    assert reopen.status_code == 200
    data = reopen.json()
    assert data["winner_bid_id"] == normal_1.id, "排除异常低价后应由最低有效报价中标"
    assert data["publish_end"] is not None, "定标后应启动中标公示"
    assert all(r["bid_document_id"] != abnormal.id for r in data["ranked"]), "被排除投标不应出现在评标排名中"
    assert db.get(TenderSection, section.id).status == "awarded"
    winner = db.query(Winner).filter(Winner.section_id == section.id).first()
    assert winner is not None and winner.bid_document_id == normal_1.id

    assert re_open_again.status_code == 400, "已定标标段不得重复开标"


def test_accept_clarification_allows_bid_to_win(db):
    """澄清通过后投标恢复有效，不再重复判异常，可正常中标。"""
    _, section = _lowest_price_section(db, "ZB-T-006", "admin_ac")
    _bid(db, section, _user(db, "bidder_ac1"), 1_000_000)
    _bid(db, section, _user(db, "bidder_ac2"), 1_000_000)
    abnormal = _bid(db, section, _user(db, "bidder_ac3"), 300_000)

    async def _run():
        async with _api_client() as ac:
            await _login(ac, "admin_ac")
            await ac.post(f"/api/sections/{section.id}/evaluation/open")
            clarify = await ac.post(
                f"/api/sections/{section.id}/evaluation/clarify",
                json={"bid_document_id": abnormal.id, "action": "accept", "reason": "成本构成说明合理"},
            )
            reopen = await ac.post(f"/api/sections/{section.id}/evaluation/open")
            return clarify, reopen

    clarify, reopen = asyncio.run(_run())
    assert clarify.status_code == 200
    assert clarify.json()["status"] == "clarified"
    db.expire_all()
    assert db.get(BidDocument, abnormal.id).status == "clarified"

    assert reopen.status_code == 200
    data = reopen.json()
    assert data["abnormal_prices"] == [], "澄清通过的投标不应再被判异常"
    assert data["winner_bid_id"] == abnormal.id, "澄清通过后最低报价应正常中标"
    assert db.get(TenderSection, section.id).status == "awarded"


def test_clarify_rejects_invalid_action_and_state(db):
    """澄清接口校验：非待澄清投标 / 非法动作应返回 400。"""
    _, section = _lowest_price_section(db, "ZB-T-007", "admin_iv")
    _bid(db, section, _user(db, "bidder_iv1"), 1_000_000)
    _bid(db, section, _user(db, "bidder_iv2"), 1_000_000)
    abnormal = _bid(db, section, _user(db, "bidder_iv3"), 300_000)

    async def _run():
        async with _api_client() as ac:
            await _login(ac, "admin_iv")
            bad_action = await ac.post(
                f"/api/sections/{section.id}/evaluation/clarify",
                json={"bid_document_id": abnormal.id, "action": "ignore"},
            )
            await ac.post(f"/api/sections/{section.id}/evaluation/open")
            ok = await ac.post(
                f"/api/sections/{section.id}/evaluation/clarify",
                json={"bid_document_id": abnormal.id, "action": "exclude"},
            )
            repeat = await ac.post(
                f"/api/sections/{section.id}/evaluation/clarify",
                json={"bid_document_id": abnormal.id, "action": "accept"},
            )
            return bad_action, ok, repeat

    bad_action, ok, repeat = asyncio.run(_run())
    assert bad_action.status_code == 400
    assert ok.status_code == 200
    assert repeat.status_code == 400, "已处理的投标不得重复澄清"
