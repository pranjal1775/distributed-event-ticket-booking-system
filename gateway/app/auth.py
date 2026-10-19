import os
import logging
from typing import Optional

from jose import JWTError, ExpiredSignatureError, jwt
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


def _secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


def _algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def extract_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1]
    return None


def require_jwt(request: Request) -> dict:
    """Dependency — validates JWT and returns payload. Raises 401 on failure."""
    token = extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed",
        )
    try:
        return jwt.decode(token, _secret(), algorithms=[_algorithm()])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except JWTError as exc:
        logger.warning("[gateway] Invalid token: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
