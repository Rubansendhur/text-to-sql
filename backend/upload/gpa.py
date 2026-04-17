"""
routers/gpa.py
────────────────────
POST /api/gpa/calculate

Calculate GPA for a specific semester
and update CGPA
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from .helpers import get_db

router = APIRouter()

GRADE_POINTS = {
    "O": 10,
    "A+": 9,
    "A": 8,
    "B+": 7,
    "B": 6,
    "C+": 5,
    "C": 4,
    "U": 0
}


# @router.post("/calculate")
def calculate_gpa(student_id: int, semester: int):

    engine = get_db()

    with engine.begin() as conn:

        # 🔹 Step 1: Fetch subject grades + credits
        rows = conn.execute(text("""
            SELECT 
                ssr.grade,
                s.subject_id
            FROM student_subject_results ssr
            JOIN subjects s ON ssr.subject_id = s.subject_id
            WHERE ssr.student_id = :student_id
              AND ssr.semester_number = :semester
        """), {
            "student_id": student_id,
            "semester": semester
        }).fetchall()

        if not rows:
            raise HTTPException(404, "No subject data found")

        total_points = 0
        total_credits = 0

        # ⚠️ You MUST add credits column in subjects table
        # assuming s.credits exists

        credit_rows = conn.execute(text("""
            SELECT subject_id, credits FROM subjects
        """)).fetchall()

        credit_map = {r[0]: r[1] for r in credit_rows}

        for grade, subject_id in rows:
            points = GRADE_POINTS.get(grade, 0)
            credits = credit_map.get(subject_id, 0)

            total_points += points * credits
            total_credits += credits

        if total_credits == 0:
            raise HTTPException(400, "Credits not configured")

        gpa = round(total_points / total_credits, 2)

        # 🔹 Step 2: UPSERT GPA (ONLY THIS SEMESTER)
        conn.execute(text("""
            INSERT INTO student_semester_gpa (student_id, semester_number, gpa)
            VALUES (:student_id, :semester, :gpa)
            ON CONFLICT (student_id, semester_number)
            DO UPDATE SET gpa = EXCLUDED.gpa
        """), {
            "student_id": student_id,
            "semester": semester,
            "gpa": gpa
        })

        # 🔹 Step 3: Calculate CGPA (ALL semesters)
        cgpa_row = conn.execute(text("""
           SUM(gpa * total_credits) / NULLIF(SUM(total_credits), 0)
            FROM student_semester_gpa
            WHERE student_id = :student_id
        """), {
            "student_id": student_id
        }).fetchone()

        cgpa = round(cgpa_row[0], 2) if cgpa_row[0] else 0

        # 🔹 Step 4: Update students table
        conn.execute(text("""
            UPDATE students
            SET cgpa = :cgpa
            WHERE student_id = :student_id
        """), {
            "cgpa": cgpa,
            "student_id": student_id
        })

    return {
        "student_id": student_id,
        "semester": semester,
        "gpa": gpa,
        "cgpa": cgpa
    }


def calculate_gpa_internal(conn, student_id, semester):

    rows = conn.execute(text("""
        SELECT ssr.grade, s.credits
        FROM student_subject_results ssr
        JOIN subjects s ON ssr.subject_id = s.subject_id
        WHERE ssr.student_id = :student_id
          AND ssr.semester_number = :semester
    """), {
        "student_id": student_id,
        "semester": semester
    }).fetchall()

    if not rows:
        return

    total_points = 0
    total_credits = 0

    for grade, credits in rows:
        points = {
            "O": 10, "A+": 9, "A": 8,
            "B+": 7, "B": 6, "C+": 5,
            "C": 4, "U": 0
        }.get(grade, 0)

        total_points += points * credits
        total_credits += credits

    if total_credits == 0:
        return

    gpa = round(total_points / total_credits, 2)

    # ✅ UPSERT GPA
    conn.execute(text("""
        INSERT INTO student_semester_gpa
        (student_id, semester_number, gpa)
        VALUES (:student_id, :semester, :gpa)
        ON CONFLICT (student_id, semester_number)
        DO UPDATE SET gpa = EXCLUDED.gpa
    """), {
        "student_id": student_id,
        "semester": semester,
        "gpa": gpa
    })

    # ✅ CGPA (weighted using subjects table)
    cgpa_row = conn.execute(text("""
        SELECT 
            SUM(g.gpa * sem_credits) / NULLIF(SUM(sem_credits), 0)
        FROM student_semester_gpa g
        JOIN (
            SELECT 
                ssr.student_id,
                ssr.semester_number,
                SUM(s.credits) AS sem_credits
            FROM student_subject_results ssr
            JOIN subjects s ON ssr.subject_id = s.subject_id
            GROUP BY ssr.student_id, ssr.semester_number
        ) c
        ON g.student_id = c.student_id 
        AND g.semester_number = c.semester_number
        WHERE g.student_id = :student_id
    """), {
        "student_id": student_id
    }).fetchone()

    cgpa = round(cgpa_row[0], 2) if cgpa_row[0] else 0

    # ✅ Update student CGPA
    conn.execute(text("""
        UPDATE students
        SET cgpa = :cgpa
        WHERE student_id = :student_id
    """), {
        "cgpa": cgpa,
        "student_id": student_id
    })