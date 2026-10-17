"""Measure judge accuracy and consistency on a labelled vocabulary set.

Usage:
    uv run python -m app.scripts.evaluate_judge                      # MockOllamaProvider, free
    uv run python -m app.scripts.evaluate_judge --live --max-requests 30 --repeat 2

The evaluation words are not part of the private game vocabulary. The deterministic layers
(prefilter, exact guess) run first exactly as in production; only the remaining questions
cost model requests, and the run stops at --max-requests. The cache is bypassed so repeats
measure consistency. Results describe this sample only; they do not prove the judge is
always right.
"""

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.integrations.ai_judge import JudgeContext, JudgeInvalidOutputError, parse_judge_output
from app.integrations.judge_prompt import PROMPT_VERSION, build_messages
from app.integrations.ollama_client import (
    OllamaClient,
    OllamaError,
    OllamaOptions,
    make_http_client,
)
from app.integrations.ollama_mock import MockOllamaProvider
from app.models.game import Answer
from app.models.judge_rules import exact_guess, prefilter, wrong_explicit_guess
from app.models.question import mentions_word, parse_question
from app.models.word import PartOfSpeech, WordEntry

DEFAULT_SET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "judge_eval.json"
HARD_CAP = 120


async def evaluate(live: bool, max_requests: int, repeat: int, dataset: Path) -> dict[str, Any]:
    settings = get_settings()
    if live:
        if settings.ollama_api_key is None or not settings.ollama_model:
            raise SystemExit("--live needs TENQ_OLLAMA_API_KEY and TENQ_OLLAMA_MODEL")
        http = make_http_client(
            settings.ollama_base_url, settings.ollama_api_key.get_secret_value()
        )
        model = settings.ollama_model
    else:
        http = make_http_client("http://mock-ollama", None, MockOllamaProvider().transport())
        model = "mock"
    client = OllamaClient(
        http,
        OllamaOptions(
            model=model, num_predict=settings.ollama_num_predict, think=settings.ollama_think_value
        ),
    )

    data = json.loads(dataset.read_text())
    requests = 0
    rows: list[dict[str, Any]] = []
    tokens = Counter[str]()
    latencies: list[float] = []
    # Interleave cases across words so a small --max-requests still samples every word.
    queue: list[tuple[dict[str, Any], dict[str, Any]]] = []
    longest = max(len(item["cases"]) for item in data["words"])
    for index in range(longest):
        for item in data["words"]:
            if index < len(item["cases"]):
                queue.append((item, item["cases"][index]))
    try:
        for item, case in queue:
            entry = WordEntry(
                word=item["word"],
                part_of_speech=PartOfSpeech(item["part_of_speech"]),
                category=item["category"],
                definition=item["definition"],
                attributes=tuple(item["attributes"]),
            )
            context = JudgeContext(
                game_date=datetime.now(UTC).date(), word=entry.word, entry=entry, puzzle_id="eval"
            )
            question = parse_question(case["question"])
            answers: list[str] = []
            source = "rule"
            ruled = prefilter(question)
            if ruled is None and exact_guess(question, entry.word):
                ruled = Answer.WIN
            if ruled is None and wrong_explicit_guess(question, entry.word):
                ruled = Answer.NO
            if ruled is not None:
                answers = [ruled.value]
            else:
                source = "model"
                for _ in range(repeat):
                    if requests >= max_requests:
                        break
                    requests += 1
                    t0 = time.monotonic()
                    try:
                        result = await client.chat(
                            build_messages(context, question, strict=False), deadline_s=30
                        )
                        tokens["prompt"] += result.prompt_tokens
                        tokens["output"] += result.output_tokens
                        label = parse_judge_output(result.content)
                        if label is Answer.WIN and not mentions_word(question, entry.word):
                            label_text = "INVALID_WIN"
                        else:
                            label_text = label.value
                    except JudgeInvalidOutputError as exc:
                        label_text = f"INVALID:{exc}"
                        if result.done_reason == "length":
                            label_text += " (truncated: raise num_predict or set think=low)"
                    except OllamaError as exc:
                        label_text = f"ERROR:{type(exc).__name__}"
                    latencies.append(time.monotonic() - t0)
                    answers.append(label_text)
                if not answers:
                    continue
            rows.append(
                {
                    "word": entry.word,
                    "kind": case["kind"],
                    "question": case["question"],
                    "expected": case["expected"],
                    "answers": answers,
                    "source": source,
                }
            )
    finally:
        await http.aclose()

    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    consistent = repeated = 0
    for row in rows:
        first = row["answers"][0]
        if row["expected"] is None:
            by_kind[row["kind"]]["unscored"] += 1
        else:
            by_kind[row["kind"]]["correct" if first == row["expected"] else "wrong"] += 1
        if len(row["answers"]) > 1:
            repeated += 1
            consistent += len(set(row["answers"])) == 1
    scored = [r for r in rows if r["expected"] is not None]
    correct = sum(r["answers"][0] == r["expected"] for r in scored)
    model_scored = [r for r in scored if r["source"] == "model"]
    model_correct = sum(r["answers"][0] == r["expected"] for r in model_scored)
    return {
        "mode": "live" if live else "mock",
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "model_requests": requests,
        "cases_evaluated": len(rows),
        "accuracy_all": round(correct / len(scored), 3) if scored else None,
        "accuracy_model_only": round(model_correct / len(model_scored), 3)
        if model_scored
        else None,
        "consistency": round(consistent / repeated, 3) if repeated else None,
        "invalid_or_error": sum(
            a.startswith(("INVALID", "ERROR")) for r in rows for a in r["answers"]
        ),
        "tokens": dict(tokens),
        "avg_latency_s": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "mistakes": [
            {k: r[k] for k in ("word", "question", "expected", "answers")}
            for r in scored
            if r["answers"][0] != r["expected"]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the AI judge.")
    parser.add_argument("--live", action="store_true", help="call the real Ollama Cloud API")
    parser.add_argument("--max-requests", type=int, default=30)
    parser.add_argument("--repeat", type=int, default=1, help="asks per question (consistency)")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_SET)
    args = parser.parse_args(argv)
    max_requests = min(args.max_requests, HARD_CAP)
    report = asyncio.run(evaluate(args.live, max_requests, max(1, args.repeat), args.dataset))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
