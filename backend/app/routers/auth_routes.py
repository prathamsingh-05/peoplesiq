"""Authentication and user administration."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..auth import (
    check_lockout,
    clear_failed_logins,
    client_ip,
    create_access_token,
    get_current_user,
    hash_password,
    record_failed_login,
    require_admin,
    verify_password,
)
from ..database import get_db
from ..models import User
from ..schemas import LoginRequest, PasswordChange, UserCreate

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "full_name": user.full_name, "role": user.role, "is_active": user.is_active,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    check_lockout(payload.username)
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        record_failed_login(payload.username)
        log_action(db, "auth.login_failed", details={"username": payload.username},
                   ip=client_ip(request), commit=True)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    clear_failed_logins(payload.username)
    user.last_login = datetime.now(timezone.utc)
    log_action(db, "auth.login", user=user, ip=client_ip(request))
    db.commit()
    return {"access_token": create_access_token(user), "token_type": "bearer",
            "user": _user_out(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.post("/change-password")
def change_password(payload: PasswordChange, request: Request,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    log_action(db, "auth.password_changed", user=user, ip=client_ip(request))
    db.commit()
    return {"ok": True}


@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [_user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, request: Request,
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first():
        raise HTTPException(status_code=409, detail="Username or email already exists")
    user = User(
        username=payload.username, email=payload.email, full_name=payload.full_name,
        password_hash=hash_password(payload.password), role=payload.role,
    )
    db.add(user)
    db.flush()
    log_action(db, "user.created", user=admin, entity_type="user", entity_id=user.id,
               details={"role": payload.role}, ip=client_ip(request))
    db.commit()
    return _user_out(user)


@router.post("/users/{user_id}/toggle-active")
def toggle_active(user_id: int, request: Request,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    user.is_active = not user.is_active
    log_action(db, "user.toggled_active", user=admin, entity_type="user",
               entity_id=user.id, details={"is_active": user.is_active},
               ip=client_ip(request))
    db.commit()
    return _user_out(user)
