from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def _format_utc(value: datetime) -> str:
    """ISO 8601 UTC with millisecond precision and a trailing Z (api-contract section 1)."""
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


UtcTimestamp = Annotated[datetime, PlainSerializer(_format_utc, return_type=str)]
