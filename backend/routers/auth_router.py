from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_password, create_access_token, get_current_user, DEMO_USER

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_name: str
    user_email: str
    user_role: str


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    if req.email != DEMO_USER["email"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, DEMO_USER["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": req.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_name": DEMO_USER["name"],
        "user_email": DEMO_USER["email"],
        "user_role": DEMO_USER["role"],
    }


@router.get("/me")
def get_me(user=Depends(get_current_user)):
    return user
