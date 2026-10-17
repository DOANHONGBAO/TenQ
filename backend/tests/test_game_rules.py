import pytest

from app.core.session import SessionCodec
from app.models.game import (
    Answer,
    GameStatus,
    display_name_for,
    leaderboard_score,
    status_after,
)
from app.models.question import InvalidQuestionError, mentions_word, parse_question


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "too_short"),
        ("a?", "too_short"),
        ("x" * 150 + "?", "too_long"),
        ("Is it café?", "invalid_characters"),
        ("Is it‮evil?", "invalid_characters"),
        ("Is it an animal", "not_a_question"),
    ],
)
def test_invalid_questions(raw: str, reason: str) -> None:
    with pytest.raises(InvalidQuestionError) as info:
        parse_question(raw)
    assert info.value.reason == reason


def test_normalization_makes_duplicates_equal() -> None:
    a = parse_question("  Is it   an ANIMAL?? ")
    b = parse_question("is it an animal?")
    assert a.text == "Is it an ANIMAL??"
    assert a.qhash == b.qhash


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Is it a zzbeacon?", True),
        ("Is it zzbeacons?", True),
        ("Is it a ZZBEACON?", True),
        ("Is it a zz beacon?", False),
        ("Is it near a zzbeacon keeper's house?", True),
        ("Is it a zzbeaconkeeper?", False),
    ],
)
def test_win_requires_the_word_as_a_token(question: str, expected: bool) -> None:
    assert mentions_word(parse_question(question), "zzbeacon") is expected


@pytest.mark.parametrize(
    ("used", "answer", "status"),
    [
        (1, Answer.NO, GameStatus.IN_PROGRESS),
        (1, Answer.WIN, GameStatus.WON),
        (9, Answer.PENALTY, GameStatus.IN_PROGRESS),
        (10, Answer.IRRELEVANT, GameStatus.LOST),
        (10, Answer.WIN, GameStatus.WON),
    ],
)
def test_status_after(used: int, answer: Answer, status: GameStatus) -> None:
    assert status_after(used, answer) is status


def test_finished_states() -> None:
    assert GameStatus.WON.is_finished and GameStatus.LOST.is_finished
    assert not GameStatus.IN_PROGRESS.is_finished and not GameStatus.NOT_STARTED.is_finished


def test_score_orders_questions_before_duration() -> None:
    a_day_ms = 86_400_000
    assert leaderboard_score(3, a_day_ms) < leaderboard_score(4, 0)
    assert leaderboard_score(3, 1000) < leaderboard_score(3, 1001)
    assert leaderboard_score(10, 2 * a_day_ms) < 2**53


def test_display_name_is_anonymous() -> None:
    assert display_name_for("7f3a9b" + "0" * 26) == "Player-7F3A9B"


def test_session_cookie_roundtrip_and_tampering() -> None:
    codec = SessionCodec(bytes(range(32)))
    value, player_id = codec.issue(1_792_000_000)

    assert codec.verify(value) == player_id
    assert codec.verify(value[:-1] + ("A" if value[-1] != "A" else "B")) is None
    assert codec.verify("x.y.z") is None
    assert codec.verify(None) is None
    other = SessionCodec(bytes(range(1, 33)))
    assert other.verify(value) is None


def test_player_hash_is_keyed_and_stable() -> None:
    codec = SessionCodec(bytes(range(32)))
    assert codec.player_hash("abc") == codec.player_hash("abc")
    assert codec.player_hash("abc") != SessionCodec(bytes(range(1, 33))).player_hash("abc")
    assert len(codec.player_hash("abc")) == 32
