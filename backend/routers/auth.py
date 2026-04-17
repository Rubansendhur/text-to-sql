import os
import jwt
import bcrypt
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from pydantic import BaseModel

from core.sql_executor import get_executor
from upload.helpers import get_db
from sqlalchemy import text

router = APIRouter(tags=["Authentication"])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

SECRET_KEY = os.environ.get("JWT_SECRET", "super-secret-key-decision-computing")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 week

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str
    department_code: str

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    # print("AUTH CALLED")
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        department_code: str = payload.get("department_code")
        if username is None or role is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    return {"username": username, "role": role, "department_code": department_code}

def is_dept_admin(user: dict) -> bool:
    return (user or {}).get("role") == "admin"

def is_central_admin(user: dict) -> bool:
    return (user or {}).get("role") == "central-admin"


def require_department_code(user: dict) -> str:
    dept = (user or {}).get("department_code")
    if not dept:
        raise HTTPException(status_code=403, detail="Department scope missing for current user")
    return dept

#@router.on_event("startup")
# async def startup_event():
#     # Initialize the users table and default users securely 
#     engine = get_db()
#     with engine.connect() as conn:
#         conn.execute(text("""
#         CREATE TABLE IF NOT EXISTS users (
#             user_id SERIAL PRIMARY KEY,
#             username VARCHAR(255) UNIQUE NOT NULL,
#             password VARCHAR(255) NOT NULL,
#             role VARCHAR(50) NOT NULL
#         )"""))
#         conn.execute(text("""
#         INSERT INTO users (username, password, role) 
#         VALUES 
#             (:u1, :p1, 'hod'), 
#             (:u2, :p2, 'admin') 
#         ON CONFLICT (username) DO UPDATE SET password = EXCLUDED.password
#         """), parameters={
#             "u1": 'HODDCS@cit.edu.in', "p1": get_password_hash('123'),
#             "u2": 'AdminDcs@cit.edu.in', "p2": get_password_hash('123')
#         })
#         conn.commit()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/api/auth/login", response_model=Token)
async def login(req: LoginRequest):
    sql = "SELECT username, role, password, department_code FROM users WHERE username = :u"
    res = await get_executor().run(sql, params={"u": req.username}, role='postgres')
    
    if res.error or not res.rows:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    user = res.rows[0]
    
    if not verify_password(req.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"], "department_code": user["department_code"]}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "role": user["role"],
        "username": user["username"],
        "department_code": user["department_code"]
    }


@router.get("/api/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "department_code": current_user.get("department_code"),
    }

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@router.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    sql = "SELECT user_id, password FROM users WHERE username = :u"
    res = await get_executor().run(sql, params={"u": current_user["username"]}, role='postgres')
    
    if res.error or not res.rows:
        raise HTTPException(status_code=404, detail="User not found")
        
    user = res.rows[0]
    
    if not verify_password(req.old_password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect current password")
        
    hashed_new_pw = get_password_hash(req.new_password)
    
    engine = get_db()
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE users SET password = :p WHERE user_id = :uid
        """), parameters={"p": hashed_new_pw, "uid": user["user_id"]})
        conn.commit()
        
    return {"message": "Password updated successfully"}
