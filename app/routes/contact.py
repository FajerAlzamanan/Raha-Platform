"""
app/routes/contact.py  –  /api/contact/guest
Uses your team's helper: save_contact_message()
Note: your schema splits name into first_name + last_name
"""

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from app.db_helpers import save_contact_message

router = APIRouter()


class ContactRequest(BaseModel):
    name: str          # we split this into first/last
    email: EmailStr
    message: str
    issue_type: str | None = None   # stored in message for now


@router.post("/guest")
def submit_contact(body: ContactRequest):
    parts = body.name.strip().split(" ", 1)
    first = parts[0]
    last  = parts[1] if len(parts) > 1 else ""

    full_message = body.message
    if body.issue_type:
        full_message = f"[{body.issue_type}] {body.message}"

    save_contact_message(first, last, body.email, full_message)
    return {"message": "Submitted"}
