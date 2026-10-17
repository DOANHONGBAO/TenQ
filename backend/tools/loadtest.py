"""Lightweight async load test for the TenQ API (no extra dependencies).

Scenario per virtual player: POST /session, GET /game/today, then N questions drawn from a
shared pool (so the daily judgement cache gets hits), then GET /leaderboard/today.
Reports only what was measured: throughput, latency percentiles per endpoint, status codes,
Redis command counts, and judge cache hit ratio (from the server log's model-call lines).

    uv run python -m tools.loadtest --base http://127.0.0.1:8003 --players 100 \
        --questions 8 --concurrency 50 --redis redis://127.0.0.1:6390/10 --server-log /tmp/x.log
"""

import argparse
import asyncio
import json
import random
import statistics
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import httpx2
from redis.asyncio import Redis

POOL = [
    f"Is it {w}?"
    for w in (
        "alive",
        "big",
        "small",
        "red",
        "blue",
        "edible",
        "metal",
        "wooden",
        "heavy",
        "soft",
        "an animal",
        "a tool",
        "a vehicle",
        "found indoors",
        "found outdoors",
        "electronic",
        "round",
        "sharp",
        "expensive",
        "older than a century",
        "used daily",
        "made by people",
        "liquid",
        "a plant",
        "a place",
        "a food",
        "a drink",
        "loud",
        "bright",
        "cold",
    )
]


class Stats:
    def __init__(self) -> None:
        self.latency: dict[str, list[float]] = defaultdict(list)
        self.status: Counter[str] = Counter()
        self.errors: Counter[str] = Counter()

    def record(self, name: str, seconds: float, status: int) -> None:
        self.latency[name].append(seconds * 1000)
        self.status[f"{name} {status}"] += 1


async def timed(stats: Stats, name: str, coro: object) -> httpx2.Response | None:
    t0 = time.perf_counter()
    try:
        response = await coro  # type: ignore[misc]
    except httpx2.HTTPError as exc:
        stats.errors[f"{name} {type(exc).__name__}"] += 1
        return None
    stats.record(name, time.perf_counter() - t0, response.status_code)
    return response


async def player(
    base: str, questions: int, stats: Stats, sem: asyncio.Semaphore, seed: int
) -> None:
    rnd = random.Random(seed)  # noqa: S311 - question sampling, not security
    async with sem, httpx2.AsyncClient(base_url=base, timeout=30) as client:
        client.headers["User-Agent"] = f"loadtest-{seed}"
        await timed(
            stats,
            "POST /session",
            client.post("/api/v1/session", json={"turnstile_token": uuid.uuid4().hex}),
        )
        await timed(stats, "GET /game/today", client.get("/api/v1/game/today"))
        for q in rnd.sample(POOL, questions):
            await timed(
                stats,
                "POST /questions",
                client.post(
                    "/api/v1/game/today/questions",
                    json={"question": q},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                ),
            )
        await timed(stats, "GET /leaderboard", client.get("/api/v1/leaderboard/today"))


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8003")
    ap.add_argument("--players", type=int, default=100)
    ap.add_argument("--questions", type=int, default=8)
    ap.add_argument("--concurrency", type=int, default=50)
    ap.add_argument("--redis", default="redis://127.0.0.1:6390/10")
    ap.add_argument("--server-log", type=Path)
    args = ap.parse_args()

    redis = Redis.from_url(args.redis, decode_responses=True)
    info0 = await redis.info("stats")
    log_offset = args.server_log.stat().st_size if args.server_log else 0
    stats = Stats()
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.perf_counter()
    await asyncio.gather(
        *(player(args.base, args.questions, stats, sem, i) for i in range(args.players))
    )
    elapsed = time.perf_counter() - t0
    info1 = await redis.info("stats")
    await redis.aclose()

    total = sum(len(v) for v in stats.latency.values())
    failed = sum(n for k, n in stats.status.items() if not k.endswith((" 200", " 201"))) + sum(
        stats.errors.values()
    )
    asked_ok = stats.status["POST /questions 200"]
    model_calls = None
    if args.server_log:
        with args.server_log.open() as fh:
            fh.seek(log_offset)
            model_calls = sum(1 for line in fh if "ollama ok" in line)
    report = {
        "players": args.players,
        "questions_per_player": args.questions,
        "concurrency": args.concurrency,
        "elapsed_s": round(elapsed, 2),
        "requests": total,
        "throughput_rps": round(total / elapsed, 1),
        "error_rate": round(failed / max(total, 1), 4),
        "status_counts": dict(sorted(stats.status.items())),
        "transport_errors": dict(stats.errors),
        "latency_ms": {
            name: {
                "n": len(v),
                "p50": round(statistics.median(v), 1),
                "p95": round(pct(v, 95), 1),
                "max": round(max(v), 1),
            }
            for name, v in sorted(stats.latency.items())
        },
        "redis_commands": int(info1["total_commands_processed"])
        - int(info0["total_commands_processed"]),
        "redis_commands_per_request": round(
            (int(info1["total_commands_processed"]) - int(info0["total_commands_processed"]))
            / max(total, 1),
            1,
        ),
        "judge_model_calls": model_calls,
        "judge_cache_hit_ratio": None
        if model_calls is None or not asked_ok
        else round(1 - model_calls / asked_ok, 3),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
