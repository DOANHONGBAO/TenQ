from fastapi import APIRouter

from app.api import game, health, puzzles, session

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
api_router.include_router(puzzles.router)
api_router.include_router(game.router)
api_router.include_router(session.router)
