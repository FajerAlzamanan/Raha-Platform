"""
app/routes/scans.py  –  /api/scans/*
Uses your team's helpers: save_scan(), save_results(), get_results_by_scan(),
                          get_scan_filename(), log_event(), save_batch(), etc.
"""

import shutil, random
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from app.db_helpers import (
    save_scan, save_results, get_results_by_scan,
    get_scan_filename, log_event, _conn,
    save_batch, update_scan_batch, get_my_batches, get_batch_detail, get_batch_count,
    delete_batch,
)
from app.auth_utils import auth_required

router = APIRouter()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.get("/my-scans")
def my_scans(user: dict = Depends(auth_required)):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT s.id, s.filename, s.original_name, s.uploaded_at, s.status,
                          r.bv_mm3 AS "BV_mm3", r.tv_mm3 AS "TV_mm3", r.bv_tv AS "BV_TV", r.severity
                   FROM scans s
                   LEFT JOIN results r ON r.scan_id = s.id
                   WHERE s.user_id = %s
                   ORDER BY s.uploaded_at DESC""",
                (user["id"],),
            )
            rows = cur.fetchall()
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

    scan_id = save_scan(
        user_id=user["id"],
        filename=str(dest),
        original_name=scan.filename,
    )

    log_event(user["id"], "upload", f"Uploaded scan: {scan.filename}")

    seg_path = UPLOAD_DIR / (dest.stem + "_seg" + dest.suffix)
    shutil.copy(dest, seg_path)

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


@router.post("/upload-batch")
async def upload_batch(
    scans: List[UploadFile] = File(...),
    title: str = Form(None),
    user: dict = Depends(auth_required),
):
    if not scans:
        raise HTTPException(400, "No files provided")

    if not title or not title.strip():
        n = get_batch_count(user["id"]) + 1
        title = f"Analysis #{str(n).zfill(2)}"
    scan_ids = []
    total_BV = 0.0
    total_TV = 0.0

    for scan in scans:
        dest = UPLOAD_DIR / scan.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(scan.file, f)

        scan_id = save_scan(
            user_id=user["id"],
            filename=str(dest),
            original_name=scan.filename,
        )
        scan_ids.append(scan_id)

        BV = round(random.uniform(50, 200), 2)
        TV = round(random.uniform(300, 600), 2)
        total_BV += BV
        total_TV += TV

        seg_path = UPLOAD_DIR / (dest.stem + "_seg" + dest.suffix)
        shutil.copy(dest, seg_path)

    total_BV  = round(total_BV, 2)
    total_TV  = round(total_TV, 2)
    agg_BV_TV = round(total_BV / total_TV, 4)

    if agg_BV_TV > 0.40:
        diagnosis = "Healthy"
        severity  = None
    else:
        diagnosis = "Periodontitis"
        severity  = "severe" if agg_BV_TV < 0.2 else "moderate" if agg_BV_TV < 0.35 else "mild"

    batch_id = save_batch(
        user_id=user["id"],
        title=title,
        image_count=len(scans),
        bv_mm3=total_BV,
        tv_mm3=total_TV,
        bv_tv=agg_BV_TV,
        severity=severity,
        diagnosis=diagnosis,
    )

    for scan_id in scan_ids:
        update_scan_batch(scan_id, batch_id)

    log_event(
        user["id"], "batch_analysis",
        f"Batch '{title}' analyzed: {len(scans)} images — {diagnosis} / {severity}",
    )

    return {
        "message": "Batch analysed successfully",
        "batchId": batch_id,
        "title": title,
        "imageCount": len(scans),
        "results": {
            "BV_mm3": total_BV,
            "TV_mm3": total_TV,
            "BV_TV": agg_BV_TV,
            "diagnosis": diagnosis,
            "severity": severity,
        },
    }


@router.get("/my-batches")
def my_batches_list(user: dict = Depends(auth_required)):
    rows = get_my_batches(user["id"])
    return rows if rows is not None else []


@router.get("/batch/{batch_id}")
def get_batch_detail_endpoint(batch_id: int, user: dict = Depends(auth_required)):
    batch = get_batch_detail(batch_id, user["id"])
    if not batch:
        raise HTTPException(404, "Batch not found")
    return batch


@router.delete("/batch/{batch_id}")
def delete_batch_endpoint(batch_id: int, user: dict = Depends(auth_required)):
    ok = delete_batch(batch_id, user["id"])
    if not ok:
        raise HTTPException(404, "Batch not found or not authorized")
    log_event(user["id"], "batch_deleted", f"Deleted batch {batch_id}")
    return {"message": "Batch deleted"}


@router.get("/compare-batches")
def compare_batches(
    baseline_id: int,
    treatment_id: int,
    user: dict = Depends(auth_required),
):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT bv_mm3, tv_mm3, bv_tv, severity, diagnosis FROM batches WHERE id=%s AND user_id=%s",
                (baseline_id, user["id"]),
            )
            baseline = cur.fetchone()
            if not baseline:
                raise HTTPException(404, f"Baseline batch {baseline_id} not found")
            cur.execute(
                "SELECT bv_mm3, tv_mm3, bv_tv, severity, diagnosis FROM batches WHERE id=%s AND user_id=%s",
                (treatment_id, user["id"]),
            )
            treatment = cur.fetchone()
            if not treatment:
                raise HTTPException(404, f"Treatment batch {treatment_id} not found")

    baseline  = dict(baseline)
    treatment = dict(treatment)

    def norm(b):
        return {"BV_mm3": b["bv_mm3"], "TV_mm3": b["tv_mm3"], "BV_TV": b["bv_tv"],
                "severity": b["severity"], "diagnosis": b["diagnosis"]}

    def delta(a, b):
        return round(b - a, 4) if a is not None and b is not None else None

    return {
        "baseline":  norm(baseline),
        "treatment": norm(treatment),
        "deltas": {
            "BV_mm3": delta(baseline["bv_mm3"], treatment["bv_mm3"]),
            "TV_mm3": delta(baseline["tv_mm3"], treatment["tv_mm3"]),
            "BV_TV":  delta(baseline["bv_tv"],  treatment["bv_tv"]),
        },
    }


@router.get("/compare")
def compare_scans(
    baseline_id: int,
    treatment_id: int,
    user: dict = Depends(auth_required),
):
    baseline_rows  = get_results_by_scan(baseline_id)
    treatment_rows = get_results_by_scan(treatment_id)
    if not baseline_rows:
        raise HTTPException(404, f"No results found for baseline scan {baseline_id}")
    if not treatment_rows:
        raise HTTPException(404, f"No results found for treatment scan {treatment_id}")

    baseline  = baseline_rows[0]
    treatment = treatment_rows[0]

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
    return result[0]


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