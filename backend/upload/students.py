"""
upload/students.py
──────────────────────
POST /api/upload/students

Accepts CSV or Excel with student + parent data.
Upserts into students + parents tables.

Required columns : register_number, name, department_code, admission_year
Optional columns : gender, date_of_birth, contact_number, email, section,
                   hostel_status, status,
                   father_name, mother_name,
                   father_contact_number, mother_contact_number, address
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi import BackgroundTasks

from sqlalchemy import text
from psycopg2.extras import execute_values

from .helpers import (
    get_db, read_file, normalize_columns, UploadResult,
    clean_str, clean_phone, clean_reg, clean_dob, clean_int,
    normalize_hostel, normalize_status, normalize_gender,
    get_dept_id,
)

router = APIRouter()

COL_MAP = {
    "register number":          "register_number",
    "name":                     "name",
    "gender":                   "gender",
    "date of birth":            "date_of_birth",
    "dob":                      "date_of_birth",
    "contact number":           "contact_number",
    "mobile":                   "contact_number",
    "email id":                 "email",
    "email":                    "email",
    "department code":          "department_code",
    "dept_code":                "department_code",
    "dept code":                "department_code",
    "admission year":           "admission_year",
    "section":                  "section",
    "hostel/days scholar":      "hostel_status",
    "hostel status":            "hostel_status",
    "Hostel_status (hosteller/Dayscholar)": "hostel_status",
    "hostel":                   "hostel_status",
    "status":                   "status",
    "father's name":            "father_name",
    "father name":              "father_name",
    "mother's name":            "mother_name",
    "mother name":              "mother_name",
    "father's contact number":  "father_contact_number",
    "father contact":           "father_contact_number",
    "father contact number":    "father_contact_number",
    "mother's contact number":  "mother_contact_number",
    "mother contact":           "mother_contact_number",
    "mother contact number":    "mother_contact_number",
    "address":                  "address",
}


# ── Upload API ─────────────────────────────────────────────

@router.post("/students")
async def upload_students(file: UploadFile = File(...)):
    content = await file.read()

    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 5MB)")

    df = read_file(content, file.filename or "upload")

    if df is None:
        raise HTTPException(400, "Invalid file format")

    df = normalize_columns(df, COL_MAP)
    result = UploadResult("students", total=len(df))

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

            student_rows = []
            parent_rows = []

            for idx, row in chunk.iterrows():
                row_num = idx + 2

                reg = clean_reg(row.get("register_number"))
                if not reg:
                    result.errors.append(f"Row {row_num}: invalid register_number")
                    result.skipped += 1
                    continue

                dept_code = clean_str(row.get("department_code", ""))
                if not dept_code:
                    result.errors.append(f"Row {row_num} ({reg}): missing department_code")
                    result.skipped += 1
                    continue

                dept_id = dept_map.get(dept_code.upper())
                if not dept_id:
                    result.errors.append(f"Row {row_num} ({reg}): invalid department")
                    result.skipped += 1
                    continue

                admission_year = clean_int(row.get("admission_year"))
                if not admission_year:
                    result.errors.append(f"Row {row_num} ({reg}): invalid admission_year")
                    result.skipped += 1
                    continue

                student_rows.append((
                    reg,
                    clean_str(row.get("name"), 100) or "UNKNOWN",
                    normalize_gender(row.get("gender")),
                    clean_dob(row.get("date_of_birth")),
                    clean_phone(row.get("contact_number")),
                    clean_str(row.get("email"), 100),
                    dept_id,
                    admission_year,
                    clean_str(row.get("section"), 10),
                    normalize_hostel(row.get("hostel_status")),
                    normalize_status(row.get("status")),
                ))

                parent_rows.append((
                    reg,
                    clean_str(row.get("father_name"), 100),
                    clean_str(row.get("mother_name"), 100),
                    clean_phone(row.get("father_contact_number")),
                    clean_phone(row.get("mother_contact_number")),
                    clean_str(row.get("address")),
                ))

            # ── BULK INSERT STUDENTS ─────────────────────────

            if student_rows:
                cursor = conn.connection.cursor()

                cursor.execute("""
                    CREATE TEMP TABLE temp_students (
                        register_number TEXT,
                        name TEXT,
                        gender TEXT,
                        date_of_birth TIMESTAMP,
                        contact_number TEXT,
                        email TEXT,
                        department_id INT,
                        admission_year INT,
                        section TEXT,
                        hostel_status TEXT,
                        status TEXT
                    ) ON COMMIT DROP;
                """)

                execute_values(
                    cursor,
                    "INSERT INTO temp_students VALUES %s",
                    student_rows
                )

                student_res = conn.execute(text("""
                    INSERT INTO students (
                        register_number, name, gender, date_of_birth,
                        contact_number, email, department_id,
                        admission_year, section, hostel_status, status
                    )
                    SELECT * FROM temp_students
                    ON CONFLICT (register_number) DO UPDATE SET
                        name = EXCLUDED.name,
                        gender = EXCLUDED.gender,
                        date_of_birth = EXCLUDED.date_of_birth,
                        contact_number = EXCLUDED.contact_number,
                        email = EXCLUDED.email,
                        department_id = EXCLUDED.department_id,
                        admission_year = EXCLUDED.admission_year,
                        section = EXCLUDED.section,
                        hostel_status = EXCLUDED.hostel_status,
                        status = EXCLUDED.status
                    WHERE (
                        students.name IS DISTINCT FROM EXCLUDED.name OR
                        students.gender IS DISTINCT FROM EXCLUDED.gender OR
                        students.date_of_birth IS DISTINCT FROM EXCLUDED.date_of_birth OR
                        students.contact_number IS DISTINCT FROM EXCLUDED.contact_number OR
                        students.email IS DISTINCT FROM EXCLUDED.email OR
                        students.department_id IS DISTINCT FROM EXCLUDED.department_id OR
                        students.admission_year IS DISTINCT FROM EXCLUDED.admission_year OR
                        students.section IS DISTINCT FROM EXCLUDED.section OR
                        students.hostel_status IS DISTINCT FROM EXCLUDED.hostel_status OR
                        students.status IS DISTINCT FROM EXCLUDED.status
                    )
                    RETURNING (xmax = 0) AS inserted;
                """)).fetchall()

                processed = len(student_rows)

                for row in student_res:
                    if row.inserted:
                        result.inserted += 1
                    else:
                        result.updated += 1

                result.skipped += (processed - len(student_res))

            # ── BULK INSERT PARENTS ─────────────────────────

            if parent_rows:
                cursor = conn.connection.cursor()

                execute_values(
                    cursor,
                    """
                    INSERT INTO parents (
                        student_id, father_name, mother_name,
                        father_contact_number, mother_contact_number, address
                    )
                    SELECT s.student_id, p.fn, p.mn, p.fc, p.mc, p.addr
                    FROM (VALUES %s) AS p(reg, fn, mn, fc, mc, addr)
                    JOIN students s ON s.register_number = p.reg
                    ON CONFLICT (student_id) DO UPDATE SET
                        father_name = EXCLUDED.father_name,
                        mother_name = EXCLUDED.mother_name,
                        father_contact_number = EXCLUDED.father_contact_number,
                        mother_contact_number = EXCLUDED.mother_contact_number,
                        address = EXCLUDED.address
                """,
                    parent_rows
                )

    return result.dict()