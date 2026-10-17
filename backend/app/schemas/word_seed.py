"""Format of the private word list file used to seed SQLite.

The file is a JSON array kept outside the repository (for example backend/secrets/words.json,
which is git-ignored, or /opt/tenq/secrets/words.json on the server).
"""

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.models.word import PartOfSpeech, WordEntry


class WordSeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    word: str
    part_of_speech: PartOfSpeech
    category: str
    definition: str
    attributes: list[str] = Field(min_length=1, max_length=8)

    def to_entry(self) -> WordEntry:
        return WordEntry(
            word=self.word,
            part_of_speech=self.part_of_speech,
            category=self.category,
            definition=self.definition,
            attributes=tuple(self.attributes),
        )


WordSeedFile = TypeAdapter(list[WordSeedItem])
