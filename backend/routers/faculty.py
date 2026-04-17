"""
routers/faculty.py
Faculty-related endpoints:
  GET  /api/faculty                        → All active faculty (own dept)
  GET  /api/faculty/all                    → All faculty (cross-dept)
  GET  /api/faculty/{faculty_id}           → Full faculty profile
  GET  /api/faculty/{faculty_id}/timetable → Faculty timetable
  POST /api/faculty/{faculty_id}/timetable → Update a faculty timetable slot
"""
from ast import Dict, List
import logging
from typing import List, Dict
from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy import text
from core.sql_executor import get_executor
from routers.auth import get_current_user, is_dept_admin, require_department_code
from upload.helpers    import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Faculty"])


@router.get("/api/faculty")
async def list_faculty(current_user: dict = Depends(get_current_user)):
    """Get active faculty for the user's own department."""
    dept = current_user.get("department_code")
    sql = """
        SELECT f.faculty_id, f.title, f.full_name, f.email, f.phone, f.designation,
               f.is_hod, f.is_active, d.department_code, d.department_name
        FROM faculty f
        JOIN departments d ON f.department_id = d.department_id
        WHERE f.is_active = TRUE AND d.department_code = :dept
        ORDER BY f.full_name ASC;
    """
    result = await get_executor().run(sql, params={"dept": dept})
    if result.error:
        raise HTTPException(500, result.error)
    return {"faculty": result.rows}


@router.get("/api/faculty/all")
async def list_all_faculty(current_user: dict = Depends(get_current_user)):
    """Get all active faculty across every department (for cross-dept timetable assignment)."""
    sql = """
        SELECT f.faculty_id, f.title, f.full_name, f.email, f.phone, f.designation,
               f.is_hod, f.is_active, d.department_code, d.department_name,
               d.department_id
        FROM faculty f
        JOIN departments d ON f.department_id = d.department_id
        WHERE f.is_active = TRUE
        ORDER BY d.department_code ASC, f.full_name ASC;
    """
    result = await get_executor().run(sql)
    if result.error:
        raise HTTPException(500, result.error)
    return {"faculty": result.rows}


@router.get("/api/faculty/{faculty_id}/profile")
async def get_faculty_profile(faculty_id: int, current_user: dict = Depends(get_current_user)):
    """
    Full faculty profile:
    - personal / contact info
    - subjects they teach (from timetable)
    - workload summary (hours/week per day)
    - weekly timetable
    """
    is_admin = is_dept_admin(current_user)
    dept = require_department_code(current_user) if not is_admin else None

    # ── 1. Basic info ────────────────────────────────────────────────────────
    info_sql = """
        SELECT f.faculty_id, f.title, f.full_name, f.email, f.phone,
               f.designation, f.is_hod, f.is_active,
               d.department_code, d.department_name
        FROM faculty f
        JOIN departments d ON f.department_id = d.department_id
        WHERE f.faculty_id = :fid
          AND (:is_admin OR d.department_code = :dept);
    """
    info_res = await get_executor().run(
        info_sql, params={"fid": faculty_id, "is_admin": is_admin, "dept": dept}
    )
    if info_res.error or not info_res.rows:
        raise HTTPException(404, "Faculty not found")
    faculty = info_res.rows[0]

    # ── 2. Weekly timetable ─────────────────────────────────────────────────
    tt_sql = """
        SELECT ft.day_of_week, ts.hour_number, ts.start_time, ts.end_time,
               ts.label AS time_range,
               s.subject_code, s.subject_name, s.subject_type,
               ft.activity, ft.sem_batch
        FROM faculty_timetable ft
        JOIN time_slots ts ON ft.slot_id = ts.slot_id
        LEFT JOIN subjects s ON ft.subject_id = s.subject_id
        WHERE ft.faculty_id = :fid
        ORDER BY
            CASE ft.day_of_week
                WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5
            END, ts.hour_number;
    """
    tt_res = await get_executor().run(tt_sql, params={"fid": faculty_id})
    timetable = tt_res.rows if not tt_res.error else []

    # ── 3. Subjects taught (distinct) ───────────────────────────────────────
    subjects_sql = """
        SELECT DISTINCT s.subject_code, s.subject_name, s.semester_number, s.subject_type
        FROM faculty_timetable ft
        JOIN subjects s ON ft.subject_id = s.subject_id
        WHERE ft.faculty_id = :fid
        ORDER BY s.semester_number, s.subject_code;
    """
    subj_res = await get_executor().run(subjects_sql, params={"fid": faculty_id})
    subjects_taught = subj_res.rows if not subj_res.error else []

    # ── 4. Workload: total teaching hours per week ───────────────────────────
    workload_sql = """
        SELECT
            COUNT(*) FILTER (WHERE ft.subject_id IS NOT NULL) AS teaching_hours,
            COUNT(*) FILTER (WHERE ft.activity IS NOT NULL AND ft.subject_id IS NULL) AS other_hours,
            COUNT(*) AS total_slots
        FROM faculty_timetable ft
        WHERE ft.faculty_id = :fid;
    """
    wl_res = await get_executor().run(workload_sql, params={"fid": faculty_id})
    workload = wl_res.rows[0] if (not wl_res.error and wl_res.rows) else {}

    return {
        "faculty": faculty,
        "timetable": timetable,
        "subjects_taught": subjects_taught,
        "workload": workload,
    }


@router.get("/api/faculty/{faculty_id}/timetable")
async def get_faculty_timetable(faculty_id: int, current_user: dict = Depends(get_current_user)):
    """Get timetable for a specific faculty member."""
    is_admin = is_dept_admin(current_user)
    dept = require_department_code(current_user) if not is_admin else None
    sql = """
        SELECT t.day_of_week, ts.hour_number, ts.start_time, ts.end_time, ts.label AS time_range,
               s.subject_code, s.subject_name, t.activity, t.sem_batch
        FROM faculty_timetable t
        JOIN faculty f ON t.faculty_id = f.faculty_id
        JOIN departments d ON d.department_id = f.department_id
        JOIN time_slots ts ON t.slot_id = ts.slot_id
        LEFT JOIN subjects s ON t.subject_id = s.subject_id
        WHERE t.faculty_id = :faculty_id
          AND (:is_admin OR d.department_code = :dept)
        ORDER BY
            CASE t.day_of_week
                WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5
            END, ts.hour_number;
    """
    result = await get_executor().run(
        sql,
        params={"faculty_id": faculty_id, "is_admin": is_admin, "dept": dept},
    )
    if result.error:
        raise HTTPException(500, result.error)
    return {"timetable": result.rows}


@router.post("/api/faculty/{faculty_id}/timetable")
def update_faculty_timetable(
    faculty_id: int,
    payload: List[Dict] = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Bulk update timetable for a faculty member."""
    try:
        is_admin = is_dept_admin(current_user)
        dept = require_department_code(current_user) if not is_admin else None
        engine = get_db()
        with engine.begin() as conn:
            # Permission check
            if not is_admin:
                faculty_allowed = conn.execute(text("""
                    SELECT 1
                    FROM faculty f
                    JOIN departments d ON d.department_id = f.department_id
                    WHERE f.faculty_id = :fid AND d.department_code = :dept
                """), {"fid": faculty_id, "dept": dept}).fetchone()
                if not faculty_allowed:
                    raise HTTPException(status_code=403, detail="Not allowed")

            for slot in payload:
                day = slot.get("day_of_week")
                hr = slot.get("hour_number")
                sem = slot.get("sem_batch")
                sub_code = slot.get("subject_code")
                act = slot.get("activity")

                # Delete existing slot
                conn.execute(text("""
                    DELETE FROM faculty_timetable
                    WHERE faculty_id = :fid AND day_of_week = :day AND slot_id = :hr
                """), {"fid": faculty_id, "day": day, "hr": hr})

                # Insert new slot
                if sub_code or act:
                    subj_id = None
                    if sub_code:
                        row = conn.execute(text("""
                            SELECT s.subject_id
                            FROM subjects s
                            LEFT JOIN departments d ON d.department_id = s.department_id
                            WHERE s.subject_code = :code
                              AND (:is_admin OR d.department_code = :dept)
                        """), {
                            "code": sub_code,
                            "is_admin": is_admin,
                            "dept": dept
                        }).fetchone()
                        if row:
                            subj_id = row[0]
                        else:
                            raise HTTPException(
                                status_code=403,
                                detail=f"Invalid subject: {sub_code}"
                            )
                    conn.execute(text("""
                        INSERT INTO faculty_timetable
                        (faculty_id, day_of_week, slot_id, subject_id, activity, sem_batch, department_id)
                        VALUES (:fid, :day, :hr, :subjid, :act, :sem, :dept_id)
                    """), {
                        "fid": faculty_id,
                        "day": day,
                        "hr": hr,
                        "subjid": subj_id,
                        "act": act,
                        "sem": sem,
                        "dept_id": current_user.get("department_id")
                    })
        return {"message": "Timetable updated successfully"}
    except Exception as e:
        logger.error(f"Error updating timetable: {e}")
        raise HTTPException(status_code=500, detail="Failed to update timetable")