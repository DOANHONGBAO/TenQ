import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.models.word import InvalidWordListError, WordEntry, validate_word_list
from app.repositories.word_repository import SqliteWordRepository
from app.scripts import seed_words

COUNT = 365


def test_dev_words_are_valid(words: list[WordEntry]) -> None:
    validate_word_list(words, COUNT)


def test_rejects_wrong_count(words: list[WordEntry]) -> None:
    with pytest.raises(InvalidWordListError, match="expected 365"):
        validate_word_list(words[:-1], COUNT)


def test_rejects_duplicates(words: list[WordEntry]) -> None:
    broken = [*words[:-1], words[0]]
    with pytest.raises(InvalidWordListError, match="duplicate"):
        validate_word_list(broken, COUNT)


@pytest.mark.parametrize("bad_word", ["", "a", "Apple", "ice cream", "café", "x" * 33, "r2d2"])
def test_rejects_invalid_words(words: list[WordEntry], bad_word: str) -> None:
    broken = [replace(words[0], word=bad_word), *words[1:]]
    with pytest.raises(InvalidWordListError, match=r"\[a-z\]"):
        validate_word_list(broken, COUNT)


def test_rejects_definition_that_reveals_the_word(words: list[WordEntry]) -> None:
    leaky = replace(words[0], definition=f"The {words[0].word}s that everyone knows well.")
    with pytest.raises(InvalidWordListError, match="must not contain the word"):
        validate_word_list([leaky, *words[1:]], COUNT)


def test_error_messages_never_quote_words(words: list[WordEntry]) -> None:
    broken = [*words[:-1], words[0]]
    with pytest.raises(InvalidWordListError) as info:
        validate_word_list(broken, COUNT)
    assert words[0].word not in str(info.value)


def test_word_entry_repr_hides_word(words: list[WordEntry]) -> None:
    assert words[0].word not in repr(words[0])


def test_database_rejects_invalid_word_even_without_validation(db_path: Path) -> None:
    import sqlite3

    entry = seed_words.dev_entries(1)[0]
    with pytest.raises(sqlite3.IntegrityError):
        SqliteWordRepository(db_path).replace_words([replace(entry, word="Bad Word")])


def test_seed_command_loads_file(
    tmp_path: Path, db_path: Path, monkeypatch: pytest.MonkeyPatch, words: list[WordEntry]
) -> None:
    payload = [
        {
            "word": w.word,
            "part_of_speech": w.part_of_speech.value,
            "category": w.category,
            "definition": w.definition,
            "attributes": list(w.attributes),
        }
        for w in words
    ]
    source = tmp_path / "words.json"
    source.write_text(json.dumps(payload))
    monkeypatch.setenv("TENQ_ENV", "test")
    monkeypatch.setenv("TENQ_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("TENQ_WORD_SELECTION_KEY", "ab" * 32)
    monkeypatch.setenv("TENQ_SESSION_SECRET", "cd" * 32)
    seed_words.get_settings.cache_clear()

    assert seed_words.main([str(source)]) == 0
    stored = SqliteWordRepository(db_path).list_words()
    assert stored == sorted(w.word for w in words)
    assert SqliteWordRepository(db_path).get_entry(words[0].word) == words[0]
    seed_words.get_settings.cache_clear()


def test_seed_command_rejects_duplicates_without_writing(
    tmp_path: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = [
        {
            "word": "samesame",
            "part_of_speech": "noun",
            "category": "test",
            "definition": "A repeated placeholder entry.",
            "attributes": ["x"],
        }
    ] * COUNT
    source = tmp_path / "words.json"
    source.write_text(json.dumps(payload))
    monkeypatch.setenv("TENQ_ENV", "test")
    monkeypatch.setenv("TENQ_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("TENQ_WORD_SELECTION_KEY", "ab" * 32)
    monkeypatch.setenv("TENQ_SESSION_SECRET", "cd" * 32)
    seed_words.get_settings.cache_clear()

    assert seed_words.main([str(source)]) == 1
    assert SqliteWordRepository(db_path).list_words() == []
    assert "samesame" not in capsys.readouterr().err
    seed_words.get_settings.cache_clear()
