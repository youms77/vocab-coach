"""User settings endpoints (the registry of `app/domain/settings_defaults.py`), D-064.

`GET` lists every setting with its default and bounds, so the settings page can build its controls
from the answer. `PATCH` changes several at once, all or nothing. Secrets are not settings: keys go
through `/api/ai/providers/{name}/credential`.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.errors import api_error, require_database
from app.config import get_settings
from app.db.engine import get_engine, get_session
from app.db.settings_store import get_all_settings, set_setting
from app.domain.settings_defaults import SETTINGS, SettingError
from app.services.demo_guard import is_demo

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_database)])

SessionDep = Annotated[Session, Depends(get_session)]
EngineDep = Annotated[Engine, Depends(get_engine)]


class SettingInfo(BaseModel):
    value: Any
    default: Any
    is_default: bool
    type: str  # "int", "float", "str" or "list"
    minimum: float | None
    maximum: float | None
    choices: list[str] | None
    item_choices: list[str] | None


def _describe_all(session: Session) -> dict[str, SettingInfo]:
    values = get_all_settings(session)
    return {
        key: SettingInfo(
            value=values[key],
            default=spec.default_value(),
            is_default=values[key] == spec.default,
            type=spec.type.__name__,
            minimum=spec.minimum,
            maximum=spec.maximum,
            choices=list(spec.choices) if spec.choices is not None else None,
            item_choices=list(spec.item_choices) if spec.item_choices is not None else None,
        )
        for key, spec in SETTINGS.items()
    }


@router.get("", response_model=dict[str, SettingInfo])
def list_settings(session: SessionDep) -> dict[str, SettingInfo]:
    return _describe_all(session)


@router.patch("", response_model=dict[str, SettingInfo])
def update_settings(
    changes: dict[str, Any], session: SessionDep, engine: EngineDep
) -> dict[str, SettingInfo]:
    # Provider order is part of the owner's real setup: the demo database leaves it alone.
    if "ai_provider_order" in changes and is_demo(get_settings(), engine):
        raise api_error(
            409, "demo_read_only", "The demo database is read-only for AI keys and provider order."
        )
    try:
        for key, value in changes.items():
            set_setting(session, key, value)
    except SettingError as exc:
        session.rollback()
        raise api_error(422, "invalid_setting", str(exc), key=key) from None
    session.commit()
    return _describe_all(session)
