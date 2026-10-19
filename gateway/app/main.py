import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
# Simple sliding-window counter: max RATE_LIMIT requests per RATE_WINDOW seconds
# per client IP. In-memory — resets on restart. Sufficient for demo purposes.
import os
RATE_LIMIT  = int(os.getenv("RATE_LIMIT", "60"))    # requests
RATE_WINDOW = int(os.getenv("RATE_WINDOW", "60"))   # seconds

# {ip: [timestamp, ...]}
_request_log: dict[str, list[float]] = defaultdict(list)


def _is_rate_limited(ip: str) -> bool:
    now      = time.monotonic()
    cutoff   = now - RATE_WINDOW
    history  = [t for t in _request_log[ip] if t > cutoff]
    history.append(now)
    _request_log[ip] = history
    return len(history) > RATE_LIMIT


# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("[gateway] Starting up")
    yield
    logger.info("[gateway] Shutting down")


app = FastAPI(title="API Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip rate limiting for health check
    if request.url.path == "/health":
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(ip):
        logger.warning("[gateway] Rate limit exceeded for %s", ip)
        return Response(
            content='{"detail":"Rate limit exceeded. Try again later."}',
            status_code=429,
            media_type="application/json",
        )
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start    = time.monotonic()
    response = await call_next(request)
    elapsed  = (time.monotonic() - start) * 1000
    logger.info("[gateway] %s %s → %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed)
    return response


app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "api-gateway"}
