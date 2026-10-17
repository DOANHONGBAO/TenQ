"""List the Ollama Cloud models your API key can see, and optionally probe one model.

Usage (reads TENQ_OLLAMA_API_KEY or OLLAMA_API_KEY from the environment or backend/.env):
    uv run python -m app.scripts.check_ollama_models                 # 1 request: GET /api/tags
    uv run python -m app.scripts.check_ollama_models --probe MODEL   # +1 tiny chat request

Ollama does not publish which models the free plan includes, so probe before choosing
TENQ_OLLAMA_MODEL. HTTP 402 means the model is not available on your plan.
"""

import argparse
import asyncio
import sys

import httpx2

from app.core.config import get_settings


async def run(probe: str | None) -> int:
    settings = get_settings()
    if settings.ollama_api_key is None:
        print("error: set TENQ_OLLAMA_API_KEY (or OLLAMA_API_KEY) first", file=sys.stderr)
        return 1
    headers = {"Authorization": f"Bearer {settings.ollama_api_key.get_secret_value()}"}
    async with httpx2.AsyncClient(
        base_url=settings.ollama_base_url, headers=headers, timeout=15
    ) as http:
        tags = await http.get("/api/tags")
        print(f"GET /api/tags -> HTTP {tags.status_code}")
        if tags.status_code == 200:
            for model in sorted(m.get("name", "?") for m in tags.json().get("models", [])):
                print(f"  {model}")
        if probe:
            response = await http.post(
                "/api/chat",
                json={
                    "model": probe,
                    "stream": False,
                    "messages": [{"role": "user", "content": 'Reply with {"result": "YES"}'}],
                    "options": {"temperature": 0, "num_predict": 64},
                },
            )
            print(f"probe {probe} -> HTTP {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                content = (data.get("message") or {}).get("content", "")
                print(f"  content: {content[:80]!r}")
                prompt_tokens, output_tokens = data.get("prompt_eval_count"), data.get("eval_count")
                print(f"  tokens: prompt={prompt_tokens} output={output_tokens}")
            else:
                print(f"  error: {response.text[:200]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Ollama Cloud model access.")
    parser.add_argument("--probe", help="model name to test with one tiny request")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.probe))


if __name__ == "__main__":
    raise SystemExit(main())
