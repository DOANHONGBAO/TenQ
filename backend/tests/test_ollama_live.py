"""Opt-in smoke test against the real Ollama Cloud API (2 requests).

Run only on purpose:
    TENQ_LIVE_AI=1 uv run pytest -m live_ai
It needs TENQ_OLLAMA_API_KEY (or OLLAMA_API_KEY) and TENQ_OLLAMA_MODEL in the environment.
"""

import os
from datetime import UTC, datetime

import pytest

from app.integrations.ai_judge import JudgeContext, parse_judge_output
from app.integrations.judge_prompt import build_messages
from app.integrations.ollama_client import OllamaClient, OllamaOptions, make_http_client
from app.models.game import Answer
from app.models.question import parse_question
from app.models.word import PartOfSpeech, WordEntry

pytestmark = [pytest.mark.live_ai, pytest.mark.anyio]

KEY = os.environ.get("TENQ_OLLAMA_API_KEY") or os.environ.get("OLLAMA_API_KEY")
MODEL = os.environ.get("TENQ_OLLAMA_MODEL")
ENABLED = os.environ.get("TENQ_LIVE_AI") == "1" and KEY and MODEL


@pytest.mark.skipif(not ENABLED, reason="set TENQ_LIVE_AI=1, an API key, and TENQ_OLLAMA_MODEL")
async def test_live_judge_returns_valid_labels() -> None:
    entry = WordEntry(
        word="kiwi",
        part_of_speech=PartOfSpeech.NOUN,
        category="food",
        definition="A small brown fuzzy fruit with green flesh and black seeds.",
        attributes=("edible", "fruit", "green inside"),
    )
    context = JudgeContext(datetime.now(UTC).date(), "kiwi", entry, "live-smoke")
    http = make_http_client("https://ollama.com", KEY)
    client = OllamaClient(http, OllamaOptions(model=str(MODEL), max_retries=1))
    try:
        results = []
        for text in ("Is it a fruit?", "Is it made of metal?"):
            chat = await client.chat(build_messages(context, parse_question(text), False), 30)
            results.append(parse_judge_output(chat.content))
    finally:
        await http.aclose()
    assert results[0] is Answer.YES  # one sample; a NO here is a model mistake, not a crash
    assert results[1] in {Answer.NO, Answer.IRRELEVANT}
