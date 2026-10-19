import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from jose import JWTError, jwt, ExpiredSignatureError
from passlib.context import CryptContext
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# bcrypt 4.x+ changed its internal API; passlib 1.7.4 triggers a warning
# but still works correctly. Suppress the version-check warning.
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
    return secret


def _algorithm() -> str:
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    if algorithm != "HS256":
        raise RuntimeError("JWT_ALGORITHM must be HS256")
    return algorithm


def _expiry_minutes() -> int:
    return int(os.getenv("JWT_EXPIRY_MINUTES", "60"))


# ---------- password ----------

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------- JWT ----------

def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_expiry_minutes())
    payload = {
        "sub":  str(user_id),
        "role": role,
        "exp":  expire,
    }
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


def decode_token(token: str) -> dict:
    """
    Validates signature and expiry.
    Raises HTTP 401 on any failure.
    """
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_algorithm()], options={"require_sub": True, "require_exp": True})
        if not payload["sub"].isdigit() or payload.get("role") not in {"user", "admin"}:
            raise JWTError("Invalid token claims")
        return payload
    except ExpiredSignatureError:
        logger.warning("[user-service] Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        logger.warning("[user-service] Invalid token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:].strip()
