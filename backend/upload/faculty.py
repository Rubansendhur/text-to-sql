"""
upload/faculty.py
─────────────────────
POST /api/upload/faculty

Required : title, full_name
Optional : email, phone, designation, is_hod, department_code
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import text
from psycopg2.extras import execute_values

from .helpers import (
    get_db, read_file, normalize_columns, UploadResult,
    clean_str, clean_phone,
)

router = APIRouter()

COL_MAP = {
    "title":            "title",
    "full name":        "full_name",
    "name":             "full_name",
    "email":            "email",
    "phone":            "phone",
    "mobile":           "phone",
    "contact":          "phone",
    "designation":      "designation",
    "is hod":           "is_hod",
    "hod":              "is_hod",
    "is_hod":           "is_hod",
    "department code":  "department_code",
    "dept_code":        "department_code",
    "dept code":        "department_code",
}

title_map = {
    "dr": "Dr.",
    "dr.": "Dr.",
    "mr": "Mr.",
    "mr.": "Mr.",
    "ms": "Ms.",
    "ms.": "Ms.",
    "mrs": "Mrs.",
    "mrs.": "Mrs.",
    "prof": "Prof.",
    "prof.": "Prof.",
    "DR": "Dr.",
    "MR": "Mr.",
    "MS": "Ms.",
    "MRS": "Mrs.",
    "PROF": "Prof.",
}

VALID_TITLES       = {"Dr.", "Ms.", "Mr.", "Mrs.", "Prof."}


@router.post("/faculty")
async def upload_faculty(file: UploadFile = File(...)):
    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large")

    df = read_file(content, file.filename or "upload")
    if df is None:
        raise HTTPException(400, "Could not read file")

    df = normalize_columns(df, COL_MAP)
    result = UploadResult("faculty", total=len(df))
    engine = get_db()

    with engine.begin() as conn:

        # 🔥 Cache departments
        dept_map = {
            row[0].strip().upper(): row[1]
            for row in conn.execute(
                text("SELECT department_code, department_id FROM departments")
            )
        }

        CHUNK_SIZE = 500

        for start in range(0, len(df), CHUNK_SIZE):
            chunk = df.iloc[start:start + CHUNK_SIZE]

            faculty_rows = []

            for idx, row in chunk.iterrows():
                row_num = idx + 2

                title = clean_str(row.get("title"), 10)
                name = clean_str(row.get("full_name"), 150)

                if not title:
                    result.errors.append(f"Row {row_num}: missing title")
                    result.skipped += 1
                    continue

                if not name:
                    result.errors.append(f"Row {row_num}: missing full_name")
                    result.skipped += 1
                    continue

                # normalize title
                if not title.endswith("."):
                    title += "."

                if title not in VALID_TITLES:
                    result.errors.append(f"Row {row_num} ({name}): invalid title")
                    result.skipped += 1
                    continue

                desig = clean_str(row.get("designation"), 100)
                if desig is None:
                   raise HTTPException(400, f"Row {row_num} ({name}): no designation provided")

                is_hod_raw = str(row.get("is_hod", "false")).strip().lower()
                is_hod = is_hod_raw in ("true", "1", "yes")

                dept_code = clean_str(row.get("department_code"))
                dept_id = dept_map.get(dept_code.upper()) if dept_code else None

                faculty_rows.append((
                    title,
                    name,
                    clean_str(row.get("email"), 150),
                    clean_phone(row.get("phone")),
                    dept_id,
                    desig,
                    is_hod
                ))

            # ── BULK INSERT ─────────────────────────

            if faculty_rows:
                cursor = conn.connection.cursor()

                cursor.execute("""
                    CREATE TEMP TABLE temp_faculty (
                        title TEXT,
                        full_name TEXT,
                        email TEXT,
                        phone TEXT,
                        department_id INT,
                        designation TEXT,
                        is_hod BOOLEAN
                    ) ON COMMIT DROP;
                """)

                execute_values(
                    cursor,
                    "INSERT INTO temp_faculty VALUES %s",
                    faculty_rows
                )

                res = conn.execute(text("""
                    INSERT INTO faculty (
                        title, full_name, email, phone,
                        department_id, designation, is_hod
                    )
                    SELECT * FROM temp_faculty
                    ON CONFLICT (title, full_name) DO UPDATE SET
                        email = EXCLUDED.email,
                        phone = EXCLUDED.phone,
                        department_id = EXCLUDED.department_id,
                        designation = EXCLUDED.designation,
                        is_hod = EXCLUDED.is_hod
                    WHERE (
                        faculty.email IS DISTINCT FROM EXCLUDED.email OR
                        faculty.phone IS DISTINCT FROM EXCLUDED.phone OR
                        faculty.department_id IS DISTINCT FROM EXCLUDED.department_id OR
                        faculty.designation IS DISTINCT FROM EXCLUDED.designation OR
                        faculty.is_hod IS DISTINCT FROM EXCLUDED.is_hod
                    )
                    RETURNING (xmax = 0) AS inserted;
                """)).fetchall()

                processed = len(faculty_rows)

                for row in res:
                    if row.inserted:
                        result.inserted += 1
                    else:
                        result.updated += 1

                result.skipped += (processed - len(res))

    return result.dict()