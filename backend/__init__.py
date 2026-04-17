"""
api/upload/__init__.py
──────────────────────
Combines all upload routers under a single APIRouter.
Include in main.py:

    from api.upload import upload_router
    app.include_router(upload_router, prefix="/api/upload", tags=["Upload"])
"""

from fastapi import APIRouter

from .students import router as students_router
from .subjects  import router as subjects_router
from .semester  import router as semester_router
from .arrear    import router as arrear_router
from .faculty   import router as faculty_router

upload_router = APIRouter()
upload_router.include_router(students_router)
upload_router.include_router(subjects_router)
upload_router.include_router(semester_router)
upload_router.include_router(arrear_router)
upload_router.include_router(faculty_router)
