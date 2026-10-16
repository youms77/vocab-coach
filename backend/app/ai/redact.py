"""Keep secrets out of messages. Some APIs put the key in the URL and library exceptions quote the
URL, so every error message goes through `mask_secrets` before it is stored, logged or returned."""

from collections.abc import Iterable
from urllib.parse import quote, quote_plus

MIN_SECRET_LENGTH = 6  # shorter values would also mask ordinary words
MASK = "***"


def mask_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of a secret (raw, URL-encoded, form-encoded) with `***`."""
    variants: set[str] = set()
    for secret in secrets:
        if len(secret) < MIN_SECRET_LENGTH:
            continue
        variants.update({secret, quote(secret, safe=""), quote_plus(secret)})
    # Longest first: an encoded variant must not be broken up by a shorter one.
    for variant in sorted(variants, key=len, reverse=True):
        text = text.replace(variant, MASK)
    return text


def clean_message(text: str, secrets: Iterable[str], limit: int) -> str:
    """Masked, then truncated to `limit` characters (masking first: a cut key would escape it)."""
    return mask_secrets(text, secrets)[:limit]
