"""Turn a Pydantic JSON Schema into the subset a provider accepts.

`Model.model_json_schema()` produces `$defs` / `$ref`, `title`, `default` and validation keywords
(`minLength`, `minItems`...). Providers differ in what they accept, and the gateway validates every
answer with Pydantic anyway (D-042), so adapters send a *simpler* schema: it steers the model, it is
not the source of truth. Pure functions, no network.
"""

import json
from collections.abc import Mapping
from typing import Any

# Keywords dropped from every schema node. The Pydantic model still enforces them afterwards: an
# answer that breaks one is repaired once, then reported as `incomplete`.
DROPPED_KEYWORDS = frozenset(
    {
        "default",
        "examples",
        "title",
        "format",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minProperties",
        "maxProperties",
    }
)
_SCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
_SCHEMA_VALUES = ("items", "additionalProperties", "not", "if", "then", "else")


class SchemaConversionError(ValueError):
    """The schema uses something we cannot express (a recursive model, a remote `$ref`...)."""


def inline_refs(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Replace every `{"$ref": "#/$defs/X"}` by the definition of X and drop `$defs`.

    Keywords next to a `$ref` (for instance a `description`) win over the definition's own.
    A recursive model cannot be inlined and raises `SchemaConversionError`.
    """
    definitions: Mapping[str, Any] = schema.get("$defs", {})

    def resolve(node: Any, active: frozenset[str]) -> Any:
        if isinstance(node, list):
            return [resolve(item, active) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            reference = node["$ref"]
            name = reference.removeprefix("#/$defs/") if isinstance(reference, str) else ""
            if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
                raise SchemaConversionError(f"unsupported $ref {reference!r}")
            if name not in definitions:
                raise SchemaConversionError(f"unknown $ref {reference!r}")
            if name in active:
                raise SchemaConversionError(f"recursive model {name!r} cannot be inlined")
            target = resolve(definitions[name], active | {name})
            siblings = {k: resolve(v, active) for k, v in node.items() if k != "$ref"}
            return {**target, **siblings}
        return {k: resolve(v, active) for k, v in node.items() if k != "$defs"}

    return resolve(dict(schema), frozenset())


def simplify_schema(
    schema: Mapping[str, Any],
    *,
    closed_objects: bool,
    dropped: frozenset[str] = DROPPED_KEYWORDS,
) -> dict[str, Any]:
    """Inline references, drop the `dropped` keywords, turn `const` into `enum`, merge one-item
    `allOf`.

    With `closed_objects`, every object schema gets `additionalProperties: false` (recommended by
    Groq; the `AiOutput` models ignore extra fields, so it only constrains the model).
    Field names are never touched: `properties` is walked as a mapping of names to schemas.
    """
    return _simplify(inline_refs(schema), closed_objects, dropped)


def _simplify(node: Any, closed: bool, dropped: frozenset[str]) -> Any:
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in dropped or key == "$defs":
            continue
        if key == "properties" and isinstance(value, dict):
            result[key] = {name: _simplify(sub, closed, dropped) for name, sub in value.items()}
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            result[key] = [_simplify(sub, closed, dropped) for sub in value]
        elif key in _SCHEMA_VALUES and isinstance(value, dict):
            result[key] = _simplify(value, closed, dropped)
        elif key == "const":
            result["enum"] = [value]
        else:
            result[key] = value
    all_of = result.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
        merged = {k: v for k, v in result.items() if k != "allOf"}
        result = {**all_of[0], **merged}
    if closed and result.get("type") == "object" and "additionalProperties" not in result:
        result["additionalProperties"] = False
    return result


def to_groq_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Schema for Groq's `response_format.json_schema` in best-effort mode (`strict: false`).

    Groq documents `$defs`/`$ref` and `anyOf`, but inlining is just as valid and avoids relying on
    reference support per model. Optional fields stay optional (best-effort mode allows it).
    """
    return simplify_schema(schema, closed_objects=True)


# Gemini documents these bounds as accepted next to the plain structural keywords, so unlike the
# other providers it keeps them: they steer the model, Pydantic still enforces them afterwards.
GEMINI_KEPT_KEYWORDS = frozenset({"minimum", "maximum", "minItems", "maxItems"})
GEMINI_DROPPED_KEYWORDS = DROPPED_KEYWORDS - GEMINI_KEPT_KEYWORDS


def to_gemini_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Schema for Gemini's structured output (`responseFormat.text.schema`, D-056).

    The documented subset: types, `properties`, `required`, `additionalProperties`, `enum`, `items`,
    `anyOf`, `minimum`/`maximum`, `minItems`/`maxItems`; "not all JSON Schema features are
    supported", so `format`, `pattern`, string lengths and the rest are dropped, references inlined.
    """
    return simplify_schema(schema, closed_objects=True, dropped=GEMINI_DROPPED_KEYWORDS)


def to_ollama_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Schema for Ollama's `format` field. Its documentation lists no supported subset, so it gets
    the plainest one (no references, no validation keywords)."""
    return simplify_schema(schema, closed_objects=True)


def schema_instruction(schema: Mapping[str, Any]) -> str:
    """Prompt text that restates the schema (Ollama recommends it next to `format`; it is also
    the way to ask for JSON from a model that only has a plain JSON mode)."""
    compact = json.dumps(
        simplify_schema(schema, closed_objects=True), separators=(",", ":"), ensure_ascii=False
    )
    return (
        "Reply with a single JSON object that matches this JSON Schema, and nothing else:\n"
        f"{compact}"
    )
