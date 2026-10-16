"""AI gateway (M2): the only place that talks to AI providers.

    from app.ai import get_gateway
    result = get_gateway().generate_json("connection_test", {"text": "ping"}, ConnectionTestOutput)

Callers: call the AI first, then write the results in your own short transaction. Never keep a write
transaction open while waiting for a provider (D-038).
"""

from app.ai.gateway import Gateway, get_gateway
from app.ai.types import AiResult, AiStatus, AudioClip, UnavailableReason

__all__ = ["AiResult", "AiStatus", "AudioClip", "Gateway", "UnavailableReason", "get_gateway"]
