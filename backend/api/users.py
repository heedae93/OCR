"""
Users Admin API - 사용자 관리 (관리자 전용)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession
from typing import Optional
from datetime import datetime

from database import get_db, User
from api.auth import hash_password

logger = logging.getLogger(__name__)
router = APIRouter()


class UserCreateRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str
    type: str = "U"  # A: Admin, U: User


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    type: Optional[str] = None


@router.get("/admin/users")
def list_users(db: DBSession = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "name": u.name,
            "email": u.email,
            "type": u.type,
            "total_jobs": u.total_jobs,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]


@router.post("/admin/users")
def create_user(body: UserCreateRequest, db: DBSession = Depends(get_db)):
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
    if body.email and db.query(User).filter_by(email=body.email).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")
    if body.type not in ("A", "U"):
        raise HTTPException(status_code=400, detail="type은 A 또는 U여야 합니다.")

    user = User(
        user_id=body.username,
        username=body.username,
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        type=body.type,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Admin created user: {user.username}")
    return {"user_id": user.user_id, "username": user.username}


@router.put("/admin/users/{user_id}")
def update_user(user_id: str, body: UserUpdateRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        if body.email != user.email and db.query(User).filter_by(email=body.email).first():
            raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")
        user.email = body.email
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.type is not None:
        if body.type not in ("A", "U"):
            raise HTTPException(status_code=400, detail="type은 A 또는 U여야 합니다.")
        user.type = body.type

    db.commit()
    logger.info(f"Admin updated user: {user.username}")
    return {"user_id": user.user_id, "username": user.username}


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: str, db: DBSession = Depends(get_db)):
    user = db.query(User).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    db.delete(user)
    db.commit()
    logger.info(f"Admin deleted user: {user_id}")
    return {"detail": "삭제되었습니다."}
