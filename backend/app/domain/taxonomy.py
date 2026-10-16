"""Error taxonomy: parse and check the YAML tree (pure Python, no file or database access)."""

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

CODE_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")


class TaxonomyError(ValueError):
    """The taxonomy file is malformed."""


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wrong: str
    correct: str


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label_en: str
    label_fr: str
    description_en: str = ""
    description_fr: str = ""
    examples: list[Example] = []
    children: list["_Node"] = []


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    categories: list[_Node]


@dataclass(frozen=True)
class Category:
    code: str
    parent_code: str | None
    label_en: str
    label_fr: str
    description_en: str
    description_fr: str
    examples: list[dict[str, str]]
    sort_order: int


@dataclass(frozen=True)
class Taxonomy:
    version: int
    # Parents always come before their children.
    categories: list[Category] = field(default_factory=list)

    @property
    def codes(self) -> set[str]:
        return {category.code for category in self.categories}


def parent_code(code: str) -> str | None:
    head, _, _ = code.rpartition(".")
    return head or None


def parse_taxonomy(data: Any) -> Taxonomy:
    """Validate the loaded YAML and flatten the tree; raise TaxonomyError on any problem."""
    try:
        parsed = _File.model_validate(data)
    except ValueError as exc:
        raise TaxonomyError(f"invalid taxonomy file: {exc}") from exc

    categories: list[Category] = []

    def walk(nodes: list[_Node], parent: str | None) -> None:
        for index, node in enumerate(nodes):
            segments = node.code.split(".")
            if not all(CODE_SEGMENT.match(segment) for segment in segments):
                raise TaxonomyError(f"invalid code {node.code!r} (dotted snake_case expected)")
            if parent_code(node.code) != parent:
                raise TaxonomyError(f"{node.code!r} must be a direct child of {parent!r}")
            categories.append(
                Category(
                    code=node.code,
                    parent_code=parent,
                    label_en=node.label_en,
                    label_fr=node.label_fr,
                    description_en=node.description_en,
                    description_fr=node.description_fr,
                    examples=[example.model_dump() for example in node.examples],
                    sort_order=index,
                )
            )
            walk(node.children, node.code)

    walk(parsed.categories, None)
    codes = [category.code for category in categories]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        raise TaxonomyError(f"duplicate codes: {', '.join(duplicates)}")
    return Taxonomy(version=parsed.version, categories=categories)
