from datetime import date

from pydantic import BaseModel, ConfigDict

from app.schemas.common import UtcTimestamp


class PuzzleTodayResponse(BaseModel):
    """Public facts about today's puzzle. Deliberately has no field that could carry the word."""

    model_config = ConfigDict(extra="forbid")

    game_date: date
    server_time: UtcTimestamp
    next_reset_at: UtcTimestamp


class PuzzleAnswerResponse(BaseModel):
    """The word of a finished game day (OQ-08)."""

    model_config = ConfigDict(extra="forbid")

    game_date: date
    word: str
