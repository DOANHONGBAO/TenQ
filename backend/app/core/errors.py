"""Typed application errors mapped to the API error envelope (docs/api-contract.md section 2).

Messages are shown to players: they must never contain secrets such as the daily word.
"""

import logging
import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    message = "An unexpected error occurred."
    headers: ClassVar[Mapping[str, str] | None] = None

    @property
    def response_headers(self) -> Mapping[str, str] | None:
        return self.headers

    def __init__(self, message: str | None = None, details: dict[str, str] | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details


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
    headers: ClassVar[Mapping[str, str] | None] = MappingProxyType({"Retry-After": "5"})


class ForbiddenOriginError(AppError):
    status_code = 403
    code = "FORBIDDEN_ORIGIN"
    message = "Forbidden."


class TurnstileFailedError(AppError):
    status_code = 403
    code = "TURNSTILE_FAILED"
    message = "The security check failed. Please reload the page and try again."


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"
    message = "The request is too large."


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests. Please slow down and try again shortly."

    def __init__(self, retry_after_s: int) -> None:
        super().__init__()
        self.retry_after_s = retry_after_s

    @property
    def response_headers(self) -> Mapping[str, str]:
        return {"Retry-After": str(self.retry_after_s)}


class BadRequestError(AppError):
    status_code = 400
    code = "BAD_REQUEST"
    message = "The request could not be processed."


class SessionRequiredError(AppError):
    status_code = 401
    code = "SESSION_REQUIRED"
    message = "A session is required. Load the game first."


class QuestionInProgressError(AppError):
    status_code = 409
    code = "QUESTION_IN_PROGRESS"
    message = "Another question is still being judged."


class AttemptLimitReachedError(AppError):
    status_code = 409
    code = "ATTEMPT_LIMIT_REACHED"
    message = "You have used all 10 questions for today."


class GameFinishedError(AppError):
    status_code = 409
    code = "GAME_FINISHED"
    message = "You already won today's game."


class DuplicateQuestionError(AppError):
    status_code = 409
    code = "DUPLICATE_QUESTION"
    message = "You already asked that question today."


class InvalidQuestionAppError(AppError):
    status_code = 422
    code = "INVALID_QUESTION"
    message = "The question is not a valid English yes/no question."


class IdempotencyKeyReusedError(AppError):
    status_code = 422
    code = "IDEMPOTENCY_KEY_REUSED"
    message = "This Idempotency-Key was already used for a different question."


class AIInvalidResponseError(AppError):
    status_code = 502
    code = "AI_INVALID_RESPONSE"
    message = "The judge gave an answer that could not be validated. You were not charged."


class AIUnavailableError(AppError):
    status_code = 503
    code = "AI_UNAVAILABLE"
    message = "The judge is unavailable. You were not charged; please try again."
    headers: ClassVar[Mapping[str, str] | None] = MappingProxyType({"Retry-After": "5"})


def _envelope(
    status: int,
    code: str,
    message: str,
    details: dict[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    # Request id middleware arrives in Phase 02b; until then each error gets its own id.
    error: dict[str, object] = {"code": code, "message": message, "request_id": uuid.uuid4().hex}
    if details:
        error["details"] = details
    return JSONResponse(
        {"error": error},
        status_code=status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(exc.status_code, exc.code, exc.message, exc.details, exc.response_headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, __: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return _envelope(422, "VALIDATION_ERROR", "The request is invalid.")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        if exc.status_code == 404:
            return _envelope(404, "NOT_FOUND", "Resource not found.")
        if exc.status_code == 405:
            return _envelope(405, "METHOD_NOT_ALLOWED", "Method not allowed.")
        return _envelope(exc.status_code, "BAD_REQUEST", "The request could not be processed.")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        # Details go to the log only; the client sees a generic message (no stack trace).
        logger.exception("unhandled error: %s", type(exc).__name__)
        return _envelope(500, "INTERNAL_ERROR", "An unexpected error occurred.")
