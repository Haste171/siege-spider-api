from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi import APIRouter
from database.handler import get_db
from database.models import User
from services.user.token import create_access_token, get_current_user
from services.user.pwd import verify_password
from pydantic import BaseModel, EmailStr, constr, field_validator

router = APIRouter()

@router.get("/users/me")
def read_users_me(current_user = Depends(get_current_user)):
    return {
        "username": current_user.username,
        "email": current_user.email,
    }

class LoginRequest(BaseModel):
    email: EmailStr
    password: constr(strip_whitespace=True, min_length=1, max_length=100)  # type: ignore

    @field_validator('email', mode='before')
    def normalize_email(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

@router.post("/token")
def login(login_request: LoginRequest, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == login_request.email).first()
    if not db_user or not verify_password(login_request.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    token = create_access_token(data={"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}
