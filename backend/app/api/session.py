from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    ClientDep,
    OptionalPlayer,
    SessionServiceDep,
    SettingsDep,
    set_session_cookie,
)
from app.models.game import display_name_for

router = APIRouter(tags=["session"])


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turnstile_token: str = Field(default="", max_length=2048)


class SessionResponse(BaseModel):
    display_name: str


@router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionRequest,
    service: SessionServiceDep,
    settings: SettingsDep,
    client: ClientDep,
    player: OptionalPlayer,
    response: Response,
) -> SessionResponse:
    """Start an anonymous session. Requires a fresh, single-use Turnstile token."""
    response.headers["Cache-Control"] = "no-store"
    if player is not None:  # already has a valid session: nothing changes
        response.status_code = status.HTTP_200_OK
        return SessionResponse(display_name=display_name_for(player))
    created = await service.create(body.turnstile_token, client)
    set_session_cookie(response, settings, created.cookie_value)
    return SessionResponse(display_name=created.display_name)
