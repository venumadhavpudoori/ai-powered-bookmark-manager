"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.routers import auth, bookmarks, collections, search, tags

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="RecallAI",
    description="AI-powered bookmark manager with semantic search",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://web:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers under /api/v1
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(bookmarks.router, prefix=API_PREFIX)
app.include_router(tags.router, prefix=API_PREFIX)
app.include_router(collections.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}
