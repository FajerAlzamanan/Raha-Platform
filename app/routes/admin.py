"""
app/routes/admin.py  –  /api/admin/*
Uses your team's helpers: get_system_logs(), get_issues(), update_user()
"""

from fastapi import APIRouter, HTTPException, Depends
from app.db_helpers import get_system_logs, get_issues, update_user, get_conn, log_event
from app.auth_utils import admin_only

router = APIRouter()


@router.get("/users")
def list_users(admin: dict = Depends(admin_only)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, full_name, email, role, title, professional_role, created_at FROM Users"
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/logs")
def view_logs(admin: dict = Depends(admin_only)):
    return get_system_logs(limit=200)


@router.get("/issues")
def view_issues(admin: dict = Depends(admin_only)):
    return get_issues()


@router.put("/users/{user_id}/toggle")
def toggle_user(user_id: int, admin: dict = Depends(admin_only)):
    with get_conn() as conn:
        row = conn.execute("SELECT role FROM Users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        # Toggle role between researcher and inactive marker
        # (your schema uses role not is_active — we use a suspended role)
        new_role = "suspended" if row["role"] != "suspended" else "researcher"
        conn.execute("UPDATE Users SET role=? WHERE id=?", (new_role, user_id))
    log_event(admin["id"], "admin_toggle", f"User {user_id} role set to {new_role}")
    return {"message": "User updated", "role": new_role}


@router.put("/issues/{issue_id}/close")
def close_issue(issue_id: int, admin: dict = Depends(admin_only)):
    with get_conn() as conn:
        conn.execute("UPDATE Issues SET status='closed' WHERE id=?", (issue_id,))
    return {"message": "Issue closed"}
