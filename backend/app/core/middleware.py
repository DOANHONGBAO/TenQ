"""Pure ASGI middleware that runs before routing: origin guard and request body limit."""

import json
import logging
import uuid
from collections.abc import Sequence

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.client_ip import ORIGIN_SECRET_HEADER, origin_secret_valid

logger = logging.getLogger(__name__)

# Paths that stay reachable without the origin secret (container health checks on the VM).
_UNGUARDED = ("/api/v1/health",)


async def _send_error(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps(
        {"error": {"code": code, "message": message, "request_id": uuid.uuid4().hex}}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class OriginGuardMiddleware:
    """Refuse requests that did not come through the trusted proxy (Vercel).

    Active only when origin secrets are configured (required in production).
    """

    def __init__(self, app: ASGIApp, secrets: Sequence[str]) -> None:
        self.app = app
        self.secrets = tuple(secrets)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.secrets or scope["path"] in _UNGUARDED:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if not origin_secret_valid(headers.get(ORIGIN_SECRET_HEADER), self.secrets):
            await _send_error(send, 403, "FORBIDDEN_ORIGIN", "Forbidden.")
            return
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Reject bodies over `max_bytes`, by Content-Length and while streaming (no trust in it)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await _send_error(send, 400, "BAD_REQUEST", "The request is malformed.")
                    return
                if declared > self.max_bytes:
                    await _send_error(send, 413, "PAYLOAD_TOO_LARGE", "The request is too large.")
                    return

        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            if too_large:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Stop reading; hand the app an empty final chunk and replace its reply.
                    too_large = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        replaced = False

        async def guarded_send(message: Message) -> None:
            nonlocal replaced
            if too_large:
                if not replaced:
                    replaced = True
                    await _send_error(send, 413, "PAYLOAD_TOO_LARGE", "The request is too large.")
                return
            await send(message)

        await self.app(scope, limited_receive, guarded_send)
