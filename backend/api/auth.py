"""
Auth API - 회원가입/로그인
"""
import uuid
import hashlib
import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session as DBSession

from database import get_db, User

logger = logging.getLogger(__name__)
router = APIRouter()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, dk_hex = password_hash.split('$')
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000)
        return dk.hex() == dk_hex
    except Exception:
        return False


class RegisterRequest(BaseModel):
    username: str
    name: str
    email: str
    password: str


@router.post("/auth/register")
def register(body: RegisterRequest, db: DBSession = Depends(get_db)):
    # 중복 체크
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

    user = User(
        user_id=body.username,
        username=body.username,
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        type='U',
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"New user registered: {user.username} ({user.user_id})")
    return {"user_id": user.user_id, "username": user.username, "name": user.name}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    from datetime import datetime
    user.last_login = datetime.now()
    db.commit()

    logger.info(f"User logged in: {user.username} ({user.user_id})")
    return {"user_id": user.user_id, "username": user.username, "name": user.name, "type": user.type}
