"""Load `content/error_taxonomy.yaml` and synchronise it into `error_category`."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.db.models import ErrorCategory
from app.domain.enums import ErrorCategoryStatus
from app.domain.taxonomy import Taxonomy, parse_taxonomy

TAXONOMY_FILE = REPO_ROOT / "content" / "error_taxonomy.yaml"


def load_taxonomy(path: Path = TAXONOMY_FILE) -> Taxonomy:
    with path.open(encoding="utf-8") as file:
        return parse_taxonomy(yaml.safe_load(file))


@dataclass(frozen=True)
class SyncResult:
    added: int
    updated: int


def sync_taxonomy(session: Session, taxonomy: Taxonomy | None = None) -> SyncResult:
    """Insert missing built-in categories and refresh built-in texts. Idempotent.

    Never deletes, and never touches categories that are not built in (user or AI proposals),
    even when one has the same code as a built-in entry. The caller commits.
    """
    taxonomy = taxonomy or load_taxonomy()
    existing = {category.code: category for category in session.scalars(select(ErrorCategory))}
    added = updated = 0
    for entry in taxonomy.categories:  # parents first
        parent = existing.get(entry.parent_code) if entry.parent_code else None
        fields = {
            "parent_id": parent.id if parent else None,
            "label_en": entry.label_en,
            "label_fr": entry.label_fr,
            "description_en": entry.description_en,
            "description_fr": entry.description_fr,
            "examples": entry.examples,
            "sort_order": entry.sort_order,
        }
        category = existing.get(entry.code)
        if category is None:
            category = ErrorCategory(
                code=entry.code, is_builtin=True, status=ErrorCategoryStatus.ACTIVE, **fields
            )
            session.add(category)
            session.flush()  # children need the id
            existing[entry.code] = category
            added += 1
        elif category.is_builtin:
            changed = False
            for name, value in fields.items():
                if getattr(category, name) != value:
                    setattr(category, name, value)
                    changed = True
            updated += changed
    session.flush()
    return SyncResult(added=added, updated=updated)
