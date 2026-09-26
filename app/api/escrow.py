from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import EscrowAccount, EscrowTransaction, User
from app.services.audit_service import add_audit
from app.services.escrow_service import forfeit_deposit, pay_deposit, return_deposit

router = APIRouter(prefix="/api", tags=["escrow"])


@router.get("/sections/{section_id}/escrow")
def list_escrow(section_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accounts = db.query(EscrowAccount).filter(EscrowAccount.section_id == section_id).all()
    return [
        {
            "id": a.id,
            "bid_document_id": a.bid_document_id,
            "bidder_id": a.bidder_id,
            "amount": float(a.amount),
            "status": a.status,
            "paid_at": a.paid_at,
            "returned_at": a.returned_at,
        }
        for a in accounts
    ]


@router.get("/escrow/{account_id}/transactions")
def list_transactions(account_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    txs = db.query(EscrowTransaction).filter(EscrowTransaction.account_id == account_id).order_by(EscrowTransaction.created_at.asc()).all()
    return [{"tx_type": t.tx_type, "amount": float(t.amount), "balance_after": float(t.balance_after), "remark": t.remark, "created_at": t.created_at} for t in txs]


@router.post("/escrow/{account_id}/pay")
def pay(account_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    account = db.get(EscrowAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="保证金账户不存在")
    if user.role != "admin" and account.bidder_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该账户")
    pay_deposit(db, account)
    add_audit(db, user.id, "ESCROW_PAY", f"缴纳保证金 {account.amount}")
    return {"id": account.id, "status": account.status}


@router.post("/escrow/{account_id}/return")
def do_return(account_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    account = db.get(EscrowAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="保证金账户不存在")
    return_deposit(db, account)
    add_audit(db, user.id, "ESCROW_RETURN", f"退还保证金 {account.amount}")
    return {"id": account.id, "status": account.status}


@router.post("/escrow/{account_id}/forfeit")
def do_forfeit(account_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "operator"))):
    account = db.get(EscrowAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="保证金账户不存在")
    forfeit_deposit(db, account, "违规投标")
    add_audit(db, user.id, "ESCROW_FORFEIT", f"没收保证金 {account.amount}")
    return {"id": account.id, "status": account.status}
