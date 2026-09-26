from app.models.misc import AuditLog


def add_audit(db, user_id, action, detail=""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))
    db.commit()
