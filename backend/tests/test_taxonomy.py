import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ErrorCategory
from app.db.taxonomy import load_taxonomy, sync_taxonomy
from app.domain.enums import ErrorCategoryStatus
from app.domain.taxonomy import TaxonomyError, parent_code, parse_taxonomy

# docs/SPEC.md section 4, module E.
REQUIRED_CODES = {
    "grammar",
    "lexis",
    "register",
    "discourse",
    "spelling",
    "pronunciation",
    *(
        f"grammar.preposition.{leaf}"
        for leaf in ("time", "place", "movement", "dependent", "fixed_expression", "by_for_since")
    ),
    *(
        f"grammar.tense.{leaf}"
        for leaf in (
            "past_simple_vs_present_perfect",
            "present_simple_vs_continuous",
            "future_forms",
            "sequence_of_tenses",
        )
    ),
    *(
        f"grammar.{leaf}"
        for leaf in (
            "article",
            "agreement",
            "word_order",
            "question_form",
            "countability",
            "modal",
            "other",
        )
    ),
    *(f"lexis.{leaf}" for leaf in ("false_friend", "wrong_word", "collocation", "word_form")),
    "register.too_informal",
    "register.too_formal",
    "discourse.connectors",
    "discourse.cohesion",
    "pronunciation.sound",
    "pronunciation.word_stress",
    "pronunciation.intelligibility",
}
# Intermediate nodes implied by the required codes.
INTERMEDIATE_CODES = {"grammar.preposition", "grammar.tense"}


def _count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(ErrorCategory)) or 0


def test_file_covers_exactly_the_spec_codes() -> None:
    taxonomy = load_taxonomy()
    assert taxonomy.codes == REQUIRED_CODES | INTERMEDIATE_CODES
    for category in taxonomy.categories:
        assert category.label_en and category.label_fr, category.code


def test_sync_twice_is_idempotent(session: Session) -> None:
    first = sync_taxonomy(session)
    session.commit()
    count = _count(session)
    second = sync_taxonomy(session)
    session.commit()

    assert first.added == count == len(REQUIRED_CODES | INTERMEDIATE_CODES)
    assert (second.added, second.updated) == (0, 0)
    assert _count(session) == count


def test_parents_match_code_prefixes(session: Session) -> None:
    sync_taxonomy(session)
    by_id = {category.id: category for category in session.scalars(select(ErrorCategory))}
    for category in by_id.values():
        parent = by_id.get(category.parent_id) if category.parent_id else None
        assert (parent.code if parent else None) == parent_code(category.code)
        assert category.is_builtin


def test_user_category_is_preserved_and_builtin_text_is_refreshed(session: Session) -> None:
    sync_taxonomy(session)
    article = session.scalars(select(ErrorCategory).filter_by(code="grammar.article")).one()
    user = ErrorCategory(
        code="grammar.article.zero_article",
        parent_id=article.id,
        label_en="My label",
        label_fr="Mon libellé",
        is_builtin=False,
        status=ErrorCategoryStatus.PROPOSED,
    )
    session.add(user)
    article.label_en = "Edited by mistake"
    session.commit()

    result = sync_taxonomy(session)
    session.commit()

    assert result.updated == 1
    assert article.label_en == "Articles"
    assert (user.label_en, user.status) == ("My label", ErrorCategoryStatus.PROPOSED)


def test_malformed_tree_is_rejected() -> None:
    bad_parent = {
        "version": 1,
        "categories": [
            {"code": "grammar", "label_en": "G", "label_fr": "G", "children": [
                {"code": "lexis.collocation", "label_en": "C", "label_fr": "C"},
            ]},
        ],
    }  # fmt: skip
    with pytest.raises(TaxonomyError, match="direct child"):
        parse_taxonomy(bad_parent)
    with pytest.raises(TaxonomyError, match="invalid taxonomy"):
        parse_taxonomy({"version": 1, "categories": [{"code": "x", "label_en": "X"}]})
