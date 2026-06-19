"""
Authentication routes: login, logout, verify
"""
import logging
from typing import Optional
from datetime import datetime, timedelta
from uuid import uuid4

import jwt
from fastapi import APIRouter, Header, HTTPException

from core.config import (
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
    SECRET_KEY,
    ACCESS_TOKEN_EXPIRE_SECONDS,
)
from backend.database.db import revoke_token, cleanup_revoked_tokens, is_token_revoked
from backend.database.schemas import LoginResponse, LoginRequest

logger = logging.getLogger("face-attendance.auth_routes")

auth_router = APIRouter(prefix="", tags=["auth"])


def create_access_token(data: dict, expires_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    """Tạo JWT token bằng PyJWT"""
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_seconds)
    payload.update({"exp": expire, "jti": uuid4().hex})
    
    encoded_jwt = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def verify_access_token(token: str) -> dict:
    """Xác thực JWT token bằng PyJWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        now_ts = int(datetime.utcnow().timestamp())
        cleanup_revoked_tokens(now_ts)

        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=401, detail="Token thiếu thông tin định danh")

        if is_token_revoked(str(jti)):
            raise HTTPException(status_code=401, detail="Token đã bị thu hồi")

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token đã hết hạn")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except Exception:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")


def extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Yêu cầu đăng nhập (Bearer token)")

    return authorization.split(' ', 1)[1]


def get_current_admin(authorization: Optional[str] = Header(None)) -> dict:
    token = extract_bearer_token(authorization)
    return verify_access_token(token)


@auth_router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    if request.username != ADMIN_USERNAME or request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")

    access_token = create_access_token({"sub": request.username})
    return LoginResponse(
        status="success",
        message="Đăng nhập thành công",
        data={"access_token": access_token, "token_type": "bearer"}
    )


@auth_router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Thu hồi JWT hiện tại bằng cách lưu jti vào blacklist bền vững."""
    token = extract_bearer_token(authorization)
    payload = verify_access_token(token)

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        revoke_token(str(jti), int(exp))

    return {"status": "success", "message": "Đăng xuất thành công"}


@auth_router.get("/auth/verify")
async def verify_auth(authorization: Optional[str] = Header(None)):
    """Frontend dùng endpoint này để kiểm tra token trước khi vào hệ thống."""
    payload = get_current_admin(authorization)
    return {
        "status": "success",
        "message": "Token hợp lệ",
        "data": {
            "username": payload.get("sub", "admin"),
            "expires_at": payload.get("exp")
        }
    }
