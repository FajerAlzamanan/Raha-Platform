"""
app/routes/user.py  –  /api/user/*
"""

import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from app.db_helpers import get_user_by_id, update_user, delete_user
from app.auth_utils import auth_required, hash_password, validate_password

router = APIRouter()

AVATAR_DIR = Path("app/static/uploads/avatars")
AVATAR_DIR.mkdir(parents=True, exist_ok=True)


class ProfileUpdate(BaseModel):
    full_name: str
    title: str | None = None
    gender: str | None = None
    professional_role: str | None = None
    institution: str | None = None
    new_password: str | None = None


@router.get("/me")
def get_profile(user: dict = Depends(auth_required)):
    row = get_user_by_id(user["id"])
    if not row:
        raise HTTPException(404, "User not found")
    row.pop("password_hash", None)
    return row


@router.put("/me")
def update_profile(body: ProfileUpdate, user: dict = Depends(auth_required)):
    fields = {
        "full_name":        body.full_name,
        "title":            body.title,
        "gender":           body.gender,
        "professional_role": body.professional_role,
        "institution":      body.institution,
    }

    if body.new_password:
        err = validate_password(body.new_password)
        if err:
            raise HTTPException(400, err)
        fields["password_hash"] = hash_password(body.new_password)

    update_user(user["id"], fields)
    return {"message": "Profile updated"}


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(auth_required),
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "File must be an image")

    suffix = Path(file.filename).suffix.lower() or ".jpg"
    dest = AVATAR_DIR / f"user_{user['id']}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    avatar_url = f"/static/uploads/avatars/user_{user['id']}{suffix}"
    update_user(user["id"], {"avatar_url": avatar_url})
    return {"avatar_url": avatar_url}


@router.delete("/me")
def delete_account(user: dict = Depends(auth_required)):
    delete_user(user["id"])
    return {"message": "Account deleted"}