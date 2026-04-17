"""
routers/students.py
Student-related endpoints:
  GET /api/students              → Student list with optional filters
  GET /api/students/{reg_no}     → Full student profile (detail page)
  GET /api/summary               → HOD dashboard summary stats
"""
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Depends
from core.sql_executor import get_executor
from routers.auth import get_current_user, require_department_code

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Students"])

# Shared semester expression
_SEM_EXPR = """(
    (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END
)"""


@router.get("/api/students")
async def list_students(
    status:         str | None = Query(None, description="Active / Passed Out / Discontinued"),
    hostel:         str | None = Query(None, description="Day Scholar / Hosteller"),
    admission_year: int | None = Query(None),
    semester:       int | None = Query(None, description="Filter by current semester (1-8)"),
    role:           Literal["hod", "staff"] = Query("hod"),
    current_user:   dict = Depends(get_current_user)
):
    """Get student list with optional filters."""
    dept = current_user.get("department_code")
    filters = ["d.department_code = :dept"]
    if status:
        filters.append(f"s.status = '{status}'")
    if hostel:
        filters.append(f"s.hostel_status = '{hostel}'")
    if admission_year:
        filters.append(f"s.admission_year = {admission_year}")
    if semester:
        filters.append(f"{_SEM_EXPR} = {semester}")
    where = " AND ".join(filters)
    sql = f"""
        SELECT s.register_number, s.name, s.gender, s.admission_year,
               s.hostel_status, s.status, s.contact_number, s.email, s.cgpa,
               {_SEM_EXPR} AS current_semester
        FROM students s
        JOIN departments d ON s.department_id = d.department_id
        WHERE {where}
        ORDER BY s.admission_year DESC, s.register_number
        LIMIT 200;
    """
    result = await get_executor().run(sql, params={"dept": dept}, role=role)
    if result.error:
        raise HTTPException(500, result.error)
    return {"students": result.rows, "count": result.row_count}


@router.get("/api/students/{register_number}")
async def get_student_detail(
    register_number: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Full student profile:
    - personal info
    - semester-wise GPA
    - active arrears
    - all subject attempts history
    - timetable for current semester
    """
    dept = current_user.get("department_code")

    # ── 1. Basic profile ────────────────────────────────────────────────────
    profile_sql = f"""
        SELECT
            s.student_id, s.register_number, s.name, s.gender,
            s.date_of_birth, s.contact_number, s.email,
            s.admission_year, s.section, s.hostel_status, s.status, s.cgpa,
            d.department_code, d.department_name,
            {_SEM_EXPR} AS current_semester
        FROM students s
        JOIN departments d ON s.department_id = d.department_id
        WHERE s.register_number = :reg
          AND d.department_code = :dept;
    """
    profile_res = await get_executor().run(profile_sql, params={"reg": register_number, "dept": dept})
    if profile_res.error or not profile_res.rows:
        raise HTTPException(404, "Student not found")
    student = profile_res.rows[0]
    student_id = student["student_id"]

    # ── 2. Semester-wise GPA ─────────────────────────────────────────────────
    gpa_sql = """
        SELECT semester_number, gpa, cgpa_upto
        FROM student_semester_gpa
        WHERE student_id = :sid
        ORDER BY semester_number;
    """
    gpa_res = await get_executor().run(gpa_sql, params={"sid": student_id})
    gpa_history = gpa_res.rows if not gpa_res.error else []

    # ── 3. Active arrears ────────────────────────────────────────────────────
    arrears_sql = """
        WITH latest AS (
            SELECT student_id, subject_id, exam_year, exam_month, grade,
                   ROW_NUMBER() OVER(
                       PARTITION BY student_id, subject_id
                       ORDER BY exam_year DESC,
                                CASE WHEN exam_month='NOV' THEN 11 WHEN exam_month='MAY' THEN 5 ELSE 1 END DESC
                   ) AS rn
            FROM student_subject_attempts
        )
        SELECT sub.subject_code, sub.subject_name, sub.semester_number,
               l.exam_month, l.exam_year, l.grade
        FROM latest l
        JOIN subjects sub ON l.subject_id = sub.subject_id
        WHERE l.student_id = :sid AND l.rn = 1 AND l.grade IN ('U', 'AB')
        ORDER BY sub.semester_number, sub.subject_code;
    """
    arrears_res = await get_executor().run(arrears_sql, params={"sid": student_id})
    arrears = arrears_res.rows if not arrears_res.error else []

    # ── 4. Full attempt history ──────────────────────────────────────────────
    history_sql = """
        SELECT sub.subject_code, sub.subject_name, sub.semester_number,
               ssa.exam_year, ssa.exam_month, ssa.grade
        FROM student_subject_attempts ssa
        JOIN subjects sub ON ssa.subject_id = sub.subject_id
        WHERE ssa.student_id = :sid
        ORDER BY sub.semester_number, sub.subject_code, ssa.exam_year DESC,
                 CASE WHEN ssa.exam_month='NOV' THEN 11 WHEN ssa.exam_month='MAY' THEN 5 ELSE 1 END DESC;
    """
    history_res = await get_executor().run(history_sql, params={"sid": student_id})
    attempt_history = history_res.rows if not history_res.error else []

    # ── 5. Current semester timetable ────────────────────────────────────────
    current_sem = student.get("current_semester", 0)
    section = student.get("section", "A")
    timetable_sql = """
        SELECT ct.day_of_week, ct.hour_number, ct.activity,
               COALESCE(ts.label,
                   to_char(ts.start_time,'HH24:MI') || '-' || to_char(ts.end_time,'HH24:MI')
               ) AS time_range,
               s.subject_code, s.subject_name, s.subject_type,
               trim(COALESCE(f.title || ' ', '') || COALESCE(f.full_name, '')) AS faculty_name
        FROM class_timetable ct
        LEFT JOIN subjects   s  ON ct.subject_id  = s.subject_id
        LEFT JOIN faculty    f  ON ct.faculty_id  = f.faculty_id
        LEFT JOIN time_slots ts ON ts.hour_number = ct.hour_number
        JOIN  departments    d  ON ct.department_id = d.department_id
        WHERE ct.sem_batch = :sem
          AND ct.section   = :section
          AND d.department_code = :dept
        ORDER BY
            CASE ct.day_of_week
                WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 ELSE 6
            END, ct.hour_number;
    """
    tt_res = await get_executor().run(
        timetable_sql,
        params={"sem": current_sem, "section": section, "dept": dept}
    )
    timetable = tt_res.rows if not tt_res.error else []

    return {
        "student": student,
        "gpa_history": gpa_history,
        "arrears": arrears,
        "attempt_history": attempt_history,
        "timetable": timetable,
    }


@router.get("/api/summary")
async def department_summary(current_user: dict = Depends(get_current_user)):
    """HOD dashboard summary stats."""
    dept = current_user.get("department_code")
    sql = """
        SELECT
            (SELECT COUNT(*) FROM students s
             JOIN departments d ON s.department_id=d.department_id
             WHERE d.department_code=:dept AND s.status='Active')          AS active_students,
            (SELECT COUNT(*) FROM students s
             JOIN departments d ON s.department_id=d.department_id
             WHERE d.department_code=:dept AND s.hostel_status='Hosteller') AS hostellers,
            (
                SELECT COUNT(*)
                FROM vw_arrear_count v
                JOIN students s ON s.register_number = v.register_number
                JOIN departments d ON s.department_id=d.department_id
                WHERE d.department_code=:dept AND v.active_arrear_count > 0
            )                                                               AS students_with_arrears,
            (
                SELECT ROUND(AVG(ssg.gpa),2)
                FROM student_semester_gpa ssg
                JOIN students s ON s.student_id = ssg.student_id
                JOIN departments d ON s.department_id=d.department_id
                WHERE d.department_code=:dept
            )                                                               AS dept_avg_gpa,
             (SELECT COUNT(*) FROM faculty f
             JOIN departments d ON f.department_id=d.department_id
             WHERE d.department_code=:dept AND f.is_active=TRUE)           AS total_faculty;
    """
    result = await get_executor().run(sql, params={"dept": dept})
    if result.error:
        raise HTTPException(500, result.error)
    return result.rows[0] if result.rows else {}