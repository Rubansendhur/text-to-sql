"""
routers/arrears.py
───────────────────
Arrear-related endpoints:
  GET /api/arrears — Students with active arrears
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Depends

from core.sql_executor import get_executor
from routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Arrears"])

_SEM_EXPR = """(
    (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END
)"""

ACTIVE_ARREARS_CTE = """
WITH latest_attempts AS (
    SELECT student_id, subject_id, exam_year, exam_month, grade,
           ROW_NUMBER() OVER(
               PARTITION BY student_id, subject_id 
               ORDER BY exam_year DESC, 
                        CASE WHEN exam_month = 'NOV' THEN 11 WHEN exam_month = 'MAY' THEN 5 ELSE 1 END DESC,
                        attempt_id DESC
           ) as rn
    FROM student_subject_attempts
),
active_arrears AS (
    SELECT student_id, subject_id, exam_year, exam_month, grade
    FROM latest_attempts
    WHERE rn = 1 AND grade IN ('U', 'AB')
)
"""

@router.get("/api/arrears/subjects")
async def list_arrear_subjects(role: Literal["hod", "staff"] = Query("hod"), current_user: dict = Depends(get_current_user)):
    """Get all subjects that currently have active arrears."""
    dept = current_user.get("department_code")
    sql = f"""
        {ACTIVE_ARREARS_CTE}
        SELECT DISTINCT sub.subject_code, sub.subject_name
        FROM active_arrears aa
        JOIN subjects sub ON aa.subject_id = sub.subject_id
        JOIN students s ON aa.student_id = s.student_id
        JOIN departments d ON s.department_id = d.department_id
        WHERE d.department_code = :dept
        ORDER BY sub.subject_code;
    """
    result = await get_executor().run(sql, params={"dept": dept}, role=role)
    if result.error:
        raise HTTPException(500, result.error)
    return {"subjects": result.rows}

@router.get("/api/arrears")
async def list_arrears(
    min_count: int = Query(1, description="Minimum number of active arrears"),
    semester:  int | None = Query(None, description="Filter by current semester (1-10)"),
    role:      Literal["hod", "staff"] = Query("hod"),
    current_user: dict = Depends(get_current_user),
):
    """Get students with active arrears."""
    dept = current_user.get("department_code")
    sem_filter = f"AND {_SEM_EXPR} = {semester}" if semester else ""
    sql = f"""
        {ACTIVE_ARREARS_CTE}
        SELECT v.register_number, v.name, v.status, v.active_arrear_count,
               {_SEM_EXPR} AS current_semester,
               s.admission_year,
               (
                   SELECT json_agg(json_build_object(
                       'subject_code', sub.subject_code,
                       'subject_name', sub.subject_name,
                       'semester_number', sub.semester_number,
                       'exam_month', aa.exam_month,
                       'exam_year', aa.exam_year
                   ) ORDER BY sub.semester_number, sub.subject_code)
                   FROM active_arrears aa
                   JOIN subjects sub ON aa.subject_id = sub.subject_id
                   WHERE aa.student_id = s.student_id
               ) AS arrear_subjects
        FROM vw_arrear_count v
        JOIN students s ON s.register_number = v.register_number
        JOIN departments d ON s.department_id = d.department_id
        WHERE v.active_arrear_count >= {min_count}
          AND d.department_code = :dept
          {sem_filter}
        ORDER BY v.active_arrear_count DESC;
    """
    result = await get_executor().run(sql, params={"dept": dept}, role=role)
    if result.error:
        raise HTTPException(500, result.error)
    return {"students": result.rows, "total": result.row_count}
