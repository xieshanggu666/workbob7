from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.models.bid import Winner
from app.services.status_service import confirm_expired_publicity

router = APIRouter(prefix="/api", tags=["winner"])


@router.get("/winners/pending")
def pending_winners(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    winners = db.query(Winner).filter(Winner.status == "pending").all()
    return [
        {
            "id": w.id,
            "section_id": w.section_id,
            "bid_document_id": w.bid_document_id,
            "win_price": float(w.win_price),
            "publish_start": w.publish_start,
            "publish_end": w.publish_end,
            "status": w.status,
        }
        for w in winners
    ]


@router.post("/winners/{winner_id}/confirm")
def confirm_winner(winner_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    winner = db.get(Winner, winner_id)
    if not winner:
        return {"ok": False, "message": "中标记录不存在"}
    ok = confirm_expired_publicity(db, winner)
    if not ok:
        return {"ok": False, "message": "公示期尚未结束，暂不能确认中标"}
    return {"ok": True, "status": winner.status}
