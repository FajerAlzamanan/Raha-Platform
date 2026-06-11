"""
app/auth_utils.py  –  JWT creation/verification + bcrypt helpers.
"""

import os, re
from typing import Optional
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "change_this_secret")
ALGORITHM  = "HS256"
EXPIRE_HOURS = 8

bearer_scheme = HTTPBearer()

# ── Password ───────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def validate_password(password: str) -> Optional[str]:
    """Return error message or None if valid."""
    if not password or len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number."
    return None

# ── JWT ────────────────────────────────────────────────────────────────────────

def create_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS)
    return jwt.encode({"id": user_id, "role": role, "exp": expire}, SECRET_KEY, ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

# ── FastAPI dependencies ───────────────────────────────────────────────────────

def auth_required(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    payload = decode_token(credentials.credentials)
    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    from app.db_helpers import get_user_by_id
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if user.get("role") == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account has been suspended by the administrator.")

    return {"id": user["id"], "role": user["role"]}

def admin_only(user: dict = Depends(auth_required)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
