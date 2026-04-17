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

class DepartmentCreate(BaseModel):
    department_code:    str
    department_name:    str


# ── Endpoints ─────────────────────────────────────────────────────────────────

# routers/subjects.py

@router.get("/api/departments/all")
def list_all_departments():
    """Return all departments for dropdown."""
    try:
        engine = get_db()

        with engine.connect() as conn:
            query = text("""
                SELECT *
                FROM departments
                ORDER BY department_code
            """)

            result = conn.execute(query)

            departments = [dict(row._mapping) for row in result]

        return {"departments": departments}

    except Exception as e:
        logger.error(f"Error fetching departments: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch departments")

