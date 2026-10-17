"""Format of the private word list file used to seed SQLite.

The file is a JSON array kept outside the repository (for example backend/secrets/words.json,
which is git-ignored, or /opt/tenq/secrets/words.json on the server).
"""

from dataclasses import replace

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.models.hints import derive_hints
from app.models.word import PartOfSpeech, WordEntry


class WordSeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    word: str
    part_of_speech: PartOfSpeech
    category: str
    definition: str
    attributes: list[str] = Field(min_length=1, max_length=8)
    # Optional: 4 hints, hardest first. Missing hints are derived from the metadata.
    hints: list[str] = Field(default_factory=list, max_length=4)

    def to_entry(self) -> WordEntry:
        entry = WordEntry(
            word=self.word,
            part_of_speech=self.part_of_speech,
            category=self.category,
            definition=self.definition,
            attributes=tuple(self.attributes),
            hints=tuple(self.hints),
        )
        return entry if entry.hints else replace(entry, hints=derive_hints(entry))


WordSeedFile = TypeAdapter(list[WordSeedItem])
