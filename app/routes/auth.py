"""
app/routes/auth.py  –  /api/auth/signup  and  /api/auth/login
Uses your team's db_helpers: create_user(), get_user(), log_event()
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.db_helpers import create_user, get_user, log_event
from app.auth_utils import hash_password, verify_password, validate_password, create_token

router = APIRouter()


class SignupRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    title: str | None = None
    gender: str | None = None
    institution: str | None = None       # stored in professional_role field
    professional_role: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup", status_code=201)
def signup(body: SignupRequest):
    err = validate_password(body.password)
    if err:
        raise HTTPException(400, err)

    if get_user(body.email):
        raise HTTPException(400, "Email already registered")

    pw_hash = hash_password(body.password)
    create_user(
        full_name=body.full_name,
        email=body.email,
        password_hash=pw_hash,
        role="researcher",
        gender=body.gender,
        title=body.title,
        professional_role=body.professional_role,
    )
    return {"message": "Account created"}


@router.post("/login")
def login(body: LoginRequest):
    user = get_user(body.email)
    if not user:
        raise HTTPException(400, "Invalid credentials")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(400, "Invalid credentials")

    log_event(user["id"], "login", f"{user['email']} logged in")

    token = create_token(user["id"], user["role"])
    return {
        "token": token,
        "role": user["role"],
        "full_name": user["full_name"],
    }
