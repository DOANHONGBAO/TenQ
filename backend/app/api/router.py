from fastapi import APIRouter

from app.api import health, puzzles

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(puzzles.router)
