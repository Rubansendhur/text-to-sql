"""
upload/semester.py
──────────────────────
POST /api/upload/semester

Upload after each semester result publication.

Two formats auto-detected:

  Format A — GPA only (one row per student):
    register_number, semester, gpa

  Format B — GPA + per-subject grades (multiple rows per student):
    register_number, semester, gpa, subject_code, grade

Logic:
  • Every row → student_semester_gpa (upsert)
  • grade == 'U' → also stored in student_subject_attempts (arrear)
"""

from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy import text
from psycopg2.extras import execute_values
from typing import Optional

from .helpers import (
    get_db, read_file, normalize_columns, UploadResult,
    clean_str, clean_reg, clean_float, clean_int,
    normalize_grade,
)
from .gpa import calculate_gpa_internal

router = APIRouter()

COL_MAP = {
    "register number": "register_number",
    "register no":     "register_number",
    "semester":        "semester",
    "sem":             "semester",
    "semester number": "semester",
    "gpa":             "gpa",
    "sgpa":            "gpa",
    "subject code":    "subject_code",
    "subject":         "subject_code",
    "grade":           "grade",
}


@router.post("/semester")
async def upload_semester(
    file: UploadFile = File(...),
    uploaded_by: Optional[str] = Form(default="staff"),
):
    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large")

    df = read_file(content, file.filename or "upload")
    if df is None:
        raise HTTPException(400, "Invalid file")

    df = normalize_columns(df, COL_MAP)
    result = UploadResult("semester_results", total=len(df))

    engine = get_db()

    has_subject = "subject_code" in df.columns
    has_grade = "grade" in df.columns

    if not (has_subject and has_grade):
        raise HTTPException(400, "File must contain subject_code and grade")

    now = datetime.now()
    exam_month = "MAY" if now.month <= 6 else "NOV"

    with engine.begin() as conn:

        # 🔥 Cache students
        student_map = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT register_number, student_id FROM students"))
        }

        # 🔥 Cache subjects
        subject_map = {
            row[0]: row[1]
            for row in conn.execute(text("SELECT subject_code, subject_id FROM subjects"))
        }

        subject_rows = []
        arrear_rows = []
        affected = set()

        for idx, row in df.iterrows():
            row_num = idx + 2

            # ── STUDENT ─────────────────────────
            reg = clean_reg(row.get("register_number"))
            student_id = student_map.get(reg)

            if not student_id:
                result.errors.append(f"Row {row_num}: student '{reg}' not found")
                result.skipped += 1
                continue

            # ── SEMESTER ────────────────────────
            sem = clean_int(row.get("semester"))
            if not sem or not (1 <= sem <= 10):
                result.errors.append(f"Row {row_num}: invalid semester")
                result.skipped += 1
                continue

            # ── SUBJECT + GRADE ─────────────────
            sub_code = clean_str(row.get("subject_code"))
            grade = normalize_grade(row.get("grade"))

            if not sub_code or not grade:
                result.errors.append(f"Row {row_num}: missing subject/grade")
                result.skipped += 1
                continue

            subject_id = subject_map.get(sub_code)

            if not subject_id:
                result.errors.append(f"Row {row_num}: subject '{sub_code}' not found")
                result.skipped += 1
                continue

            # ✅ STORE ALL SUBJECT RESULTS
            subject_rows.append((
                student_id,
                subject_id,
                sem,
                grade,
                now.year,
                exam_month
            ))

            # ✅ AFFECTED STUDENTS (for GPA recalculation)
            affected.add((student_id, sem))

            # ✅ TRACK ARREARS
            if grade == "U":
                arrear_rows.append((
                    student_id,
                    subject_id,
                    now.year,
                    exam_month,
                    "U"
                ))
            

        # ── BULK SUBJECT RESULTS INSERT ─────────────────────────
        if subject_rows:
            cursor = conn.connection.cursor()

            execute_values(
                cursor,
                """
                INSERT INTO student_subject_results
                (student_id, subject_id, semester_number, grade, exam_year, exam_month)
                VALUES %s
                ON CONFLICT (student_id, subject_id, semester_number)
                DO UPDATE SET
                    grade = EXCLUDED.grade,
                    exam_year = EXCLUDED.exam_year,
                    exam_month = EXCLUDED.exam_month
                """
                ,
                subject_rows
            )

            result.inserted = len(subject_rows)

        # ── BULK ARREARS INSERT ─────────────────────────
        if arrear_rows:
            cursor = conn.connection.cursor()

            execute_values(
                cursor,
                """
                INSERT INTO student_subject_attempts
                (student_id, subject_id, exam_year, exam_month, grade)
                VALUES %s
                ON CONFLICT (student_id, subject_id, exam_year, exam_month)
                DO UPDATE SET grade = 'U'
                """,
                arrear_rows
            )
        # ── GPA CALCULATION ─────────────────────────
        if subject_rows:
            for student_id, sem in affected:
                calculate_gpa_internal(conn, student_id, sem)

    result_dict = result.dict()
    result_dict["arrears_tracked"] = len(arrear_rows)

    return result_dict