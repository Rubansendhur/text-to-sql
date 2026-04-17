"""
upload/arrear.py
────────────────────
POST /api/upload/arrear

Upload after arrear exams — store ALL grades (pass AND fail).

The vw_active_arrears view automatically determines cleared vs active:
  latest attempt = 'U'          → still active
  latest attempt = O/A+/A/etc   → cleared (history preserved)

Required: register_number, subject_code, exam_year, exam_month, grade
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import text

from .helpers import (
    get_db, read_file, normalize_columns, UploadResult,
    clean_str, clean_reg, clean_int,
    normalize_grade, normalize_month,
    get_student_id, get_subject_id,
)

router = APIRouter()

COL_MAP = {
    "register number": "register_number",
    "register no":     "register_number",
    "subject code":    "subject_code",
    "course code":     "subject_code",
    "exam year":       "exam_year",
    "year":            "exam_year",
    "exam month":      "exam_month",
    "month":           "exam_month",
    "grade":           "grade",
    "result":          "grade",
}


@router.post("/arrear")
async def upload_arrear(file: UploadFile = File(...)):
    content = await file.read()
    df      = read_file(content, file.filename or "upload")
    if df is None:
        raise HTTPException(400, "Could not read file.")

    df     = normalize_columns(df, COL_MAP)
    result = UploadResult("arrear_results", total=len(df))
    engine = get_db()

    with engine.begin() as conn:
        for idx, row in df.iterrows():
            row_num = idx + 2

            # ── Validate all required fields first ────────────────────────────
            reg      = clean_reg(row.get("register_number"))
            sub_code = clean_str(row.get("subject_code"), 20)
            grade    = normalize_grade(row.get("grade"))
            month    = normalize_month(row.get("exam_month"))
            year     = clean_int(row.get("exam_year"))

            errs = []
            if not reg:      errs.append("invalid register_number")
            if not sub_code: errs.append("missing subject_code")
            if not grade:    errs.append(f"invalid grade '{row.get('grade')}'")
            if not month:    errs.append(f"invalid exam_month '{row.get('exam_month')}' — use MAY or NOV")
            if not year:     errs.append(f"invalid exam_year '{row.get('exam_year')}'")

            if errs:
                result.errors.append(f"Row {row_num}: {' | '.join(errs)}")
                result.skipped += 1; continue

            # ── DB lookups ────────────────────────────────────────────────────
            student_id = get_student_id(conn, reg)           # type: ignore[arg-type]
            if not student_id:
                result.errors.append(f"Row {row_num}: student '{reg}' not found")
                result.skipped += 1; continue

            subject_id = get_subject_id(conn, sub_code.upper())  # type: ignore[union-attr]
            if not subject_id:
                result.errors.append(f"Row {row_num}: subject '{sub_code}' not found — upload subjects first")
                result.skipped += 1; continue

            # ── Upsert attempt ────────────────────────────────────────────────
            existing = conn.execute(text("""
                SELECT attempt_id FROM student_subject_attempts
                WHERE student_id=:sid AND subject_id=:subid
                  AND exam_year=:year AND exam_month=:month
            """), {"sid": student_id, "subid": subject_id,
                   "year": year, "month": month}).fetchone()

            conn.execute(text("""
                INSERT INTO student_subject_attempts
                    (student_id, subject_id, exam_year, exam_month, grade)
                VALUES (:sid, :subid, :year, :month, :grade)
                ON CONFLICT (student_id, subject_id, exam_year, exam_month)
                DO UPDATE SET grade = EXCLUDED.grade
            """), {
                "sid":   student_id,
                "subid": subject_id,
                "year":  year,
                "month": month,
                "grade": grade,
            })

            if existing: result.updated += 1
            else:        result.inserted += 1

    return result.dict()
