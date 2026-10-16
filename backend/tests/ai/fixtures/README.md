# Provider answer fixtures

Realistic answers of the provider APIs, used by the adapter tests (no network).

They are **built from the official documentation** (see D-046 to D-050 in `docs/DECISIONS.md`) and
from public reports of real answers, with invented identifiers and no personal data. No real call was
made to produce them. Where the documentation is silent (the exact Groq 429 body, for instance) the
file says so in the adapter test that uses it; a first real call by the owner may call for an update.
