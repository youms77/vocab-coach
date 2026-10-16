# Provider answer fixtures

Realistic answers of the provider APIs, used by the adapter tests (no network).

They are **built from the official documentation** (see D-046 to D-050 in `docs/DECISIONS.md`) and
from public reports of real answers, with invented identifiers and no personal data. No real call was
made to produce them. Where the documentation is silent (the exact Groq 429 body, for instance) the
file says so in the adapter test that uses it; a first real call by the owner may call for an update.

`gemini/`: Google documents no error body for `generateContent` (only for the Interactions API), so
the classic shape (`error.code` = HTTP status, `error.status`, `details[]` with `ErrorInfo`,
`QuotaFailure.violations[].quotaId`, `RetryInfo.retryDelay`) comes from public forum reports, and
`error_429_interactions_*` / `error_402` follow the documented Interactions codes. The quota ids,
retry delays and the `FAILED_PRECONDITION` wording are reported values, not guaranteed ones.
