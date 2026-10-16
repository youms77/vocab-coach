"""Secret masking."""

from urllib.parse import quote, quote_plus

from app.ai.redact import clean_message, mask_secrets

KEY = "AIzaSy/key+with spaces&odd=chars"


def test_raw_and_encoded_forms_are_masked() -> None:
    text = f"raw {KEY}; url {quote(KEY, safe='')}; form {quote_plus(KEY)}; done"
    assert mask_secrets(text, [KEY]) == "raw ***; url ***; form ***; done"


def test_short_values_are_left_alone() -> None:
    assert mask_secrets("a short value 12345 stays", ["12345"]) == "a short value 12345 stays"


def test_several_secrets_and_repeats() -> None:
    assert mask_secrets("a-secret-1 b-secret-2 a-secret-1", ["a-secret-1", "b-secret-2"]) == (
        "*** *** ***"
    )


def test_masking_happens_before_truncation() -> None:
    secret = "S3CRET-" + "x" * 30
    message = "y" * 280 + secret  # truncation at 300 would cut the secret in two
    cleaned = clean_message(message, [secret], 300)
    assert "S3CRET" not in cleaned and len(cleaned) <= 300


def test_no_secrets_is_a_no_op() -> None:
    assert mask_secrets("nothing to hide", []) == "nothing to hide"
