"""
routers/subjects.py
────────────────────
Subject-related endpoints:
  GET  /api/subjects/all — Full subject list for dropdowns
  POST /api/subjects     — Create a new subject
"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

from upload.helpers import get_db
from routers.auth import get_current_user

from upload.helpers import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Subjects"])


# ── Request model ─────────────────────────────────────────────────────────────

class SubjectCreate(BaseModel):
    subject_code:    str
    subject_name:    str
    semester_number: int
    subject_type:    str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/subjects/all")
def list_all_subjects(current_user: dict = Depends(get_current_user)):
    """Get all subjects for the user's department."""
    dept = current_user.get("department_code")
    try:
        engine = get_db()
        with engine.connect() as conn:
            query = text("""
                SELECT s.subject_id, s.subject_code, s.subject_name, s.semester_number, s.subject_type, s.lecture_hrs, s.tutorial_hrs, s.practical_hrs, s.credits
                FROM subjects s
                JOIN departments d ON s.department_id = d.department_id
                WHERE d.department_code = :dept
                ORDER BY s.semester_number, s.subject_code
            """)
            result = conn.execute(query, {"dept": dept})
            subjects = [dict(row._mapping) for row in result]
            return {"subjects": subjects}
    except Exception as e:
        logger.error(f"Error fetching subjects: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch subjects")


@router.post("/api/subjects")
def create_subject(subject: SubjectCreate, current_user: dict = Depends(get_current_user)):
    """Create a new subject (e.g. an elective)."""
    dept = current_user.get("department_code")
    try:
        engine = get_db()
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT subject_id FROM subjects WHERE subject_code = :code"),
                {"code": subject.subject_code}
            ).fetchone()
            if existing:
                raise HTTPException(status_code=400, detail="Subject code already exists")

            dept_row = conn.execute(
                text("SELECT department_id FROM departments WHERE department_code = :dcode"),
                {"dcode": dept}
            ).fetchone()
            if not dept_row:
                raise HTTPException(status_code=500, detail=f"Department {dept} not found in DB")
            dept_id = dept_row[0]

            conn.execute(text("""
                INSERT INTO subjects (subject_code, subject_name, department_id, semester_number, subject_type)
                VALUES (:code, :name, :dept, :sem, :type)
            """), {
                "code": subject.subject_code, "name": subject.subject_name,
                "dept": dept_id, "sem": subject.semester_number, "type": subject.subject_type
            })
            return {"message": "Subject created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subject: {e}")
        raise HTTPException(status_code=500, detail="Failed to create subject")
