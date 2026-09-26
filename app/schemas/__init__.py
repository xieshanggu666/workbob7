from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class ProjectIn(BaseModel):
    code: str
    name: str
    category: str = "货物"
    budget: float = 0
    description: str = ""


class SectionIn(BaseModel):
    code: str
    name: str
    method: str = "comprehensive"
    deposit_ratio: float = 0.02
    qualification_req: str = ""
    notice_days: int = 3


class TransitionIn(BaseModel):
    to_status: str
    remark: str = ""


class AnnouncementIn(BaseModel):
    title: str
    content: str = ""
    announce_type: str = "notice"


class BidIn(BaseModel):
    price: float
    license_expiry: str = ""
    tech_material: str = ""


class RuleIn(BaseModel):
    method: str = "comprehensive"
    price_weight: float = 0.4
    price_full_score: float = 100
    abnormal_price_ratio: float = 0.6
    drop_highest_lowest: int = 1


class ItemIn(BaseModel):
    name: str
    category: str = "tech"
    weight: float = 0.1
    full_score: float = 10


class JudgeIn(BaseModel):
    user_id: int


class ScoreIn(BaseModel):
    bid_document_id: int
    scores: dict[str, float]
