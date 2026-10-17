"""Batch enrichment service (M3.b): selection, call, split, writing, concurrency, editing.

Every test runs offline with `FakeProvider` (the network guard of tests/ai/conftest.py applies).
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.ai.gateway import Gateway
from app.ai.providers.fake import Failure, FakeProvider, Success
from app.ai.types import ErrorKind, ProviderRequest, ProviderResponse, UnavailableReason
from app.db.models import Enrichment, ExerciseTemplate, LexicalItem
from app.domain.enums import ContentOrigin, EnrichmentStatus, ItemStatus
from app.domain.usage_sheet import UsageSheet
from app.services import enrichment as en
from app.services import library
from app.services.items import transition_item
from tests.ai.conftest import FakeClock
from tests.enrichment_support import batch_output, broken_entry, generated_entry
from tests.factories import NOW, add_card, add_review
from tests.library_support import count, events

ProviderFactory = Callable[..., FakeProvider]
GatewayFactory = Callable[..., Gateway]
TERMS = ["to account for", "heteroskedasticity", "shed light on", "a large extent", "to draw on"]


def _factory(engine: Engine) -> Callable[[], Session]:
    return lambda: Session(engine, expire_on_commit=False)


def _add(
    engine: Engine,
    terms: list[str],
    status: ItemStatus = ItemStatus.QUEUED,
    *,
    deck_name: str = "Causal inference reading",
    domain: str | None = "econometrics",
    sentence: str | None = None,
) -> list[int]:
    with Session(engine) as session:
        deck = session.scalar(select(library.Deck).where(library.Deck.name == deck_name))
        if deck is None:
            deck = library.create_deck(session, name=deck_name, domain=domain, at=NOW)
        ids = []
        for term in terms:
            intake = ItemStatus.TRIAGE if status == ItemStatus.KNOWN else status
            item = library.create_item(
                session,
                term=term,
                at=NOW,
                origin=library.ItemOrigin.IMPORT,
                intake=intake,
                sentence=sentence,
            )
            if status == ItemStatus.KNOWN:
                transition_item(session, item, ItemStatus.KNOWN, NOW)
            library.add_item_to_deck(session, deck, item, NOW)
            ids.append(item.id)
        session.commit()
        return ids


def _run(engine: Engine, gateway: Gateway, clock: FakeClock, **kwargs: Any) -> en.RunReport:
    return en.run_enrichment(_factory(engine), gateway, clock=clock.now, **kwargs)


def _current(session: Session, item_id: int) -> Enrichment | None:
    return en.current_sheet(session, item_id)


def _single(term: str) -> Success:
    return Success(content={"sheets": [generated_entry(0, term)]})


# --- Happy path ----------------------------------------------------------------------------------


def test_a_batch_of_five_writes_five_sheets_templates_and_events(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    ids = _add(engine, TERMS)
    fake = provider_factory("a", Success(content=batch_output(TERMS)), model="fake-1")
    report = _run(engine, make_gateway(fake), clock)

    assert report.status == "ok" and report.reason is None
    assert (report.generated, report.needs_completion, report.remaining) == (5, 0, 0)
    assert report.item_ids == ids
    assert fake.calls == 1 and fake.requests[0].max_output_tokens == 7500
    with Session(engine) as session:
        for item_id in ids:
            sheet = _current(session, item_id)
            assert sheet is not None and sheet.status == EnrichmentStatus.COMPLETE
            assert (sheet.provider, sheet.model, sheet.prompt_version) == (
                "a",
                "fake-1",
                "enrichment.v1",
            )
            assert sheet.schema_version == 1 and not sheet.edited_by_user
            UsageSheet.model_validate(sheet.content)
        types = sorted(
            session.scalars(
                select(ExerciseTemplate.exercise_type).where(
                    ExerciseTemplate.lexical_item_id == ids[0]
                )
            )
        )
        assert types == sorted(
            ["gap_fill"] * 2
            + ["typed_recall"]
            + ["recognition_in_sentence"] * 2
            + ["listening_comprehension"]
            + ["sentence_production"] * 2
            + ["spoken_answer"]
        )
        template = session.scalar(
            select(ExerciseTemplate).where(ExerciseTemplate.exercise_type == "typed_recall")
        )
        assert template is not None and template.origin == ContentOrigin.AI
        assert template.direction == "productive" and template.prompt_version == "enrichment.v1"
        assert template.content["answer"] == "account for"
        generated = events(session, "enrichment.generated")
        assert len(generated) == 5 and {e["status"] for e in generated} == {"complete"}


def test_one_run_is_one_batch_and_the_rest_stays_pending(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    _add(engine, [*TERMS, "to rule out"])
    fake = provider_factory("a", Success(content=batch_output(TERMS)))
    report = _run(engine, make_gateway(fake), clock)
    assert report.generated == 5 and report.remaining == 1
    with Session(engine) as session:
        assert [i.term for i in en.list_pending(session)] == ["to rule out"]


def test_the_prompt_frames_the_terms_and_uses_the_deck_sentence(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    [item_id] = _add(engine, ["to account for"], sentence="We account for size.")
    with Session(engine) as session:
        session.get(library.DeckItem, 1).context_sentence = "Deck: we account for regions."  # type: ignore[union-attr]
        session.commit()
    fake = provider_factory("a", _single("to account for"))
    _run(engine, make_gateway(fake), clock)
    request = fake.requests[0]
    assert "<<<USER_DATA" in request.user
    assert '"sentence": "Deck: we account for regions."' in request.user
    assert '"domain": "econometrics"' in request.user
    assert request.max_output_tokens == 1500
    assert item_id


# --- Selection -----------------------------------------------------------------------------------


def test_triage_known_draft_and_archived_terms_are_never_selected(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    _add(engine, ["in triage"], ItemStatus.TRIAGE)
    _add(engine, ["already known"], ItemStatus.KNOWN)
    _add(engine, ["archived one"], ItemStatus.ARCHIVED)
    fake = provider_factory("a")
    report = _run(engine, make_gateway(fake), clock)
    assert report.status == "ok" and report.item_ids == [] and fake.calls == 0
    with Session(engine) as session:
        assert en.list_pending(session) == []


def test_explicit_ids_accept_any_status_but_archived(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    [triage_id] = _add(engine, ["to account for"], ItemStatus.TRIAGE)
    [archived_id] = _add(engine, ["archived one"], ItemStatus.ARCHIVED)
    fake = provider_factory("a", _single("to account for"))
    gateway = make_gateway(fake)
    with pytest.raises(en.ItemArchived):
        _run(engine, gateway, clock, item_ids=[triage_id, archived_id])
    assert fake.calls == 0
    report = _run(engine, gateway, clock, item_ids=[triage_id])
    assert report.generated == 1
    with pytest.raises(library.ItemNotFound):
        _run(engine, gateway, clock, item_ids=[999])


def test_deck_scope_and_unknown_deck(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    _add(engine, ["to account for"])
    [other] = _add(engine, ["heteroskedasticity"], deck_name="Other deck")
    fake = provider_factory("a", _single("heteroskedasticity"))
    with Session(engine) as session:
        deck_id = library.get_item(session, other).deck_links[0].deck_id
    report = _run(engine, make_gateway(fake), clock, deck_id=deck_id)
    assert report.item_ids == [other] and report.remaining == 0
    with pytest.raises(library.DeckNotFound):
        _run(engine, make_gateway(fake), clock, deck_id=999)


# --- Failures ------------------------------------------------------------------------------------


def test_an_invalid_sheet_is_repaired_then_split_into_single_terms(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    ids = _add(engine, TERMS)
    broken = batch_output(TERMS)
    broken["sheets"][2] = broken_entry(2, TERMS[2])
    bad_single = {"sheets": [broken_entry(0, TERMS[2])]}
    fake = provider_factory(
        "a",
        Success(content=broken),
        Success(content=broken),  # the repair fails too: incomplete
        _single(TERMS[0]),
        _single(TERMS[1]),
        Success(content=bad_single),
        Success(content=bad_single),  # still wrong alone: skeleton
        _single(TERMS[3]),
        _single(TERMS[4]),
    )
    report = _run(engine, make_gateway(fake), clock)

    assert report.status == "partial"
    assert (report.generated, report.needs_completion, report.remaining) == (4, 1, 0)
    assert "Your previous answer was rejected" in fake.requests[1].user
    assert "examples[0]" in fake.requests[1].user
    with Session(engine) as session:
        skeleton = _current(session, ids[2])
        assert skeleton is not None and skeleton.status == EnrichmentStatus.NEEDS_COMPLETION
        assert skeleton.content["translation_fr"] == []
        assert count(session, ExerciseTemplate) == 4 * 9
        assert all(
            _current(session, i).status == EnrichmentStatus.COMPLETE  # type: ignore[union-attr]
            for i in ids
            if i != ids[2]
        )
        statuses = [e["status"] for e in events(session, "enrichment.generated")]
        assert statuses.count("needs_completion") == 1 and statuses.count("complete") == 4
        # A skeleton is not picked up again automatically, only on request.
        assert en.list_pending(session) == []
        assert [i.id for i in en.list_pending(session, include_incomplete=True)] == [ids[2]]


def test_no_provider_configured_writes_nothing(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    _add(engine, TERMS)
    report = _run(engine, make_gateway(provider_factory("a", configured=False)), clock)
    assert report.status == "unavailable"
    assert report.reason is UnavailableReason.NO_PROVIDER_CONFIGURED
    assert report.remaining == 5 and report.generated == 0
    with Session(engine) as session:
        assert count(session, Enrichment) == 0 and count(session, ExerciseTemplate) == 0
        assert events(session, "enrichment.generated") == []


def test_a_quota_error_writes_nothing_and_is_not_split(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    _add(engine, TERMS)
    fake = provider_factory("a", Failure(ErrorKind.QUOTA_EXHAUSTED))
    report = _run(engine, make_gateway(fake), clock)
    assert (report.status, report.reason) == ("unavailable", UnavailableReason.QUOTA)
    assert fake.calls == 1


def test_all_failed_on_a_batch_is_split_and_a_quota_stops_the_split(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    ids = _add(engine, TERMS[:3])
    fake = provider_factory(
        "a",
        Failure(ErrorKind.BAD_REQUEST, "request too large", status_code=413),
        _single(TERMS[0]),
        Failure(ErrorKind.QUOTA_EXHAUSTED),
    )
    report = _run(engine, make_gateway(fake), clock)
    assert (report.status, report.reason) == ("partial", UnavailableReason.QUOTA)
    assert (report.generated, report.needs_completion, report.remaining) == (1, 0, 2)
    with Session(engine) as session:
        assert _current(session, ids[0]) is not None and _current(session, ids[1]) is None


def test_the_split_stops_at_the_time_cap(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    _add(engine, TERMS)
    fake = provider_factory(
        "a",
        Failure(ErrorKind.BAD_REQUEST, "too large"),
        Success(content={"sheets": [generated_entry(0, TERMS[0])]}, latency_s=80),
        Success(content={"sheets": [generated_entry(0, TERMS[1])]}, latency_s=80),
    )
    report = _run(engine, make_gateway(fake), clock)
    assert report.status == "partial" and report.reason is None
    assert (report.generated, report.remaining) == (2, 3)
    assert fake.calls == 3


def test_a_single_term_that_fails_gets_a_skeleton(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    [item_id] = _add(engine, ["to account for"])
    fake = provider_factory("a", Success(content="not json"))
    report = _run(engine, make_gateway(fake), clock)
    assert (report.status, report.needs_completion) == ("partial", 1)
    assert fake.calls == 2  # the call and its repair, no extra split call
    with Session(engine) as session:
        assert _current(session, item_id).status == EnrichmentStatus.NEEDS_COMPLETION  # type: ignore[union-attr]
        assert count(session, ExerciseTemplate) == 0


# --- Concurrency and stale results ---------------------------------------------------------------


class _Hook(FakeProvider):
    """Runs `hook` while the AI call is in progress (no session of the run is open then)."""

    def __init__(self, hook: Callable[[], None], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hook = hook

    def generate_json(self, request: ProviderRequest) -> ProviderResponse:
        self.hook()
        return super().generate_json(request)


def test_a_second_run_during_a_run_is_refused(
    engine: Engine, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    _add(engine, ["to account for"])
    refused: list[Exception] = []

    def second_run() -> None:
        try:
            _run(engine, gateway, clock)
        except en.EnrichmentRunning as exc:
            refused.append(exc)

    fake = _Hook(second_run, "a", [_single("to account for")])
    gateway = make_gateway(fake)
    assert _run(engine, gateway, clock).generated == 1
    assert len(refused) == 1 and refused[0].code == "enrichment_running"
    # The lock is released afterwards.
    assert _run(engine, gateway, clock).status == "ok"


def test_a_term_edited_during_the_call_keeps_the_users_sheet(
    engine: Engine, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    item_id, other_id = _add(engine, TERMS[:2])

    def user_types_a_sheet() -> None:
        with Session(engine) as session:
            en.save_sheet(session, item_id, UsageSheet(translation_fr=["expliquer"]), NOW)
            session.commit()

    fake = _Hook(user_types_a_sheet, "a", [Success(content=batch_output(TERMS[:2]))])
    report = _run(engine, make_gateway(fake), clock)
    assert (report.generated, report.superseded, report.status) == (1, 1, "ok")
    with Session(engine) as session:
        sheet = _current(session, item_id)
        assert sheet is not None and sheet.edited_by_user and sheet.provider is None
        assert count(session, Enrichment) == 2
        assert _current(session, other_id) is not None


def test_a_term_renamed_during_the_call_drops_the_result(
    engine: Engine, make_gateway: GatewayFactory, clock: FakeClock
) -> None:
    [item_id] = _add(engine, ["to account for"])

    def rename() -> None:
        with Session(engine) as session:
            library.update_item(
                session, library.get_item(session, item_id), {"term": "explain"}, NOW
            )
            session.commit()

    fake = _Hook(rename, "a", [_single("to account for")])
    assert _run(engine, make_gateway(fake), clock).superseded == 1
    with Session(engine) as session:
        assert _current(session, item_id) is None


# --- Regeneration --------------------------------------------------------------------------------


def _enrich_one(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> int:
    [item_id] = _add(engine, ["to account for"])
    _run(engine, make_gateway(provider_factory("a", _single("to account for"))), clock)
    return item_id


def test_an_edited_sheet_is_never_regenerated_without_consent(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    item_id = _enrich_one(engine, provider_factory, make_gateway, clock)
    with Session(engine) as session:
        first = _current(session, item_id)
        assert first is not None
        edited = UsageSheet.model_validate({**first.content, "usage_notes": "My own note."})
        en.save_sheet(session, item_id, edited, NOW, base_enrichment_id=first.id)
        session.commit()
    fake = provider_factory("b", _single("to account for"))
    gateway = make_gateway(fake)
    with pytest.raises(en.SheetEdited):
        _run(engine, gateway, clock, regenerate_id=item_id)
    with pytest.raises(en.SheetEdited):
        _run(engine, gateway, clock, item_ids=[item_id], regenerate_id=item_id)
    assert fake.calls == 0
    # Automatic runs and explicit ids leave it alone too.
    assert _run(engine, gateway, clock, item_ids=[item_id]).item_ids == []

    report = _run(engine, gateway, clock, regenerate_id=item_id, confirm_overwrite=True)
    assert report.generated == 1
    with Session(engine) as session:
        versions = en.list_versions(session, item_id)
        assert [v.version for v in versions] == [3, 2, 1]
        assert [v.is_current for v in versions] == [True, False, False]
        assert versions[1].edited_by_user and versions[1].content["usage_notes"] == "My own note."
        assert not versions[0].edited_by_user and versions[0].provider == "b"
        replaced = events(session, "enrichment.generated")[-1]["replaced_enrichment_id"]
        assert replaced == versions[1].enrichment_id


def test_a_failed_regeneration_keeps_the_sheet(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    item_id = _enrich_one(engine, provider_factory, make_gateway, clock)
    fake = provider_factory("a", Success(content="nope"))
    report = _run(engine, make_gateway(fake), clock, regenerate_id=item_id)
    assert (report.status, report.failed, report.needs_completion) == ("partial", 1, 0)
    with Session(engine) as session:
        assert _current(session, item_id).status == EnrichmentStatus.COMPLETE  # type: ignore[union-attr]
        assert count(session, Enrichment) == 1


def test_regeneration_keeps_edited_and_reviewed_templates(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    item_id = _enrich_one(engine, provider_factory, make_gateway, clock)
    with Session(engine) as session:
        templates = list(
            session.scalars(
                select(ExerciseTemplate).where(ExerciseTemplate.exercise_type == "gap_fill")
            )
        )
        edited, reviewed = templates
        en.update_exercise(
            session,
            edited.id,
            {"sentence": "My own ___ sentence.", "answer": "account for", "accepted": []},
            NOW,
        )
        item = session.get(LexicalItem, item_id)
        review = add_review(session, add_card(session, item))  # type: ignore[arg-type]
        review.exercise_template_id = reviewed.id
        session.commit()
        kept = {edited.id, reviewed.id}
    _run(
        engine,
        make_gateway(provider_factory("a", _single("to account for"))),
        clock,
        regenerate_id=item_id,
    )
    with Session(engine) as session:
        gap_fills = list(
            session.scalars(
                select(ExerciseTemplate).where(ExerciseTemplate.exercise_type == "gap_fill")
            )
        )
        assert kept <= {t.id for t in gap_fills} and len(gap_fills) == 4
        assert (
            session.get(ExerciseTemplate, edited.id).content["sentence"] == "My own ___ sentence."
        )  # type: ignore[union-attr]
        assert count(session, ExerciseTemplate) == 9 + 2


# --- Manual entry and editing --------------------------------------------------------------------


def test_manual_entry_on_a_term_without_sheet(engine: Engine) -> None:
    [item_id] = _add(engine, ["to account for"])
    with Session(engine) as session:
        view = en.save_sheet(
            session,
            item_id,
            UsageSheet(translation_fr=["expliquer"], definition_simple="to explain"),
            NOW,
        )
        session.commit()
        assert view.sheet_status == en.SheetState.EDITED and view.provider is None
        assert view.version == 1 and view.status == EnrichmentStatus.COMPLETE
        [edited] = events(session, "enrichment.edited")
        assert edited["base_enrichment_id"] is None
        [recall] = en.list_exercises(session, item_id)
        assert recall.exercise_type == "typed_recall" and recall.origin == ContentOrigin.USER
        assert recall.content["cue_fr"] == "expliquer"


def test_an_edit_copies_the_provenance_and_refuses_a_stale_base(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    item_id = _enrich_one(engine, provider_factory, make_gateway, clock)
    with Session(engine) as session:
        base = en.get_sheet(session, item_id)
        sheet = UsageSheet.model_validate({**base.content, "translation_fr": ["justifier"]})
        view = en.save_sheet(session, item_id, sheet, NOW, base_enrichment_id=base.enrichment_id)
        session.commit()
        assert (view.provider, view.prompt_version, view.edited_by_user) == (
            "a",
            "enrichment.v1",
            True,
        )
        with pytest.raises(en.SheetChanged) as caught:
            en.save_sheet(session, item_id, sheet, NOW, base_enrichment_id=base.enrichment_id)
        assert caught.value.extra["current_enrichment_id"] == view.enrichment_id
        # The derived recall follows the edit; the other templates are untouched.
        recall = [
            e for e in en.list_exercises(session, item_id) if e.exercise_type == "typed_recall"
        ]
        assert len(recall) == 1 and recall[0].content["cue_fr"] == "justifier"
        assert len(en.list_exercises(session, item_id)) == 9


def test_get_sheet_errors(engine: Engine) -> None:
    [item_id] = _add(engine, ["to account for"])
    with Session(engine) as session:
        with pytest.raises(en.SheetNotFound):
            en.get_sheet(session, item_id)
        with pytest.raises(library.ItemNotFound):
            en.get_sheet(session, 999)


def test_exercise_edit_is_validated_and_logged(
    engine: Engine,
    provider_factory: ProviderFactory,
    make_gateway: GatewayFactory,
    clock: FakeClock,
) -> None:
    item_id = _enrich_one(engine, provider_factory, make_gateway, clock)
    with Session(engine) as session:
        template = en.list_exercises(session, item_id)[0]
        with pytest.raises(en.InvalidExercise) as caught:
            en.update_exercise(session, template.id, {"sentence": "no gap", "answer": "x"}, NOW)
        assert caught.value.extra["errors"]
        with pytest.raises(en.ExerciseNotFound):
            en.update_exercise(session, 999, {}, NOW)
        out = en.update_exercise(
            session, template.id, {"sentence": "We ___ it.", "answer": "account for"}, NOW
        )
        session.commit()
        assert out.edited_by_user
        [event] = events(session, "exercise_template.edited")
        assert event == {
            "exercise_template_id": template.id,
            "lexical_item_id": item_id,
            "exercise_type": "gap_fill",
        }
