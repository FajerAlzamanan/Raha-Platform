"""
app/routes/auth.py  –  /api/auth/signup, /api/auth/login,
                        /api/auth/forgot-password, /api/auth/reset-password
Uses your team's db_helpers: create_user(), get_user(), log_event()
"""

import os, secrets
from datetime import datetime, timedelta, timezone

import resend
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

from app.db_helpers import create_user, get_user, get_user_by_id, log_event, \
    save_reset_token, verify_reset_token, mark_token_used, update_user
from app.auth_utils import hash_password, verify_password, validate_password, create_token

load_dotenv()
resend.api_key = os.getenv("RESEND_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "noreply@raha.com")

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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    user = get_user(body.email)
    # Always return the same message to avoid leaking whether an email exists
    generic = {"message": "If that email is registered, you will receive a reset link shortly."}
    if not user:
        return generic

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    save_reset_token(user["id"], token, expires_at)

    base_url = os.getenv("BASE_URL", "http://localhost:4000")
    reset_link = f"{base_url}/reset-password/{token}"

    html_body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Reset Your Raha Password</title>
</head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background-color:#f4f7f6;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f7f6;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#378d8c,#2a6e6d);padding:40px 40px 32px;text-align:center;">
              <div style="width:64px;height:64px;background:rgba(255,255,255,0.15);border-radius:16px;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
              </div>
              <h1 style="margin:0;font-size:26px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">Reset Your Password</h1>
              <p style="margin:8px 0 0;font-size:14px;color:rgba(255,255,255,0.8);">Raha Bone Density Analysis Platform</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 16px;font-size:16px;color:#374151;line-height:1.6;">
                Hi <strong>{user['full_name']}</strong>,
              </p>
              <p style="margin:0 0 24px;font-size:15px;color:#6b7280;line-height:1.7;">
                We received a request to reset the password for your Raha account. Click the button below to choose a new password. This link will expire in <strong>1 hour</strong>.
              </p>

              <!-- CTA Button -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding:8px 0 32px;">
                    <a href="{reset_link}"
                       style="display:inline-block;background:linear-gradient(135deg,#378d8c,#2a6e6d);color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;padding:14px 36px;border-radius:10px;box-shadow:0 4px 14px rgba(55,141,140,0.35);">
                      Reset Password
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Divider -->
              <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;"/>

              <p style="margin:0 0 12px;font-size:13px;color:#9ca3af;line-height:1.6;">
                If the button doesn't work, copy and paste this link into your browser:
              </p>
              <p style="margin:0 0 24px;font-size:12px;word-break:break-all;">
                <a href="{reset_link}" style="color:#378d8c;text-decoration:none;">{reset_link}</a>
              </p>

              <div style="background:#fef3ee;border-left:4px solid #d18670;border-radius:6px;padding:14px 16px;">
                <p style="margin:0;font-size:13px;color:#92400e;line-height:1.6;">
                  <strong>Didn't request this?</strong> You can safely ignore this email. Your password will not change unless you click the link above.
                </p>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f9fafb;padding:24px 40px;text-align:center;border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 4px;font-size:13px;color:#6b7280;">
                &copy; 2025 Raha Platform. All rights reserved.
              </p>
              <p style="margin:0;font-size:12px;color:#9ca3af;">
                This email was sent to {user['email']}
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    try:
        resend.Emails.send({
            "from": MAIL_FROM,
            "to": [user["email"]],
            "subject": "Reset Your Raha Password",
            "html": html_body,
        })
    except Exception as e:
        print(f"forgot_password email error: {e}")
        # Still return generic message – don't expose internal errors

    return generic


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    record = verify_reset_token(body.token)
    if not record:
        raise HTTPException(400, "Reset link is invalid or has expired.")

    err = validate_password(body.password)
    if err:
        raise HTTPException(400, err)

    pw_hash = hash_password(body.password)
    update_user(record["user_id"], {"password_hash": pw_hash})
    mark_token_used(body.token)

    user = get_user_by_id(record["user_id"])
    if user:
        log_event(user["id"], "password_reset", f"{user['email']} reset their password")

    return {"message": "Password updated successfully."}
