import os
import time
import logging
import logging.config
from collections import defaultdict
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import project, auth
from app.config import ALLOWED_ORIGINS, RATE_LIMIT_PER_MINUTE, IS_PRODUCTION

# Configure logging to be visible in console even when run via Uvicorn
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
})
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Ranqora - Dataset Intelligence API",
    description="AI-Powered Dataset Discovery & Ranking Platform",
    version="2.1.0",
    # Disable docs in production for security
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
)


# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],       # Only methods we actually use
    allow_headers=["Content-Type"],
)


# ── Security Headers Middleware ──────────────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # XSS protection (legacy browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Don't leak referrer info
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Remove server header
    if "server" in response.headers:
        del response.headers["server"]
    return response


# ── Rate Limiting Middleware ─────────────────────────────────────────────────
# Simple in-memory rate limiter (for single-worker HF Spaces deployment)
_rate_store: dict = defaultdict(list)


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    if RATE_LIMIT_PER_MINUTE <= 0:
        return await call_next(request)

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60  # 1 minute

    # Clean old entries
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < window]

    if len(_rate_store[ip]) >= RATE_LIMIT_PER_MINUTE:
        logger.warning(f"Rate limit exceeded for IP: {ip}")
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests. Please wait a minute."},
        )

    _rate_store[ip].append(now)
    return await call_next(request)


# ── Request Size Limit ───────────────────────────────────────────────────────
MAX_REQUEST_SIZE = 10_000  # 10KB — queries shouldn't be larger than this


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_SIZE:
        return JSONResponse(
            status_code=413,
            content={"error": "Request too large."},
        )
    return await call_next(request)


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(project.router)
app.include_router(auth.router)


# ── Health Check ─────────────────────────────────────────────────────────────
@app.get("/")
def health_check():
    return {
        "status": "ok",
        "version": "2.1.0",
        "message": "Ranqora Dataset Intelligence API is running",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0")