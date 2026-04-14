"""
app/routes/user.py  –  /api/user/me
Uses your team's helpers: get_user_by_id(), update_user()
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db_helpers import get_user_by_id, update_user
from app.auth_utils import auth_required, hash_password, validate_password

router = APIRouter()


class ProfileUpdate(BaseModel):
    full_name: str
    title: str | None = None
    gender: str | None = None
    professional_role: str | None = None
    new_password: str | None = None


@router.get("/me")
def get_profile(user: dict = Depends(auth_required)):
    row = get_user_by_id(user["id"])
    if not row:
        raise HTTPException(404, "User not found")
    # Remove password hash before returning
    row.pop("password_hash", None)
    return row


@router.put("/me")
def update_profile(body: ProfileUpdate, user: dict = Depends(auth_required)):
    fields = {
        "full_name": body.full_name,
        "title": body.title,
        "gender": body.gender,
        "professional_role": body.professional_role,
    }

    if body.new_password:
        err = validate_password(body.new_password)
        if err:
            raise HTTPException(400, err)
        fields["password_hash"] = hash_password(body.new_password)

    update_user(user["id"], fields)
    return {"message": "Profile updated"}
