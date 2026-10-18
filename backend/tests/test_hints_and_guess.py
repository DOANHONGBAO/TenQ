"""Progressive hints and the direct guess box."""

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from httpx2 import AsyncClient

from app.core.errors import DuplicateQuestionError, GameFinishedError, InvalidGuessAppError
from app.models.game import Answer, AttemptKind, GameStatus
from app.models.guess import InvalidGuessError, guess_is_correct, parse_guess
from app.models.hints import HINT_COUNT, derive_hints, hint_problems, visible_hint_count
from app.models.word import InvalidWordListError, PartOfSpeech, WordEntry, validate_word_list
from app.repositories.database import MIGRATIONS_DIR, apply_migrations
from app.repositories.word_repository import SqliteWordRepository
from app.schemas.word_seed import WordSeedFile
from app.scripts import prepare_hints
from app.services.daily_word_service import DailyWordService
from app.services.game_service import GameService
from tests.conftest import start_session

PLAYER = "h" * 32
ENTRY = WordEntry(
    word="zzwalrus",
    part_of_speech=PartOfSpeech.NOUN,
    category="animal",
    definition="A large Arctic sea mammal with long tusks.",
    attributes=("alive", "mammal", "ocean", "tusks"),
)


def key() -> str:
    return str(uuid.uuid4())


# --- hint rules -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("used", "visible"), [(0, 0), (1, 0), (2, 1), (3, 1), (4, 2), (6, 3), (8, 4), (9, 4), (10, 4)]
)
def test_one_hint_after_every_two_attempts(used: int, visible: int) -> None:
    assert visible_hint_count(used) == visible


def test_derived_hints_go_from_vague_to_certain() -> None:
    hints = derive_hints(ENTRY)
    assert len(hints) == HINT_COUNT
    assert hints[0] == "First clue: alive, mammal."
    assert "animal" in hints[1]
    assert "8 characters long" in hints[3] and "“Z”" in hints[3]
    assert hint_problems(ENTRY.word, hints) == []


def test_derived_hints_skip_metadata_that_names_the_word() -> None:
    leaky = WordEntry(
        "rose", PartOfSpeech.NOUN, "rose plants", "A fragrant flower.", ("rose", "thorns")
    )
    assert hint_problems("rose", derive_hints(leaky)) == []


@pytest.mark.parametrize(
    "hints",
    [
        ("one", "two", "three"),
        ("Hint one.", "Hint two.", "Hint three.", "It is a zzwalrus."),
        ("Hint one.", "Hint two.", "Hint three.", "Plural: zzwalruses."),
        ("Hint one.", "Hint two.", "Hint three.", "x" * 201),
    ],
)
def test_bad_hint_lists_are_rejected(hints: tuple[str, ...]) -> None:
    assert hint_problems("zzwalrus", hints)


def test_word_list_validation_requires_hints(words: list[WordEntry]) -> None:
    from dataclasses import replace

    broken = [replace(words[0], hints=()), *words[1:]]
    with pytest.raises(InvalidWordListError, match="hints"):
        validate_word_list(broken, len(words))


def test_seed_file_keeps_given_hints_and_derives_missing_ones() -> None:
    base = {
        "word": "zzwalrus",
        "part_of_speech": "noun",
        "category": "animal",
        "definition": "A large Arctic sea mammal with long tusks.",
        "attributes": ["alive", "mammal", "ocean", "tusks"],
    }
    given = ["Cold.", "Big.", "Tusks.", "Rhymes with ... no, just a large Arctic sea mammal."]
    items = WordSeedFile.validate_python([{**base, "hints": given}, base])
    assert items[0].to_entry().hints == tuple(given)
    assert items[1].to_entry().hints == derive_hints(ENTRY)


def test_migration_adds_hints_to_an_existing_database(tmp_path: Path) -> None:
    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.executescript((MIGRATIONS_DIR / "0001_words_and_daily_puzzles.sql").read_text())
    conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO schema_migrations VALUES (1, 'x')")
    conn.execute("INSERT INTO words VALUES ('zzold', 'noun', 'test', 'An older entry.', '[\"x\"]')")
    conn.commit()
    conn.close()

    assert apply_migrations(db) == [2, 3]
    entry = SqliteWordRepository(db).get_entry("zzold")
    assert entry is not None and entry.hints == ()


def test_prepare_hints_script_fills_missing_hints(tmp_path: Path, words: list[WordEntry]) -> None:
    source = tmp_path / "words.json"
    payload = [
        {
            "word": w.word,
            "part_of_speech": "noun",
            "category": w.category,
            "definition": w.definition,
            "attributes": list(w.attributes),
        }
        for w in words
    ]
    payload[0]["hints"] = ["Custom one.", "Custom two.", "Custom three.", "Custom four."]
    source.write_text(json.dumps(payload))

    assert prepare_hints.main([str(source)]) == 0
    written = json.loads(source.read_text())
    assert written[0]["hints"][0] == "Custom one."  # kept
    assert all(len(item["hints"]) == HINT_COUNT for item in written)
    assert (tmp_path / "words.json.bak").exists()


# --- guesses ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "word"), [("Walrus", "walrus"), ("  the WALRUS ", "walrus"), ("a walrus", "walrus")]
)
def test_parse_guess(raw: str, word: str) -> None:
    assert parse_guess(raw).word == word


@pytest.mark.parametrize("raw", ["", "  ", "two words", "walrus!", "café", "a", "x" * 33])
def test_invalid_guesses(raw: str) -> None:
    with pytest.raises(InvalidGuessError):
        parse_guess(raw)


def test_guess_accepts_simple_plurals_only() -> None:
    assert guess_is_correct(parse_guess("walruses"), "walrus")
    assert not guess_is_correct(parse_guess("walru"), "walrus")


@pytest.mark.anyio
async def test_correct_guess_wins_and_costs_one_attempt(
    game_service: GameService, word_service: DailyWordService
) -> None:
    await game_service.ask(PLAYER, "Is it alive?", key())
    word = word_service.puzzle_for_today().word

    result = await game_service.guess(PLAYER, word.upper(), key())

    assert result.answer is Answer.WIN and result.number == 2
    assert result.game.status is GameStatus.WON
    assert result.game.history[-1].kind is AttemptKind.GUESS
    assert (await game_service.leaderboard(10, PLAYER)).me is not None


@pytest.mark.anyio
async def test_wrong_guess_costs_one_attempt_and_cannot_repeat(game_service: GameService) -> None:
    first = await game_service.guess(PLAYER, "zzwrongword", key())
    assert first.answer is Answer.NO and first.game.used == 1
    with pytest.raises(DuplicateQuestionError):
        await game_service.guess(PLAYER, "ZZWrongWord", key())
    assert (await game_service.state(PLAYER)).used == 1


@pytest.mark.anyio
async def test_guess_replay_and_validation(game_service: GameService) -> None:
    idem = key()
    first = await game_service.guess(PLAYER, "zzwrongword", idem)
    again = await game_service.guess(PLAYER, "zzwrongword", idem)
    assert again.replayed and again.number == first.number
    with pytest.raises(InvalidGuessAppError):
        await game_service.guess(PLAYER, "two words", key())
    assert (await game_service.state(PLAYER)).used == 1


@pytest.mark.anyio
async def test_no_guesses_after_the_game_ends(
    game_service: GameService, word_service: DailyWordService
) -> None:
    await game_service.guess(PLAYER, word_service.puzzle_for_today().word, key())
    with pytest.raises(GameFinishedError):
        await game_service.guess(PLAYER, "zzother", key())


@pytest.mark.anyio
async def test_hints_unlock_with_attempts(
    game_service: GameService, word_service: DailyWordService
) -> None:
    entry = word_service.entry_for(word_service.puzzle_for_today())
    assert entry is not None
    seen = []
    for n in range(1, 10):
        if n % 3 == 0:
            await game_service.guess(
                PLAYER, f"zzguess{'abcdefghij'[n]}", key()
            )  # guesses count too
        else:
            await game_service.ask(PLAYER, f"Is it number {n}?", key())
        seen.append(len((await game_service.state(PLAYER)).hints))
    assert seen == [0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert (await game_service.state(PLAYER)).hints == entry.hints


# --- API --------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_guess_endpoint_and_hint_fields(api: AsyncClient) -> None:
    await start_session(api)
    headers = {"Idempotency-Key": key()}
    for text in ("Is it alive?", "Is it big?"):
        await api.post(
            "/api/v1/game/today/questions",
            json={"question": text},
            headers={"Idempotency-Key": key()},
        )

    response = await api.post(
        "/api/v1/game/today/guesses", json={"guess": "zznotit"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "NO" and body["number"] == 3
    game = body["game"]
    assert len(game["hints"]) == 1 and game["hints_total"] == 4 and game["next_hint_in"] == 1
    assert game["history"][-1] == {**game["history"][-1], "kind": "guess", "question": "zznotit"}


@pytest.mark.anyio
async def test_guess_endpoint_rejects_extra_fields_and_bad_guesses(api: AsyncClient) -> None:
    await start_session(api)
    tampered = await api.post(
        "/api/v1/game/today/guesses",
        json={"guess": "zzx", "hints": ["give me all"]},
        headers={"Idempotency-Key": key()},
    )
    assert tampered.status_code == 422
    bad = await api.post(
        "/api/v1/game/today/guesses",
        json={"guess": "two words"},
        headers={"Idempotency-Key": key()},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_GUESS"
    state = (await api.get("/api/v1/game/today")).json()
    assert state["used"] == 0 and state["hints"] == [] and state["next_hint_in"] == 2
