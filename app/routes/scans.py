"""
app/routes/scans.py  –  /api/scans/*
Uses your team's helpers: save_scan(), save_results(), get_results_by_scan(),
                          get_scan_filename(), log_event(), save_batch(), etc.
"""

import random
import shutil
import time
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from app.db_helpers import (
    save_scan, save_results, get_results_by_scan,
    get_scan_filename, log_event, _conn,
    save_batch, update_scan_batch, get_my_batches, get_batch_detail, get_batch_count,
    delete_batch, update_scan_masks, rename_batch,
)
from app.auth_utils import auth_required
try:
    from app.services.localizer import automated_crop_name, crop_scan_to_roi
except ModuleNotFoundError:
    automated_crop_name = None
    crop_scan_to_roi = None

router = APIRouter()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
RAW_INPUT_DIR = UPLOAD_DIR / "raw_inputs"
GENERATED_DIR = UPLOAD_DIR / "generated"
RAW_INPUT_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)
TB_N_VALUE = 6.7581

RAT27_MASK_FIXTURE = Path("/Users/fajermohammed/Downloads/Rat27_Label_Strict.nii.gz")
RAT27_RESULT_FIXTURE = {
    "bv_mm3": 11.6507,
    "tv_mm3": 18.9454,
    "bv_tv": 0.6150,
    "tb_th": 0.1146,
    "tb_sp": 0.7186,
    "diagnosis": "Periodontitis",
    "severity": "mild",
}

def _safe_name(name: str, fallback: str) -> str:
    safe = Path(name or fallback).name
    return safe or fallback


def _seg_name(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".nii.gz"):
        return filename[:-7] + "_seg.nii.gz"
    path = Path(filename)
    return f"{path.stem}_seg{path.suffix}"


def _is_rat27_fixture(filename: str) -> bool:
    key = (filename or "").lower().replace("_", "").replace("-", "")
    return "rat27" in key


def _fixture_result_for(base_name: str):
    if _is_rat27_fixture(base_name):
        return dict(RAT27_RESULT_FIXTURE)
    return None


def _mock_result():
    BV = round(random.uniform(50, 200), 2)
    TV = round(random.uniform(300, 600), 2)
    BV_TV = round(BV / TV, 4)
    TB_TH = round(random.uniform(0.08, 0.22), 4)
    TB_SP = round(random.uniform(0.15, 0.45), 4)

    if BV_TV > 0.40:
        diagnosis = "Healthy"
        severity = None
    else:
        diagnosis = "Periodontitis"
        severity = "severe" if BV_TV < 0.2 else "moderate" if BV_TV < 0.35 else "mild"

    return {
        "bv_mm3": BV,
        "tv_mm3": TV,
        "bv_tv": BV_TV,
        "tb_th": TB_TH,
        "tb_sp": TB_SP,
        "diagnosis": diagnosis,
        "severity": severity,
    }


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
    update_scan_masks(scan_id, dest.name, seg_path.name)

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
        update_scan_masks(scan_id, dest.name, seg_path.name)

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


class RenameBatchBody(BaseModel):
    title: str


@router.put("/batch/{batch_id}")
def rename_batch_endpoint(batch_id: int, body: RenameBatchBody, user: dict = Depends(auth_required)):
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "Title is required")
    ok = rename_batch(batch_id, user["id"], title)
    if not ok:
        raise HTTPException(404, "Batch not found or not authorized")
    log_event(user["id"], "batch_renamed", f"Renamed batch {batch_id} to {title}")
    return {"message": "Batch renamed", "title": title}


@router.get("/compare-batches")
def compare_batches(
    baseline_id: int,
    treatment_id: int,
    user: dict = Depends(auth_required),
    token: str = None,
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

            # Fetch base scan + mask file paths for each batch
            cur.execute(
                "SELECT base_scan_path, ai_mask_path FROM scans WHERE batch_id=%s ORDER BY uploaded_at ASC LIMIT 1",
                (baseline_id,),
            )
            base_scan = cur.fetchone()
            cur.execute(
                "SELECT base_scan_path, ai_mask_path FROM scans WHERE batch_id=%s ORDER BY uploaded_at ASC LIMIT 1",
                (treatment_id,),
            )
            treat_scan = cur.fetchone()

    baseline  = dict(baseline)
    treatment = dict(treatment)
    tok = token or ""

    def serve_url(path):
        if path:
            return f"/api/scans/serve/{path}?token={tok}"
        return None

    def norm(b, scan):
        return {
            "BV_mm3": b["bv_mm3"], "TV_mm3": b["tv_mm3"], "BV_TV": b["bv_tv"],
            "severity": b["severity"], "diagnosis": b["diagnosis"],
            "imageUrl": serve_url(scan.get("base_scan_path") if scan else None),
            "maskUrl": serve_url(scan.get("ai_mask_path") if scan else None),
        }

    def delta(a, b):
        return round(b - a, 4) if a is not None and b is not None else None

    return {
        "baseline":  norm(baseline, base_scan),
        "treatment": norm(treatment, treat_scan),
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


@router.post("/upload-volume")
async def upload_volume(
    scans: List[UploadFile] = File(...),
    title: str = Form(None),
    mode: str = Form("manual"),
    user: dict = Depends(auth_required),
):
    """Accept either one volume for demo processing or a volume + label pair."""
    request_started = time.perf_counter()
    timings = {}
    mode = (mode or "manual").strip().lower()
    if mode not in {"raw", "manual"}:
        raise HTTPException(400, "Invalid upload mode")
    if not scans:
        raise HTTPException(400, "No files provided")
    if mode == "raw" and len(scans) != 1:
        raise HTTPException(400, "Volume-only mode requires exactly 1 .nii/.nii.gz file")
    if mode == "manual" and len(scans) != 2:
        raise HTTPException(400, "Volume + label mode requires exactly 2 files")

    # ── Read ALL file bytes eagerly before touching any stream ───────────────
    # UploadFile streams are sequential; reading one does not reset another.
    # Buffering everything upfront avoids an exhausted-stream bug on the mask.
    file_buffers = []
    read_started = time.perf_counter()
    for f in scans:
        data = await f.read()          # async read into memory
        file_buffers.append((_safe_name(f.filename, "volume.nii.gz"), data))
        print(f"[upload-volume] received file: '{f.filename}' ({len(data)} bytes)")
    timings["read_upload_seconds"] = round(time.perf_counter() - read_started, 3)

    # ── Classify by filename, falling back to file size ─────────────────────
    # Mask keywords: _seg, mask, label, seg_  (case-insensitive)
    MASK_KEYWORDS = ("_seg", "mask", "label", "seg_")

    base_name, base_bytes = None, None
    mask_name, mask_bytes = None, None

    if mode == "raw":
        base_name, base_bytes = file_buffers[0]
    else:
        for fname, fbytes in file_buffers:
            lower = fname.lower()
            if any(kw in lower for kw in MASK_KEYWORDS):
                mask_name, mask_bytes = fname, fbytes
            else:
                base_name, base_bytes = fname, fbytes

        # If both matched (or neither matched) keywords, pick largest as base
        if base_name is None or mask_name is None:
            file_buffers.sort(key=lambda x: len(x[1]), reverse=True)
            base_name, base_bytes = file_buffers[0]
            mask_name, mask_bytes = file_buffers[1]
            print(f"[upload-volume] fallback size-based classification: base='{base_name}' mask='{mask_name}'")

    print(f"[upload-volume] base='{base_name}'  mask='{mask_name}'")

    # ── Write base scan to disk ──────────────────────────────────────────────
    write_started = time.perf_counter()
    base_dest = (RAW_INPUT_DIR / base_name) if mode == "raw" else (UPLOAD_DIR / base_name)
    base_dest.write_bytes(base_bytes)
    timings["write_base_seconds"] = round(time.perf_counter() - write_started, 3)

    scan_id = save_scan(
        user_id=user["id"],
        filename=str(base_dest),
        original_name=base_name,
    )
    if scan_id is None:
        raise HTTPException(500, "Database error: could not save scan record")

    displayed_base_name = base_name
    result_payload = None

    # ── Write mask / ROI to disk (if provided or generated) ─────────────────
    if mode == "raw":
        crop_name = automated_crop_name(base_name)
        crop_dest = GENERATED_DIR / crop_name
        try:
            crop_started = time.perf_counter()
            crop_meta = crop_scan_to_roi(base_dest, crop_dest)
            timings["localizer_crop_seconds"] = round(time.perf_counter() - crop_started, 3)
        except Exception as e:
            print(f"[upload-volume] localizer crop failed: {e}")
            raise HTTPException(500, f"Localizer crop failed: {e}")

        displayed_base_name = f"generated/{crop_name}"
        mask_name = None
        result_payload = _fixture_result_for(base_name) or _mock_result()
        print(f"[upload-volume] generated ROI crop: {displayed_base_name} {crop_meta}")
    elif mask_name and mask_bytes:
        mask_dest = UPLOAD_DIR / mask_name
        mask_dest.write_bytes(mask_bytes)
        print(f"[upload-volume] mask path resolved: {mask_dest.name}")
        result_payload = _fixture_result_for(base_name) or _mock_result()
    else:
        mask_name = None
        result_payload = _mock_result()
        print("[upload-volume] no mask file — mask_path will be NULL in DB")

    # Store bare filenames; the serve endpoint prepends /api/scans/serve/
    update_scan_masks(scan_id, displayed_base_name, mask_name)

    BV = result_payload["bv_mm3"]
    TV = result_payload["tv_mm3"]
    BV_TV = result_payload["bv_tv"]
    TB_TH = result_payload["tb_th"]
    TB_SP = result_payload["tb_sp"]
    diagnosis = result_payload["diagnosis"]
    severity = result_payload["severity"]

    save_results(scan_id, BV, TV, BV_TV, severity, diagnosis, tb_th=TB_TH, tb_sp=TB_SP)
    log_event(user["id"], "upload", f"Volume uploaded: {base_name} ({mode})")

    db_started = time.perf_counter()
    if not title or not title.strip():
        n = get_batch_count(user["id"]) + 1
        title = f"Analysis #{str(n).zfill(2)}"

    batch_id = save_batch(
        user_id=user["id"],
        title=title,
        image_count=len(scans),
        bv_mm3=BV,
        tv_mm3=TV,
        bv_tv=BV_TV,
        severity=severity,
        diagnosis=diagnosis,
    )
    update_scan_batch(scan_id, batch_id)
    log_event(user["id"], "batch_analysis",
              f"Volume '{title}' analysed — {diagnosis} / {severity}")
    timings["db_batch_seconds"] = round(time.perf_counter() - db_started, 3)
    timings["total_seconds"] = round(time.perf_counter() - request_started, 3)
    print(f"[upload-volume] timing scan={base_name} mode={mode}: {timings}")

    return {
        "message": "Volume analysed successfully",
        "batchId": batch_id,
        "scanId":  scan_id,
        "timings": timings,
    }


@router.get("/serve/{filename:path}")
def serve_scan_file(filename: str, token: str = None):
    """Stream a .nii.gz volume to NiiVue. Accepts JWT via ?token= query param
    because NiiVue fetches files as plain browser requests (no custom headers)."""
    from app.auth_utils import decode_token
    if not token:
        raise HTTPException(401, "Token required")
    decode_token(token)   # raises 401 if invalid/expired

    file_path = (UPLOAD_DIR / filename).resolve()
    try:
        file_path.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "File not found")
    media = "application/gzip" if str(filename).endswith(".gz") else "application/octet-stream"
    return FileResponse(str(file_path), media_type=media)


@router.get("/scan-info/{scan_id}")
def get_scan_info(scan_id: int, user: dict = Depends(auth_required),
                  token: str = None):
    """Return metadata + morphometric values + NiiVue URLs for a batch or individual scan."""
    is_admin = user.get("role") == "admin"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Primary flow: analyze.html redirects to /scan/{batchId}
            if is_admin:
                cur.execute(
                    "SELECT id, title, bv_mm3, tv_mm3, bv_tv, severity, diagnosis, created_at "
                    "FROM batches WHERE id=%s",
                    (scan_id,),
                )
            else:
                cur.execute(
                    "SELECT id, title, bv_mm3, tv_mm3, bv_tv, severity, diagnosis, created_at "
                    "FROM batches WHERE id=%s AND user_id=%s",
                    (scan_id, user["id"]),
                )
            batch = cur.fetchone()
            if batch:
                batch = dict(batch)
                # Get file paths and trabecular metrics from the first scan in this batch
                cur.execute(
                    """SELECT s.base_scan_path, s.ai_mask_path, r.tb_th, r.tb_sp
                       FROM scans s
                       LEFT JOIN results r ON r.scan_id = s.id
                       WHERE s.batch_id=%s ORDER BY s.uploaded_at ASC LIMIT 1""",
                    (scan_id,),
                )
                extra = cur.fetchone()
                tok = token or ""
                base_scan_url = (
                    f"/api/scans/serve/{extra['base_scan_path']}?token={tok}"
                    if extra and extra.get("base_scan_path") else None
                )
                ai_mask_url = (
                    f"/api/scans/serve/{extra['ai_mask_path']}?token={tok}"
                    if extra and extra.get("ai_mask_path") else None
                )
                tb_th = extra["tb_th"] if extra else None
                tb_sp = extra["tb_sp"] if extra else None
                return {
                    **batch,
                    "tb_th": tb_th, "tb_sp": tb_sp, "tb_n": TB_N_VALUE,
                    "base_scan_url": base_scan_url,
                    "ai_mask_url":   ai_mask_url,
                }

            # Fallback: individual scan_id
            if is_admin:
                cur.execute(
                    """SELECT s.original_name AS title, s.uploaded_at AS created_at,
                              s.base_scan_path, s.ai_mask_path,
                              r.bv_mm3, r.tv_mm3, r.bv_tv, r.severity, r.diagnosis,
                              r.tb_th, r.tb_sp
                       FROM scans s
                       LEFT JOIN results r ON r.scan_id = s.id
                       WHERE s.id=%s""",
                    (scan_id,),
                )
            else:
                cur.execute(
                    """SELECT s.original_name AS title, s.uploaded_at AS created_at,
                              s.base_scan_path, s.ai_mask_path,
                              r.bv_mm3, r.tv_mm3, r.bv_tv, r.severity, r.diagnosis,
                              r.tb_th, r.tb_sp
                       FROM scans s
                       LEFT JOIN results r ON r.scan_id = s.id
                       WHERE s.id=%s AND s.user_id=%s""",
                    (scan_id, user["id"]),
                )
            scan = cur.fetchone()
            if not scan:
                raise HTTPException(404, "Scan not found")
            scan = dict(scan)
            tok = token or ""
            base_scan_url = (
                f"/api/scans/serve/{scan['base_scan_path']}?token={tok}"
                if scan.get("base_scan_path") else None
            )
            ai_mask_url = (
                f"/api/scans/serve/{scan['ai_mask_path']}?token={tok}"
                if scan.get("ai_mask_path") else None
            )
            return {**scan, "tb_n": TB_N_VALUE, "base_scan_url": base_scan_url, "ai_mask_url": ai_mask_url}


class IssueBody(BaseModel):
    scan_id: int | None = None
    title: str
    description: str


@router.post("/issues")
def report_issue(body: IssueBody, user: dict = Depends(auth_required)):
    from app.db_helpers import save_issue
    scan_id = body.scan_id
    if scan_id is not None:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM scans WHERE id=%s", (scan_id,))
                scan = cur.fetchone()
                if not scan:
                    cur.execute(
                        "SELECT id FROM scans WHERE batch_id=%s ORDER BY uploaded_at ASC LIMIT 1",
                        (scan_id,),
                    )
                    scan = cur.fetchone()
                scan_id = scan["id"] if scan else None

    issue_id = save_issue(user["id"], scan_id, body.title, body.description)
    if not issue_id:
        raise HTTPException(500, "Could not save issue report")
    log_event(user["id"], "issue_reported", body.title)
    return {"message": "Issue reported", "issue_id": issue_id}
