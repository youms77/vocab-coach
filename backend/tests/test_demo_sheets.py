"""The hand-typed demo sheets (`content/demo/sheets.yaml`, D-110) follow the rules of generated
content (`app/domain/exercises.py`, the same checks as `EnrichmentEntry.problems`)."""

import pytest

from app.demo.dataset import DemoSheet, Fate, load_dataset
from app.domain import exercises as ex
from app.domain.normalize import normalize_term
from app.domain.usage_sheet import UsageSheet

DATASET = load_dataset()
FULL = [sheet for sheet in DATASET.sheets if sheet.full]
MINIMAL = [sheet for sheet in DATASET.sheets if not sheet.full]


def _problems(demo: DemoSheet) -> list[str]:
    term, sheet, exercises = demo.term, demo.sheet, demo.exercises
    assert exercises is not None
    where = demo.term
    gap = exercises.gap_fill
    forms = [gap.answer, *gap.accepted]
    family = [form.form for form in sheet.word_family]
    examples = [example.sentence for example in sheet.examples]
    problems = ex.check_examples(
        term, [(e.sentence, e.kind.value) for e in sheet.examples], forms, where
    )
    problems += ex.check_gap_fill(term, gap.sentence, gap.answer, gap.accepted, f"{where}.gap")
    problems += ex.check_not_copied(ex.fill_gap(gap.sentence, gap.answer), examples, where)
    recognition = exercises.recognition_in_sentence
    if not ex.contains_term(term, recognition.sentence, forms):
        problems.append(f"{where}.recognition: must contain the term")
    problems += ex.check_not_copied(recognition.sentence, examples, f"{where}.recognition")
    options = [normalize_term(d) for d in recognition.distractors]
    if len(set(options)) != 3 or normalize_term(recognition.meaning) in options:
        problems.append(f"{where}.recognition: three different wrong meanings are required")
    production, spoken = exercises.sentence_production, exercises.spoken_answer
    prompts = [
        (f"{where}.production", production.situation, production.example_answer),
        (f"{where}.spoken", spoken.question, spoken.example_answer),
    ]
    for at, prompt, answer in prompts:
        problems += ex.check_no_term(term, prompt, family, at)
        if not ex.contains_term(term, answer, forms):
            problems.append(f"{at}.example_answer: must use the term")
    return problems


@pytest.mark.parametrize("demo", FULL, ids=[sheet.term for sheet in FULL])
def test_full_sheet_follows_the_generated_content_rules(demo: DemoSheet) -> None:
    sheet = demo.sheet
    assert sheet.definition_simple and sheet.translation_fr
    assert len(sheet.examples) == 2
    assert sheet.pronunciation is not None
    assert sheet.pronunciation.ipa_us and sheet.pronunciation.stressed_syllable
    assert _problems(demo) == []


def test_minimal_sheets_have_a_french_translation_only() -> None:
    for demo in MINIMAL:
        expected = UsageSheet(translation_fr=demo.sheet.translation_fr)
        assert demo.sheet == expected, demo.term
        assert demo.sheet.translation_fr, demo.term


def test_every_discoverable_term_has_one_sheet_and_draft_or_known_terms_none() -> None:
    with_sheet = {sheet.term.lower() for sheet in DATASET.sheets}
    for term in DATASET.all_terms():
        expected = term.fate not in (Fate.DRAFT, Fate.KNOWN)
        assert (term.term.lower() in with_sheet) == expected, term.term


def test_full_sheets_mix_academic_and_spoken_examples_and_name_some_pitfalls() -> None:
    assert len(FULL) >= 25 + 40
    with_warning = [s for s in FULL if s.sheet.confusables or s.sheet.french_speaker_pitfalls]
    assert len(with_warning) >= len(FULL) // 3  # "when relevant"
