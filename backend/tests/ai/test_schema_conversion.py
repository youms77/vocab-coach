"""Pydantic schema -> provider schema, on the shape of the M3 usage sheets.

Nested models, lists, enumerations, optional fields, validation keywords: what a real task output
looks like. The converted schema steers the model; Pydantic still validates every answer.
"""

import copy
import json
from collections.abc import Iterator
from enum import StrEnum
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field

from app.ai.providers.schema import (
    DROPPED_KEYWORDS,
    GEMINI_DROPPED_KEYWORDS,
    SchemaConversionError,
    inline_refs,
    schema_instruction,
    simplify_schema,
    to_gemini_schema,
    to_groq_schema,
    to_ollama_schema,
)
from app.ai.schemas import AiOutput
from app.ai.schemas.connection_test import ConnectionTestOutput


class Register(StrEnum):
    FORMAL = "formal"
    NEUTRAL = "neutral"
    INFORMAL = "informal"


class Example(BaseModel):
    sentence: str = Field(description="One natural sentence using the headword.")
    translation_fr: str | None = None


class Sense(BaseModel):
    definition: str = Field(min_length=3, max_length=200)
    style: Register = Register.NEUTRAL
    examples: list[Example] = Field(min_length=1, max_length=5)
    collocations: list[str] = []


class UsageSheetLike(AiOutput):
    headword: str
    part_of_speech: Literal["noun", "verb", "adjective"]
    level: int = Field(ge=1, le=6)
    senses: list[Sense]
    confusions: list[str] | None = None
    note: str | None = None


def schema_nodes(node: Any) -> Iterator[dict[str, Any]]:
    """Every schema node (not the field names under `properties`)."""
    if not isinstance(node, dict):
        return
    yield node
    for sub in node.get("properties", {}).values():
        yield from schema_nodes(sub)
    for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
        for sub in node.get(key, []):
            yield from schema_nodes(sub)
    for key in ("items", "additionalProperties"):
        yield from schema_nodes(node.get(key))


def everything(node: Any) -> Iterator[str]:
    """Every key anywhere, field names included: to prove a reference is really gone."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from everything(value)
    elif isinstance(node, list):
        for item in node:
            yield from everything(item)


RAW = UsageSheetLike.model_json_schema()


def test_the_raw_pydantic_schema_is_what_we_have_to_simplify() -> None:
    keys = set(everything(RAW))
    assert {"$defs", "$ref", "title", "default", "minLength", "minItems", "maximum"} <= keys


@pytest.mark.parametrize("convert", [to_groq_schema, to_ollama_schema])
def test_references_and_unsupported_keywords_are_gone(convert: Any) -> None:
    schema = convert(RAW)
    keys = set(everything(schema))
    assert "$defs" not in keys and "$ref" not in keys
    for node in schema_nodes(schema):
        assert not DROPPED_KEYWORDS & node.keys(), node


@pytest.mark.parametrize("convert", [to_groq_schema, to_ollama_schema, to_gemini_schema])
def test_structure_enums_and_descriptions_survive(convert: Any) -> None:
    schema = convert(RAW)
    assert schema["type"] == "object"
    assert schema["required"] == ["headword", "part_of_speech", "level", "senses"]
    assert schema["properties"]["part_of_speech"]["enum"] == ["noun", "verb", "adjective"]
    sense = schema["properties"]["senses"]["items"]  # a nested model, inlined
    assert sense["type"] == "object"
    assert sense["required"] == ["definition", "examples"]
    assert sense["properties"]["style"]["enum"] == ["formal", "neutral", "informal"]
    example = sense["properties"]["examples"]["items"]  # nested two levels deep
    assert example["properties"]["sentence"]["description"] == (
        "One natural sentence using the headword."
    )
    assert example["required"] == ["sentence"]


@pytest.mark.parametrize("convert", [to_groq_schema, to_ollama_schema, to_gemini_schema])
def test_optional_fields_stay_optional_and_nullable(convert: Any) -> None:
    schema = convert(RAW)
    assert "confusions" not in schema["required"] and "note" not in schema["required"]
    assert schema["properties"]["note"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert schema["properties"]["confusions"]["anyOf"][1] == {"type": "null"}
    assert schema["properties"]["confusions"]["anyOf"][0]["items"] == {"type": "string"}


@pytest.mark.parametrize("convert", [to_groq_schema, to_ollama_schema, to_gemini_schema])
def test_every_object_is_closed(convert: Any) -> None:
    objects = [n for n in schema_nodes(convert(RAW)) if n.get("type") == "object"]
    assert len(objects) == 3  # the sheet, a sense, an example
    assert all(node["additionalProperties"] is False for node in objects)


def test_field_names_are_never_mistaken_for_keywords() -> None:
    class Odd(AiOutput):
        title: str
        default: str
        format: int
        pattern: list[str] = []

    schema = to_groq_schema(Odd.model_json_schema())
    assert set(schema["properties"]) == {"title", "default", "format", "pattern"}
    assert schema["required"] == ["title", "default", "format"]


def test_the_input_schema_is_not_modified() -> None:
    before = copy.deepcopy(RAW)
    to_groq_schema(RAW)
    to_ollama_schema(RAW)
    assert before == RAW


def test_a_simple_schema_is_still_simple() -> None:
    schema = to_ollama_schema(ConnectionTestOutput.model_json_schema())
    assert schema == {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
        "required": ["ok", "echo"],
        "additionalProperties": False,
    }


def test_open_dictionaries_keep_their_value_schema() -> None:
    class WithMap(AiOutput):
        scores: dict[str, int]

    schema = to_groq_schema(WithMap.model_json_schema())
    assert schema["properties"]["scores"]["additionalProperties"] == {"type": "integer"}


def test_const_becomes_a_single_value_enum() -> None:
    assert simplify_schema({"type": "string", "const": "x"}, closed_objects=False) == {
        "type": "string",
        "enum": ["x"],
    }


def test_a_one_item_all_of_is_merged() -> None:
    schema = {"allOf": [{"type": "string", "enum": ["a"]}], "description": "d"}
    assert simplify_schema(schema, closed_objects=False) == {
        "type": "string",
        "enum": ["a"],
        "description": "d",
    }


def test_keywords_next_to_a_ref_win_over_the_definition() -> None:
    schema = {
        "$defs": {"X": {"type": "string", "description": "from the definition"}},
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/X", "description": "from the field"}},
    }
    assert inline_refs(schema)["properties"]["a"] == {
        "type": "string",
        "description": "from the field",
    }


def test_recursive_models_cannot_be_inlined() -> None:
    class Node(BaseModel):
        children: list["Node"] = []

    with pytest.raises(SchemaConversionError, match="recursive"):
        inline_refs(Node.model_json_schema())


@pytest.mark.parametrize("reference", ["#/$defs/Missing", "http://example.com/schema.json", "#"])
def test_unknown_or_remote_references_are_refused(reference: str) -> None:
    with pytest.raises(SchemaConversionError):
        inline_refs({"type": "object", "properties": {"a": {"$ref": reference}}})


def test_the_prompt_instruction_carries_the_compact_schema() -> None:
    text = schema_instruction(RAW)
    assert "JSON" in text and "$defs" not in text and "minLength" not in text
    embedded = json.loads(text.split("nothing else:\n", 1)[1])
    assert embedded == to_groq_schema(RAW)
    assert "\n" not in text.split("nothing else:\n", 1)[1]  # compact: a single line


# --- Gemini (D-056): documented bounds are kept, the rest is dropped ----------------------------


def test_gemini_keeps_the_documented_bounds_and_drops_the_other_keywords() -> None:
    schema = to_gemini_schema(RAW)
    keys = set(everything(schema))
    assert "$defs" not in keys and "$ref" not in keys
    for node in schema_nodes(schema):
        assert not GEMINI_DROPPED_KEYWORDS & node.keys(), node
    assert schema["properties"]["level"]["minimum"] == 1
    assert schema["properties"]["level"]["maximum"] == 6
    examples = schema["properties"]["senses"]["items"]["properties"]["examples"]
    assert examples["minItems"] == 1 and examples["maxItems"] == 5
    definition = schema["properties"]["senses"]["items"]["properties"]["definition"]
    assert definition == {"type": "string"}  # string lengths are not in the documented subset


def test_the_gemini_policy_differs_from_the_others_by_the_bounds_only() -> None:
    assert {
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
    } == DROPPED_KEYWORDS - GEMINI_DROPPED_KEYWORDS
    plain = to_groq_schema(RAW)
    assert plain["properties"]["level"] == {"type": "integer"}  # Groq output is unchanged


def test_gemini_does_not_modify_the_input_and_keeps_field_names() -> None:
    class Odd(AiOutput):
        minimum: int = Field(ge=0)
        maxItems: list[str] = []

    before = copy.deepcopy(RAW)
    to_gemini_schema(RAW)
    assert before == RAW
    schema = to_gemini_schema(Odd.model_json_schema())
    assert set(schema["properties"]) == {"minimum", "maxItems"}
    assert schema["properties"]["minimum"]["minimum"] == 0
