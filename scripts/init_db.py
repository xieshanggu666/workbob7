"""初始化数据库并写入演示数据。

用法：python scripts/init_db.py
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    Announcement,
    BidDocument,
    ComplianceRule,
    EscrowAccount,
    EvaluationItem,
    EvaluationRule,
    Project,
    TenderJudge,
    TenderSection,
    User,
)

PASSWORD = "123456"


def make_user(db, username, display_name, role, company=""):
    pw_hash, salt = hash_password(PASSWORD)
    user = User(
        username=username,
        display_name=display_name,
        email=f"{username}@example.com",
        company=company,
        password_hash=pw_hash,
        salt=salt,
        role=role,
    )
    db.add(user)
    return user


def init():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()

    admin = make_user(db, "admin", "系统管理员", "admin")
    operator = make_user(db, "operator", "招标经办人", "operator")
    b1 = make_user(db, "bidder1", "张明", "bidder", "云启科技")
    b2 = make_user(db, "bidder2", "李华", "bidder", "恒远建设")
    b3 = make_user(db, "bidder3", "王强", "bidder", "中科电子")
    j1 = make_user(db, "judge1", "评审专家一", "judge")
    j2 = make_user(db, "judge2", "评审专家二", "judge")
    j3 = make_user(db, "judge3", "评审专家三", "judge")
    db.commit()

    p1 = Project(
        code="ZB-2026-001", name="智慧园区安防设备采购", category="货物", budget=2_000_000,
        description="园区视频监控、门禁系统等安防设备统一采购", status="published", creator_id=admin.id,
    )
    p2 = Project(
        code="ZB-2026-002", name="信息系统运维服务", category="服务", budget=800_000,
        description="核心业务系统年度运维保障服务", status="draft", creator_id=admin.id,
    )
    db.add_all([p1, p2])
    db.commit()

    s1 = TenderSection(
        project_id=p1.id, code="BD-2026-001", name="视频监控设备采购", status="bidding",
        method="comprehensive", deposit_ratio=0.02, notice_days=3,
        qualification_req="具有安防工程企业资质证书",
        announce_at=datetime.now() - timedelta(days=2),
        bid_deadline=datetime.now() + timedelta(days=5),
    )
    s2 = TenderSection(
        project_id=p1.id, code="BD-2026-002", name="门禁系统采购", status="announced",
        method="lowest_price", deposit_ratio=0.03, notice_days=3,
        qualification_req="具有门禁系统原厂授权",
        announce_at=datetime.now() - timedelta(days=1),
    )
    s3 = TenderSection(
        project_id=p2.id, code="BD-2026-003", name="运维服务标段", status="draft",
        method="comprehensive", deposit_ratio=0.02, notice_days=5,
    )
    db.add_all([s1, s2, s3])
    db.commit()

    db.add_all(
        [
            ComplianceRule(section_id=s1.id, field="license_expiry", rule_type="date", message="营业执照已过期或临近到期"),
            ComplianceRule(section_id=s1.id, field="price", rule_type="range", param=f"0,{float(p1.budget)}", message="报价超出预算上限"),
            ComplianceRule(section_id=s2.id, field="license_expiry", rule_type="date", message="营业执照已过期或临近到期"),
            ComplianceRule(section_id=s2.id, field="tech_material", rule_type="required", message="缺少技术方案材料"),
        ]
    )

    rule1 = EvaluationRule(
        section_id=s1.id, method="comprehensive", price_weight=0.4,
        price_full_score=100, abnormal_price_ratio=0.6, drop_highest_lowest=1,
    )
    db.add(rule1)
    db.add_all(
        [
            EvaluationItem(section_id=s1.id, name="技术方案", category="tech", weight=0.4, full_score=100),
            EvaluationItem(section_id=s1.id, name="售后服务", category="business", weight=0.2, full_score=100),
            TenderJudge(section_id=s1.id, user_id=j1.id),
            TenderJudge(section_id=s1.id, user_id=j2.id),
            TenderJudge(section_id=s1.id, user_id=j3.id),
        ]
    )

    demo_bids = [
        (b1, 1_600_000, "2027-12-31", "提供全套高清监控设备与三年质保"),
        (b2, 1_800_000, "2026-12-30", "提供设备安装调试与两年质保"),
        (b3, 1_500_000, "2028-06-30", "提供全系列设备与五年质保"),
    ]
    for bidder, price, expiry, tech in demo_bids:
        bid = BidDocument(
            section_id=s1.id, bidder_id=bidder.id, company=bidder.company,
            price=price, license_expiry=expiry, tech_material=tech,
            status="qualified", compliance_json='{"passed": true, "errors": []}',
        )
        db.add(bid)
        db.flush()
        db.add(
            EscrowAccount(
                section_id=s1.id, bid_document_id=bid.id, bidder_id=bidder.id,
                amount=round(float(p1.budget) * 0.02, 2), status="unpaid",
            )
        )

    db.add(
        Announcement(
            section_id=s1.id, title="招标公告", announce_type="notice",
            content="智慧园区视频监控设备采购项目公开招标，欢迎符合资格要求的供应商参与投标。",
        )
    )
    db.commit()
    print("初始化完成：2 个项目，3 个标段，8 个用户，3 份演示投标")


if __name__ == "__main__":
    init()
