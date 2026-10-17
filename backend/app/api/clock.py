"""The current time as a FastAPI dependency, so tests can share the gateway's fake clock (D-097)."""

from datetime import datetime
from typing import Annotated

from fastapi import Depends

from app.db.base import utcnow


def get_now() -> datetime:
    return utcnow()


NowDep = Annotated[datetime, Depends(get_now)]
