"""Start the real API for load testing, fully offline.

Same app as production (`create_app`), but: the AI judge is MockOllamaProvider (no Ollama),
Turnstile Siteverify is answered locally (no Cloudflare), and abuse limits come from the
environment you pass. Never point this at production data.

    TENQ_ENV=test ... uv run python -m tools.loadtest_server --port 8003
"""

import argparse
from datetime import UTC, datetime

import httpx2
import uvicorn

from app.core.config import get_settings
from app.main import create_app


def _siteverify_ok(_: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "success": True,
            "hostname": "localhost",
            "action": "session",
            "challenge_ts": datetime.now(UTC).isoformat(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    settings = get_settings()
    if settings.ai_judge != "mock":
        raise SystemExit("load tests must use TENQ_AI_JUDGE=mock")
    app = create_app(settings, turnstile_transport=httpx2.MockTransport(_siteverify_ok))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
