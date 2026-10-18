"""The demo's fictional AI outputs (app/demo/fictional_ai.py) fit the real schemas (D-163)."""

import pytest

from app.db.taxonomy import load_taxonomy
from app.demo import fictional_ai
from app.demo.dataset import DemoDrill, ErrorTemplate, load_dataset
from app.domain.drills import grade_item, options_order
from app.domain.enums import ErrorSource
from app.domain.sentences import split_sentences
from app.domain.transcript_import import split_units
from app.services import corrections, transcripts

DATASET = load_dataset()
CODES = load_taxonomy().codes
FILLER = DATASET.fillers[0]


def _family(code: str) -> set[str]:
    return {c for c in CODES if c == code or c.startswith(code + ".")}


def _prepared(text: str) -> corrections.Prepared:
    return corrections.Prepared(
        attempt_id=1,
        text=text,
        prompt="",
        source=ErrorSource.WRITING,
        sentences=split_sentences(text),
        targets=[],
        taxonomy=dict.fromkeys(CODES, ""),
    )


@pytest.mark.parametrize("template", DATASET.error_templates, ids=lambda t: t.original[:40])
def test_every_template_gives_a_valid_correction(template: ErrorTemplate) -> None:
    prepared = _prepared(f"{FILLER} {template.original}")
    output = fictional_ai.correction_output(prepared, [template])
    (error,) = output.errors
    assert (error.wrong, error.correction) == (template.wrong, template.correction)
    assert error.explanation_fr == template.explanation_fr
    assert [s.status for s in output.sentences] == ["correct", "corrected"]
    assert template.correction in output.corrected_text


@pytest.mark.parametrize(
    "template",
    [
        t
        for t in DATASET.error_templates
        if not t.code.startswith(transcripts.EXCLUDED_CODE_PREFIXES)
    ],
    ids=lambda t: t.original[:40],
)
def test_every_template_gives_a_valid_transcript_analysis(template: ErrorTemplate) -> None:
    text = f"{FILLER} {template.original}"
    units = split_units(text)
    prepared = transcripts.Prepared(
        attempt_id=1,
        units=units,
        contexts={},
        taxonomy={
            code: "" for code in CODES if not code.startswith(transcripts.EXCLUDED_CODE_PREFIXES)
        },
        errors_at=None,
    )
    output = fictional_ai.transcript_chunk(prepared, units, [template])
    assert [e.wrong for e in output.errors] == [template.wrong]


def test_a_template_that_matches_no_sentence_is_a_dataset_bug() -> None:
    other = DATASET.error_templates[1]
    prepared = _prepared(FILLER)
    with pytest.raises(ValueError, match="match no sentence"):
        fictional_ai.correction_output(prepared, [other])


@pytest.mark.parametrize("drill", DATASET.drills, ids=lambda d: d.code)
def test_every_drill_fits_the_drill_schema_and_its_grading(drill: DemoDrill) -> None:
    output = fictional_ai.drill_output(drill, _family(drill.code))
    assert len(output.items) == len(drill.items)
    for index, (item, demo) in enumerate(zip(output.items, drill.items, strict=True)):
        stored = item.model_dump(mode="json")
        shown = options_order(1, index, stored["options"]) if demo.kind == "choice" else None
        right = grade_item(
            stored,
            shown,
            answer=demo.answer if demo.kind == "gap_fill" else None,
            choice_index=shown.index(demo.answer) if shown else None,
        )
        assert right.outcome == "exact"
        if demo.kind == "gap_fill":
            wrong = grade_item(stored, None, answer=demo.wrong, choice_index=None)
            assert wrong.outcome == "wrong"  # the learner's mistake really is graded as one


def test_the_drills_cover_several_categories_and_themes() -> None:
    assert len({d.code for d in DATASET.drills}) >= 5
    assert {i.theme for d in DATASET.drills for i in d.items} == {
        "campus",
        "data_economics",
        "everyday",
    }
