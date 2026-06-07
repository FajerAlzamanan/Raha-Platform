"""
app/routes/admin.py  –  /api/admin/*
Uses your team's helpers: get_system_logs(), get_issues(), update_user()
"""

from fastapi import APIRouter, HTTPException, Depends
from psycopg2.extras import RealDictCursor
from app.db_helpers import get_system_logs, get_issues, update_user, _conn, log_event
from app.auth_utils import admin_only
from app.name_utils import format_title

router = APIRouter()


@router.get("/users")
def list_users(admin: dict = Depends(admin_only)):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, full_name, email, role, title, professional_role, institution, created_at FROM users"
            )
            rows = cur.fetchall()
    users = []
    for row in rows:
        item = dict(row)
        item["display_title"] = format_title(item.get("title"))
        users.append(item)
    return users


@router.get("/stats")
def admin_stats(admin: dict = Depends(admin_only)):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS total FROM users")
            total_users = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM batches")
            total_analyses = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM issues WHERE status='open'")
            open_issues = cur.fetchone()["total"]
    return {
        "total_users": total_users,
        "total_analyses": total_analyses,
        "open_issues": open_issues,
    }


@router.get("/logs")
def view_logs(admin: dict = Depends(admin_only)):
    return get_system_logs(limit=200)


@router.get("/issues")
def view_issues(admin: dict = Depends(admin_only)):
    return get_issues()


@router.put("/users/{user_id}/toggle")
def toggle_user(user_id: int, admin: dict = Depends(admin_only)):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT role FROM users WHERE id=%s", (user_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "User not found")
            new_role = "suspended" if row["role"] != "suspended" else "researcher"
            cur.execute("UPDATE users SET role=%s WHERE id=%s", (new_role, user_id))
    log_event(admin["id"], "admin_toggle", f"User {user_id} role set to {new_role}")
    return {"message": "User updated", "role": new_role}


@router.put("/issues/{issue_id}/close")
def close_issue(issue_id: int, admin: dict = Depends(admin_only)):
    return set_issue_status(issue_id, "closed", admin)


@router.put("/issues/{issue_id}/reopen")
def reopen_issue(issue_id: int, admin: dict = Depends(admin_only)):
    return set_issue_status(issue_id, "open", admin)


def set_issue_status(issue_id: int, new_status: str, admin: dict):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, title FROM issues WHERE id=%s", (issue_id,))
            issue = cur.fetchone()
            if not issue:
                raise HTTPException(404, "Issue not found")
            cur.execute("UPDATE issues SET status=%s WHERE id=%s", (new_status, issue_id))
    log_event(admin["id"], f"issue_{new_status}", f"Issue {issue_id}: {issue['title']}")
    return {"message": f"Issue {new_status}", "status": new_status}
