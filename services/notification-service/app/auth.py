import os
import logging
from typing import Optional

from jose import JWTError, ExpiredSignatureError, jwt
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


def _algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def _internal_token() -> str:
    return os.getenv("INTERNAL_SERVICE_TOKEN", "")


def get_token_from_header(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed",
        )
    return authorization.split(" ", 1)[1]


def verify_internal_token(authorization: Optional[str]) -> None:
    """Used by POST /notifications/ — called only by booking-service."""
    token = get_token_from_header(authorization)
    expected = _internal_token()
    if not expected or token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


def decode_user_token(authorization: Optional[str]) -> dict:
    """Used by GET /notifications/my — called by end users."""
    token = get_token_from_header(authorization)
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_algorithm()])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except JWTError as exc:
        logger.warning("[notification-service] Invalid token: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
