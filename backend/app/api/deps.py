from typing import Annotated, cast

from fastapi import Depends, Request

from app.services.daily_word_service import DailyWordService


def get_daily_word_service(request: Request) -> DailyWordService:
    return cast(DailyWordService, request.app.state.daily_word_service)


DailyWordServiceDep = Annotated[DailyWordService, Depends(get_daily_word_service)]
