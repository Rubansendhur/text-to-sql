"""
routers/stats.py
Admin analytics endpoints:
  GET /api/admin/stats → Overall + department-wise performance stats (admin only)
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from core.sql_executor import get_executor
from routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Stats"])


def require_admin(user: dict):
    if user.get("role") not in ["admin", "central-admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/api/admin/stats")
async def get_admin_stats(current_user: dict = Depends(get_current_user)):
    """
    Returns system-wide + department-wise performance statistics.
    Accessible only by admin / central-admin.
    """
    require_admin(current_user)
    executor = get_executor()

    # ── 1. Global totals ────────────────────────────────────────────────────
    totals_sql = """
        SELECT
            (SELECT COUNT(*) FROM students WHERE status = 'active')          AS total_students,
            (SELECT COUNT(*) FROM faculty  WHERE is_active = TRUE)           AS total_faculty,
            (SELECT ROUND(AVG(cgpa), 2) FROM students WHERE status = 'active') AS avg_gpa,
            (
                SELECT COUNT(DISTINCT student_id)
                FROM (
                    SELECT student_id, subject_id,
                           ROW_NUMBER() OVER(
                               PARTITION BY student_id, subject_id
                               ORDER BY exam_year DESC,
                                        CASE WHEN exam_month='NOV' THEN 11
                                             WHEN exam_month='MAY' THEN 5 ELSE 1 END DESC
                           ) AS rn, grade
                    FROM student_subject_attempts
                ) latest
                WHERE rn = 1 AND grade IN ('U', 'AB')
            ) AS total_arrears,
            (SELECT COUNT(*) FROM departments) AS total_departments;
    """
    totals_res = await executor.run(totals_sql)
    if totals_res.error:
        raise HTTPException(500, totals_res.error)
    totals = totals_res.rows[0] if totals_res.rows else {}

    # ── 2. Department-wise performance ──────────────────────────────────────
    dept_sql = """
        WITH active_arrears AS (
            SELECT student_id
            FROM (
                SELECT student_id, subject_id, grade,
                       ROW_NUMBER() OVER(
                           PARTITION BY student_id, subject_id
                           ORDER BY exam_year DESC,
                                    CASE WHEN exam_month='NOV' THEN 11
                                         WHEN exam_month='MAY' THEN 5 ELSE 1 END DESC
                       ) AS rn
                FROM student_subject_attempts
            ) x WHERE rn = 1 AND grade IN ('U', 'AB')
        )
        SELECT
            d.department_code                                        AS dept,
            d.department_name,
            COUNT(DISTINCT s.student_id)                            AS students,
            COUNT(DISTINCT s.student_id) FILTER (WHERE s.hostel_status = 'Hosteller') AS hostellers,
            COUNT(DISTINCT s.student_id) FILTER (WHERE s.hostel_status = 'Day Scholar') AS day_scholars,
            COUNT(DISTINCT f.faculty_id)                            AS faculty,
            ROUND(AVG(s.cgpa), 2)                                   AS avg_gpa,
            MAX(s.cgpa)                                             AS max_gpa,
            MIN(s.cgpa) FILTER (WHERE s.cgpa > 0)                  AS min_gpa,
            COUNT(DISTINCT aa.student_id)                           AS students_with_arrears,
            CASE WHEN COUNT(DISTINCT s.student_id) > 0
                 THEN ROUND(
                     COUNT(DISTINCT aa.student_id)::numeric /
                     COUNT(DISTINCT s.student_id) * 100, 1)
                 ELSE 0 END                                         AS arrear_rate_pct,
            -- Students per faculty ratio
            CASE WHEN COUNT(DISTINCT f.faculty_id) > 0
                 THEN ROUND(COUNT(DISTINCT s.student_id)::numeric /
                            COUNT(DISTINCT f.faculty_id), 1)
                 ELSE NULL END                                      AS students_per_faculty
        FROM departments d
        LEFT JOIN students s
            ON s.department_id = d.department_id AND s.status = 'active'
        LEFT JOIN faculty f
            ON f.department_id = d.department_id AND f.is_active = TRUE
        LEFT JOIN active_arrears aa
            ON aa.student_id = s.student_id
        GROUP BY d.department_id, d.department_code, d.department_name
        ORDER BY d.department_code;
    """
    dept_res = await executor.run(dept_sql)
    if dept_res.error:
        raise HTTPException(500, dept_res.error)
    departments = dept_res.rows

    # ── 3. Semester-wise GPA across all departments ──────────────────────────
    sem_gpa_sql = """
        SELECT
            d.department_code AS dept,
            ssg.semester_number,
            ROUND(AVG(ssg.gpa), 2) AS avg_gpa,
            COUNT(ssg.student_id) AS students
        FROM student_semester_gpa ssg
        JOIN students s ON s.student_id = ssg.student_id
        JOIN departments d ON s.department_id = d.department_id
        GROUP BY d.department_code, ssg.semester_number
        ORDER BY d.department_code, ssg.semester_number;
    """
    sem_gpa_res = await executor.run(sem_gpa_sql)
    semester_gpa = sem_gpa_res.rows if not sem_gpa_res.error else []

    # ── 4. Top arrear subjects across all departments ────────────────────────
    top_arrear_subjects_sql = """
        WITH latest AS (
            SELECT student_id, subject_id, grade,
                   ROW_NUMBER() OVER(
                       PARTITION BY student_id, subject_id
                       ORDER BY exam_year DESC,
                                CASE WHEN exam_month='NOV' THEN 11
                                     WHEN exam_month='MAY' THEN 5 ELSE 1 END DESC
                   ) AS rn
            FROM student_subject_attempts
        )
        SELECT
            sub.subject_code, sub.subject_name, sub.semester_number,
            d.department_code,
            COUNT(DISTINCT l.student_id) AS active_arrear_count
        FROM latest l
        JOIN subjects sub ON l.subject_id = sub.subject_id
        JOIN students s ON l.student_id = s.student_id
        JOIN departments d ON s.department_id = d.department_id
        WHERE l.rn = 1 AND l.grade IN ('U', 'AB')
        GROUP BY sub.subject_code, sub.subject_name, sub.semester_number, d.department_code
        ORDER BY active_arrear_count DESC
        LIMIT 10;
    """
    tar_res = await executor.run(top_arrear_subjects_sql)
    top_arrear_subjects = tar_res.rows if not tar_res.error else []

    # ── 5. Batch-wise GPA trend (by admission year) ──────────────────────────
    batch_trend_sql = """
        SELECT
            s.admission_year AS batch,
            d.department_code AS dept,
            ROUND(AVG(s.cgpa), 2) AS avg_cgpa,
            COUNT(s.student_id) AS students
        FROM students s
        JOIN departments d ON s.department_id = d.department_id
        WHERE s.status = 'active' AND s.cgpa > 0
        GROUP BY s.admission_year, d.department_code
        ORDER BY s.admission_year DESC, d.department_code;
    """
    batch_res = await executor.run(batch_trend_sql)
    batch_trends = batch_res.rows if not batch_res.error else []

    # ── 6. Insights / highlights ─────────────────────────────────────────────
    insights_sql = """
        SELECT
            (
                SELECT d.department_code
                FROM departments d
                JOIN students s ON s.department_id = d.department_id
                WHERE s.status = 'active'
                GROUP BY d.department_code
                ORDER BY AVG(s.cgpa) DESC NULLS LAST
                LIMIT 1
            ) AS top_gpa_dept,
            (
                SELECT d.department_code
                FROM departments d
                JOIN students s ON s.department_id = d.department_id
                JOIN (
                    SELECT student_id FROM (
                        SELECT student_id, grade,
                               ROW_NUMBER() OVER(PARTITION BY student_id, subject_id
                                                 ORDER BY exam_year DESC,
                                                          CASE WHEN exam_month='NOV' THEN 11
                                                               WHEN exam_month='MAY' THEN 5 ELSE 1 END DESC) rn
                        FROM student_subject_attempts
                    ) x WHERE rn=1 AND grade IN ('U','AB')
                ) aa ON aa.student_id = s.student_id
                GROUP BY d.department_code
                ORDER BY COUNT(DISTINCT aa.student_id) DESC
                LIMIT 1
            ) AS max_arrears_dept,
            (
                SELECT d.department_code
                FROM departments d
                JOIN faculty f ON f.department_id = d.department_id
                WHERE f.is_active = TRUE
                GROUP BY d.department_code
                ORDER BY COUNT(f.faculty_id) DESC
                LIMIT 1
            ) AS highest_faculty_dept,
            (
                SELECT d.department_code
                FROM departments d
                JOIN students s ON s.department_id = d.department_id
                WHERE s.status = 'active'
                GROUP BY d.department_code
                ORDER BY COUNT(s.student_id) DESC
                LIMIT 1
            ) AS largest_dept;
    """
    insights_res = await executor.run(insights_sql)
    insights = insights_res.rows[0] if (not insights_res.error and insights_res.rows) else {}

    return {
        # Global
        "total_students":     totals.get("total_students"),
        "total_faculty":      totals.get("total_faculty"),
        "total_departments":  totals.get("total_departments"),
        "avg_gpa":            totals.get("avg_gpa"),
        "total_arrears":      totals.get("total_arrears"),
        # Per-department
        "departments":        departments,
        # Trends
        "semester_gpa":       semester_gpa,
        "batch_trends":       batch_trends,
        # Subject-level
        "top_arrear_subjects": top_arrear_subjects,
        # Highlights
        "top_gpa_dept":       insights.get("top_gpa_dept"),
        "max_arrears_dept":   insights.get("max_arrears_dept"),
        "highest_faculty_load": insights.get("highest_faculty_dept"),
        "largest_dept":       insights.get("largest_dept"),
    }