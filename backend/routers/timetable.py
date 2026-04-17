"""
routers/timetable.py
─────────────────────
Timetable endpoints:
  GET  /api/timetable/{semester}             — Timetable via view (legacy)
  GET  /api/timetable/sem/{sem}              — Class timetable for a dept+sem+section
  GET  /api/timetable/sections               — Available sections for a dept+sem
  POST /api/timetable/save                   — Bulk-save a dept+sem+section timetable
"""

import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from core.sql_executor import get_executor
from upload.helpers    import get_db
from routers.auth      import get_current_user, is_central_admin, require_department_code

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Timetable"])


# ── Request models ────────────────────────────────────────────────────────────

class SlotSave(BaseModel):
    day_of_week: str
    hour_number: int
    faculty_id:  int | None
    subject_id:  int | None
    activity:    str | None
    sem_batch:   int | None


class TimetableSave(BaseModel):
    sem_batch:     int
    department_id: int
    section:       str = "A"
    slots:         list[SlotSave]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_dept_id(conn, department_code: str) -> int | None:
    """Resolve department_code → department_id."""
    row = conn.execute(
        text("SELECT department_id FROM departments WHERE department_code = :code"),
        {"code": department_code},
    ).fetchone()
    return row[0] if row else None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/timetable/sections")
def get_timetable_sections(
    department_id: int = Query(...),
    sem_batch:     int = Query(...),
    current_user:  dict = Depends(get_current_user),
):
    """Return the distinct sections that already have data for a dept+sem."""
    try:
        engine = get_db()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT section
                FROM class_timetable
                WHERE department_id = :dept AND sem_batch = :sem
                ORDER BY section
            """), {"dept": department_id, "sem": sem_batch}).fetchall()
            sections = [r[0] for r in rows]
            # Always include 'A' as default
            if not sections:
                sections = ["A"]
            return {"sections": sections}
    except Exception as e:
        logger.error(f"Error fetching sections: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sections")


@router.get("/api/timetable/{semester}")
async def get_timetable(
    semester:      int,
    department_id: int | None = Query(None),
    section:       str        = Query("A"),
    current_user:  dict       = Depends(get_current_user),
):
    """Get timetable for a specific semester, department, and section."""
    is_admin = is_central_admin(current_user)
    dept_code = require_department_code(current_user) if not is_admin else None

    # Resolve dept_id for non-admin users from their dept_code
    engine = get_db()
    with engine.connect() as conn:
        if not is_admin and not department_id:
            department_id = _resolve_dept_id(conn, dept_code)

    sql = """
        SELECT
            ct.day_of_week,
            ct.hour_number,
            COALESCE(ts.label, to_char(ts.start_time, 'HH24:MI') || '-' || to_char(ts.end_time, 'HH24:MI')) AS time_range,
            s.subject_code AS code,
            s.subject_name AS subject,
            s.subject_type,
            trim(COALESCE(f.title || ' ', '') || COALESCE(f.full_name, '')) AS faculty_name,
            NULL::text AS lecture_hall,
            ct.activity AS notes
        FROM class_timetable ct
        LEFT JOIN subjects s   ON ct.subject_id  = s.subject_id
        LEFT JOIN faculty f    ON ct.faculty_id   = f.faculty_id
        LEFT JOIN time_slots ts ON ts.hour_number = ct.hour_number
        WHERE ct.sem_batch    = :semester
          AND ct.section      = :section
          AND (:dept_id IS NULL OR ct.department_id = :dept_id)
          AND (:is_admin OR ct.department_id = :dept_id)
        ORDER BY
            CASE ct.day_of_week
                WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5
            END,
            ct.hour_number;
    """
    result = await get_executor().run(
        sql,
        params={"semester": semester, "section": section,
                "is_admin": is_admin, "dept_id": department_id},
    )
    if result.error:
        raise HTTPException(500, result.error)
    return {"semester": semester, "slots": result.rows}


@router.get("/api/timetable/sem/{sem}")
def get_semester_timetable(
    sem:           int,
    department_id: int | None = Query(None),
    section:       str        = Query("A"),
    current_user:  dict       = Depends(get_current_user),
):
    """Get class timetable for a semester, department, and section."""
    try:
        is_admin  = is_central_admin(current_user)
        dept_code = require_department_code(current_user) if not is_admin else None
        engine    = get_db()

        with engine.connect() as conn:
            # HOD: resolve their dept_id automatically
            if not is_admin and not department_id:
                department_id = _resolve_dept_id(conn, dept_code)

            query = text("""
                SELECT
                    ct.day_of_week, ct.hour_number, ct.activity,
                    ct.sem_batch, ct.section, ct.department_id,
                    ct.faculty_id,
                    f.title, f.full_name AS faculty_name,
                    ct.subject_id,
                    s.subject_code, s.subject_name, s.subject_type
                FROM class_timetable ct
                LEFT JOIN faculty f  ON ct.faculty_id  = f.faculty_id
                LEFT JOIN subjects s ON ct.subject_id  = s.subject_id
                WHERE ct.sem_batch     = :sem
                  AND ct.section       = :section
                  AND (:is_admin OR ct.department_id = :dept_id)
                  AND (:dept_id IS NULL OR ct.department_id = :dept_id)
                ORDER BY
                    CASE ct.day_of_week
                        WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                        WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 ELSE 6
                    END, ct.hour_number
            """)
            result = conn.execute(query, {
                "sem":      sem,
                "section":  section,
                "is_admin": is_admin,
                "dept_id":  department_id,
            })
            slots = [dict(row._mapping) for row in result]
            return {"slots": slots, "section": section, "department_id": department_id}
    except Exception as e:
        logger.error(f"Error fetching sem timetable: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch timetable")


@router.post("/api/timetable/save")
def save_semester_timetable(
    data:         TimetableSave,
    current_user: dict = Depends(get_current_user),
):
    """Bulk-save (replace) a dept+semester+section timetable."""
    try:
        is_admin  = is_central_admin(current_user)
        dept_code = require_department_code(current_user) if not is_admin else None
        sem       = data.sem_batch
        dept_id   = data.department_id
        section   = data.section
        engine    = get_db()

        with engine.begin() as conn:
            # Non-admin must own the department they're writing to
            if not is_admin:
                user_dept_id = _resolve_dept_id(conn, dept_code)
                if user_dept_id != dept_id:
                    raise HTTPException(status_code=403,
                                        detail="Not allowed to modify another department's timetable")

            # Delete existing slots for this exact dept+sem+section
            conn.execute(
                text("""DELETE FROM class_timetable
                         WHERE sem_batch = :sem
                           AND department_id = :dept_id
                           AND section = :section"""),
                {"sem": sem, "dept_id": dept_id, "section": section},
            )

            for s in data.slots:
                if s.subject_id or s.activity:
                    if not is_admin:
                        # Validate subject belongs to this dept
                        if s.subject_id:
                            subject_ok = conn.execute(text("""
                                SELECT 1 FROM subjects sub
                                WHERE sub.subject_id = :sid
                                  AND sub.department_id = :dept_id
                            """), {"sid": s.subject_id, "dept_id": dept_id}).fetchone()
                            if not subject_ok:
                                raise HTTPException(403,
                                    "Subject does not belong to your department")
                        # Validate faculty belongs to this dept
                        if s.faculty_id:
                            faculty_ok = conn.execute(text("""
                                SELECT 1 FROM faculty f
                                WHERE f.faculty_id = :fid
                                  AND f.department_id = :dept_id
                            """), {"fid": s.faculty_id, "dept_id": dept_id}).fetchone()
                            if not faculty_ok:
                                raise HTTPException(403,
                                    "Faculty does not belong to your department")

                    conn.execute(text("""
                        INSERT INTO class_timetable
                            (sem_batch, department_id, section,
                             day_of_week, hour_number, subject_id, faculty_id, activity)
                        VALUES
                            (:sem, :dept_id, :section, :d, :h, :sub, :fid, :act)
                        ON CONFLICT (department_id, sem_batch, section, day_of_week, hour_number)
                        WHERE department_id IS NOT NULL
                        DO UPDATE SET
                            subject_id = EXCLUDED.subject_id,
                            faculty_id = EXCLUDED.faculty_id,
                            activity   = EXCLUDED.activity
                    """), {
                        "sem": sem, "dept_id": dept_id, "section": section,
                        "d": s.day_of_week, "h": s.hour_number,
                        "sub": s.subject_id, "fid": s.faculty_id, "act": s.activity,
                    })

        return {"message": "Timetable saved successfully",
                "department_id": dept_id, "section": section, "slots": len(data.slots)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving timetable: {e}")
        raise HTTPException(status_code=500, detail="Failed to save timetable")
