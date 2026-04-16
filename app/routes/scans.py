"""
app/routes/scans.py  –  /api/scans/*
Uses your team's helpers: save_scan(), save_results(), get_results_by_scan(),
                          get_scan_filename(), log_event()
"""

import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from app.db_helpers import (
    save_scan, save_results, get_results_by_scan,
    get_scan_filename, log_event, get_conn
)
from app.auth_utils import auth_required

router = APIRouter()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.get("/my-scans")
def my_scans(user: dict = Depends(auth_required)):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.id, s.filename, s.original_name, s.uploaded_at, s.status,
                      r.BV_mm3, r.TV_mm3, r.BV_TV, r.severity
               FROM Scans s
               LEFT JOIN Results r ON r.scan_id = s.id
               WHERE s.user_id = ?
               ORDER BY s.uploaded_at DESC""",
            (user["id"],),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/upload")
async def upload_scan(
    scan: UploadFile = File(...),
    title: str = Form(None),
    user: dict = Depends(auth_required),
):
    dest = UPLOAD_DIR / scan.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(scan.file, f)

    # Save scan record
    scan_id = save_scan(
        user_id=user["id"],
        filename=str(dest),
        original_name=scan.filename,
    )

    log_event(user["id"], "upload", f"Uploaded scan: {scan.filename}")

    # ── Replace this block with your real AI model later ──────────────
    # Placeholder segmentation copy
    seg_path = UPLOAD_DIR / (dest.stem + "_seg" + dest.suffix)
    shutil.copy(dest, seg_path)

    # Mock results — replace with real model output
    import random
    BV    = round(random.uniform(50, 200), 2)
    TV    = round(random.uniform(300, 600), 2)
    BV_TV = round(BV / TV, 4)
    if BV_TV > 0.40:
        diagnosis = "Healthy"
        severity  = None
    else:
        diagnosis = "Periodontitis"
        severity  = "severe" if BV_TV < 0.2 else "moderate" if BV_TV < 0.35 else "mild"

    save_results(scan_id, BV, TV, BV_TV, severity, diagnosis)
    log_event(user["id"], "analysis", f"Analysis complete for scan {scan_id}: {diagnosis} / {severity}")
    # ──────────────────────────────────────────────────────────────────

    return {
        "message": "Uploaded and analysed successfully",
        "scanId": scan_id,
        "imageUrl": f"/uploads/{dest.name}",
        "segmentationUrl": f"/uploads/{seg_path.name}",
        "results": {
            "BV_mm3": BV,
            "TV_mm3": TV,
            "BV_TV": BV_TV,
            "diagnosis": diagnosis,
            "severity": severity,
        },
    }


@router.get("/compare")
def compare_scans(
    baseline_id: int,
    treatment_id: int,
    user: dict = Depends(auth_required),
):
    baseline  = get_results_by_scan(baseline_id)
    treatment = get_results_by_scan(treatment_id)
    if not baseline:
        raise HTTPException(404, f"No results found for baseline scan {baseline_id}")
    if not treatment:
        raise HTTPException(404, f"No results found for treatment scan {treatment_id}")

    def delta(a, b):
        if a is None or b is None:
            return None
        return round(b - a, 4)

    return {
        "baseline":  baseline,
        "treatment": treatment,
        "deltas": {
            "BV_mm3": delta(baseline["BV_mm3"], treatment["BV_mm3"]),
            "TV_mm3": delta(baseline["TV_mm3"], treatment["TV_mm3"]),
            "BV_TV":  delta(baseline["BV_TV"],  treatment["BV_TV"]),
        },
    }


@router.get("/results/{scan_id}")
def get_results(scan_id: int, user: dict = Depends(auth_required)):
    result = get_results_by_scan(scan_id)
    if not result:
        raise HTTPException(404, "No results found for this scan")
    return result


class IssueBody(BaseModel):
    scan_id: int | None = None
    title: str
    description: str


@router.post("/issues")
def report_issue(body: IssueBody, user: dict = Depends(auth_required)):
    from app.db_helpers import save_issue
    save_issue(user["id"], body.scan_id, body.title, body.description)
    log_event(user["id"], "issue_reported", body.title)
    return {"message": "Issue reported"}
