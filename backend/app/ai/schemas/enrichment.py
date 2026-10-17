"""Output of the `enrichment` task: usage sheets and exercise sentences for a batch of 1 to 5 terms.

Each entry is flat (sheet fields, then exercises) so the schema stays three object levels deep
(D-056). The business rules of `app/domain/exercises.py` run in a validator that reads the batch
from the validation context (`{"terms": {ref: term}}`, D-079): a broken rule is a validation error,
so the gateway asks for one repair, then answers `incomplete`.
"""

from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from app.ai.schemas import AiOutput
from app.domain import exercises as ex
from app.domain.normalize import normalize_term
from app.domain.usage_sheet import GeneratedSheet

ENRICHMENT_BATCH_SIZE = 5  # low end of SPEC §7 (5 to 10): Groq's 8 000 tokens per minute, D-051

Sentence = Annotated[str, Field(min_length=1, max_length=400)]
Form = Annotated[str, Field(min_length=1, max_length=300)]


class _Part(BaseModel):
    model_config = ConfigDict(extra="ignore")


class GapFillOut(_Part):
    sentence: Sentence
    answer: Form
    accepted: Annotated[list[Form], Field(max_length=8)]


class RecognitionOut(_Part):
    sentence: Sentence
    meaning: Sentence
    meaning_fr: Sentence
    distractors: Annotated[list[Sentence], Field(min_length=3, max_length=3)]


class ProductionOut(_Part):
    situation: Sentence
    example_answer: Sentence


class SpokenOut(_Part):
    question: Sentence
    example_answer: Sentence


class EnrichmentEntry(GeneratedSheet):
    ref: Annotated[int, Field(ge=0, le=ENRICHMENT_BATCH_SIZE - 1)]
    term: Form
    gap_fills: Annotated[list[GapFillOut], Field(min_length=2, max_length=2)]
    recognitions: Annotated[list[RecognitionOut], Field(min_length=2, max_length=2)]
    productions: Annotated[list[ProductionOut], Field(min_length=2, max_length=2)]
    spoken: SpokenOut

    def answer_forms(self) -> list[str]:
        forms: list[str] = []
        for gap in self.gap_fills:
            for form in (gap.answer, *gap.accepted):
                if form not in forms:
                    forms.append(form)
        return forms

    def problems(self, term: str) -> list[str]:
        """Business rules for the expected `term` (messages name locations, never text)."""
        where = f"sheets[ref={self.ref}]"
        forms = self.answer_forms()
        family = [form.form for form in self.word_family]
        examples = [example.sentence for example in self.examples]
        problems = ex.check_examples(
            term, [(e.sentence, e.kind.value) for e in self.examples], forms, where
        )
        for i, gap in enumerate(self.gap_fills):
            at = f"{where}.gap_fills[{i}]"
            problems += ex.check_gap_fill(term, gap.sentence, gap.answer, gap.accepted, at)
            problems += ex.check_not_copied(ex.fill_gap(gap.sentence, gap.answer), examples, at)
        for i, recognition in enumerate(self.recognitions):
            at = f"{where}.recognitions[{i}]"
            if not ex.contains_term(term, recognition.sentence, forms):
                problems.append(f"{at}.sentence: must contain the term")
            problems += ex.check_not_copied(recognition.sentence, examples, at)
            options = [normalize_term(d) for d in recognition.distractors]
            if len(set(options)) != 3 or normalize_term(recognition.meaning) in options:
                problems.append(f"{at}.distractors: three different wrong meanings are required")
        prompts = [
            (f"{where}.productions[{i}]", p.situation, p.example_answer)
            for i, p in enumerate(self.productions)
        ]
        prompts.append((f"{where}.spoken", self.spoken.question, self.spoken.example_answer))
        for at, prompt, answer in prompts:
            problems += ex.check_no_term(term, prompt, family, at)
            if not ex.contains_term(term, answer, forms):
                problems.append(f"{at}.example_answer: must use the term")
        return problems


class EnrichmentBatchOutput(AiOutput):
    sheets: Annotated[list[EnrichmentEntry], Field(min_length=1, max_length=ENRICHMENT_BATCH_SIZE)]

    @model_validator(mode="after")
    def matches_the_batch(self, info: ValidationInfo) -> Self:
        terms: dict[int, str] | None = (info.context or {}).get("terms")
        if terms is None:
            return self
        refs = [entry.ref for entry in self.sheets]
        problems: list[str] = []
        if len(set(refs)) != len(refs):
            problems.append("sheets: each ref must appear only once")
        unknown = sorted(set(refs) - set(terms))
        missing = sorted(set(terms) - set(refs))
        if unknown:
            problems.append(f"sheets: unknown refs {unknown}")
        if missing:
            problems.append(f"sheets: missing refs {missing}")
        for entry in self.sheets:
            term = terms.get(entry.ref)
            if term is None:
                continue
            if normalize_term(entry.term) != normalize_term(term):
                problems.append(
                    f"sheets[ref={entry.ref}].term: must be the term given for this ref"
                )
                continue
            problems += entry.problems(term)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def batch_context(terms: dict[int, str]) -> dict[str, Any]:
    return {"terms": dict(terms)}
