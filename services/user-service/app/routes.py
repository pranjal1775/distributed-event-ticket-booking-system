import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .database import get_db
from .models import User
from .schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from .auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    get_token_from_header,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------- helpers ----------

def _current_user(authorization: str, db: Session) -> User:
    """Validate JWT and return the User row. Raises 401/404 on failure."""
    token   = get_token_from_header(authorization)
    payload = decode_token(token)
    user    = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ---------- public endpoints ----------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = str(body.email).lower()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email           = email,
        hashed_password = hash_password(body.password),
        full_name       = body.full_name,
        role            = "user",
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    token = create_access_token(user.id, user.role)
    logger.info("[user-service] Registered user id=%d", user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = str(body.email).lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id, user.role)
    logger.info("[user-service] Login success: id=%d", user.id)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


# ---------- protected endpoints ----------

@router.get("/me", response_model=UserResponse)
def get_me(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user = _current_user(authorization, db)
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Used by other services (booking-service) to verify a user exists.
    Requires a valid JWT — the caller must be authenticated.
    """
    decode_token(get_token_from_header(authorization))   # validate token
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)


# ---------- admin-only endpoints ----------

@router.get("/", response_model=List[UserResponse])
def list_users(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    caller = _current_user(authorization, db)
    _require_admin(caller)
    users = db.query(User).order_by(User.id).all()
    return [UserResponse.model_validate(u) for u in users]
