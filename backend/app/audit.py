"""Audit trail — every AI action and every human decision is recorded."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditLog, User


def log_action(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    entity_type: str = "",
    entity_id: str | int = "",
    details: dict | None = None,
    ip: str = "",
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
        ip_address=ip,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
