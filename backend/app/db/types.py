"""Column types shared by every model.

JSON columns: SQLAlchemy does not see in-place changes to a dict or list loaded from a JSON
column. `JSONDict` / `JSONList` wrap them in `MutableDict` / `MutableList`, which track
**top-level** changes (`obj.content["x"] = 1`, `obj.items.append(...)`). Changes to nested values
are not tracked: reassign the whole value (`obj.content = {**obj.content, ...}`) or call
`sqlalchemy.orm.attributes.flag_modified`.
"""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Dialect, Enum
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.types import TypeDecorator

JSONDict = MutableDict.as_mutable(JSON)
JSONList = MutableList.as_mutable(JSON)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime stored as UTC.

    Naive datetimes are refused, so comparing a naive and an aware value can never happen.
    Values come back with `tzinfo=UTC`.
    """

    impl = DateTime(timezone=False)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"UTCDateTime expects a datetime, got {type(value).__name__}")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"Naive datetime refused (use an aware datetime, e.g. UTC): {value!r}")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def closed_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """A value set fixed by the spec: stored as its string value, guarded by a named CHECK.

    `create_constraint=True` is required: SQLAlchemy 2 does not emit the CHECK by default.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
