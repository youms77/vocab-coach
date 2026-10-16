"""Output of the `connection_test` task (used by the settings page in M2.b)."""

from app.ai.schemas import AiOutput


class ConnectionTestOutput(AiOutput):
    ok: bool
    echo: str
