"""Typed application errors mapped to the API error envelope (docs/api-contract.md section 2).

Messages are shown to players: they must never contain secrets such as the daily word.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    message = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found."


class AnswerNotAvailableError(AppError):
    status_code = 403
    code = "ANSWER_NOT_AVAILABLE"
    message = "The answer is only available after the game day has ended (UTC)."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
    message = "The service is temporarily unavailable."


def _envelope(status: int, code: str, message: str) -> JSONResponse:
    # Request id middleware arrives in Phase 02b; until then each error gets its own id.
    body = {"error": {"code": code, "message": message, "request_id": uuid.uuid4().hex}}
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, __: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(422, "VALIDATION_ERROR", "The request is invalid.")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        if exc.status_code == 404:
            return _envelope(404, "NOT_FOUND", "Resource not found.")
        return _envelope(exc.status_code, "BAD_REQUEST", "The request could not be processed.")
