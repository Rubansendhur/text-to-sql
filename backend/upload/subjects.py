"""
upload/subjects.py
──────────────────────
POST /api/upload/subjects

Required : subject_code, subject_name, department_code, semester_number
Optional : subject_type, lecture_hrs, tutorial_hrs, practical_hrs, credits
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import text

from .helpers import (
    get_db, read_file, normalize_columns, UploadResult,
    clean_str, clean_int, get_dept_id,
)

router = APIRouter()

COL_MAP = {
    "subject code":    "subject_code",
    "subject name":    "subject_name",
    "course code":     "subject_code",
    "course name":     "subject_name",
    "department code": "department_code",
    "dept_code":       "department_code",
    "dept code":       "department_code",
    "semester number": "semester_number",
    "semester":        "semester_number",
    "sem":             "semester_number",
    "subject type":    "subject_type",
    "type":            "subject_type",
    "lecture hrs":     "lecture_hrs",
    "l":               "lecture_hrs",
    "tutorial hrs":    "tutorial_hrs",
    "t":               "tutorial_hrs",
    "practical hrs":   "practical_hrs",
    "p":               "practical_hrs",
    "credits":         "credits",
    "c":               "credits",
}

VALID_TYPES = {"Theory", "Practical", "Elective", "Elective Practical", "Activity"}


@router.post("/subjects")
async def upload_subjects(file: UploadFile = File(...)):
    content = await file.read()
    df      = read_file(content, file.filename or "upload")
    if df is None:
        raise HTTPException(400, "Could not read file.")

    df     = normalize_columns(df, COL_MAP)
    result = UploadResult("subjects", total=len(df))
    engine = get_db()

    with engine.begin() as conn:
        for idx, row in df.iterrows():
            row_num = idx + 2

            code = clean_str(row.get("subject_code"), 20)
            name = clean_str(row.get("subject_name"), 150)
            dept_code = clean_str(row.get("department_code", ""))

            if not code:
                result.errors.append(f"Row {row_num}: missing subject_code")
                result.skipped += 1; continue
            if not name:
                result.errors.append(f"Row {row_num} ({code}): missing subject_name")
                result.skipped += 1; continue
            if not dept_code:
                result.errors.append(f"Row {row_num} ({code}): missing department_code")
                result.skipped += 1; continue

            dept_id = get_dept_id(conn, dept_code)
            if not dept_id:
                result.errors.append(f"Row {row_num} ({code}): dept '{dept_code}' not found")
                result.skipped += 1; continue

            sem   = clean_int(row.get("semester_number"))
            stype = clean_str(row.get("subject_type")) or "Theory"
            if stype not in VALID_TYPES:
                stype = "Theory"

            existing = conn.execute(
                text("SELECT subject_id FROM subjects WHERE subject_code = :c"),
                {"c": code.upper()}
            ).fetchone()

            conn.execute(text("""
                INSERT INTO subjects (
                    subject_code, subject_name, department_id, semester_number,
                    subject_type, lecture_hrs, tutorial_hrs, practical_hrs, credits
                ) VALUES (
                    :code, :name, :dept_id, :sem,
                    :stype, :l, :t, :p, :c
                )
                ON CONFLICT (subject_code) DO UPDATE SET
                    subject_name    = EXCLUDED.subject_name,
                    department_id   = EXCLUDED.department_id,
                    semester_number = EXCLUDED.semester_number,
                    subject_type    = EXCLUDED.subject_type,
                    lecture_hrs     = EXCLUDED.lecture_hrs,
                    tutorial_hrs    = EXCLUDED.tutorial_hrs,
                    practical_hrs   = EXCLUDED.practical_hrs,
                    credits         = EXCLUDED.credits
            """), {
                "code":  code.upper(), "name": name,
                "dept_id": dept_id,   "sem":  sem,
                "stype": stype,
                "l": clean_int(row.get("lecture_hrs"))   or 0,
                "t": clean_int(row.get("tutorial_hrs"))  or 0,
                "p": clean_int(row.get("practical_hrs")) or 0,
                "c": clean_int(row.get("credits"))       or 0,
            })

            if existing: result.updated += 1
            else:        result.inserted += 1

    return result.dict()
