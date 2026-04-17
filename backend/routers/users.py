from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from upload.helpers import get_db
from sqlalchemy import text
from core.sql_executor import get_executor
import bcrypt
from .auth import get_current_user

router = APIRouter(tags=["Users"])

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    department_code: str

@router.get("/api/users")
async def get_users(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "central-admin":
        raise HTTPException(status_code=403, detail="Not authorized to perform this action")
        
    sql = "SELECT user_id, username, role, department_code FROM users ORDER BY user_id"
    res = await get_executor().run(sql, role='postgres')
    
    if res.error:
        raise HTTPException(status_code=500, detail=f"Database error: {res.error}")
        
    return {"users": res.rows}

@router.post("/api/users")
async def create_user(req: CreateUserRequest, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "central-admin":
        raise HTTPException(status_code=403, detail="Not authorized to perform this action")
        
    engine = get_db()
    hashed_pw = bcrypt.hashpw(req.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                INSERT INTO users (username, password, role, department_code) 
                VALUES (:u, :p, :r, :d)
            """), parameters={"u": req.username, "p": hashed_pw, "r": req.role, "d": req.department_code})
            conn.commit()
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e).lower():
                raise HTTPException(status_code=400, detail="Username already exists")
            raise HTTPException(status_code=500, detail=str(e))

# @router.get("/api/subjects")
            
    return {"message": "User created successfully"}
