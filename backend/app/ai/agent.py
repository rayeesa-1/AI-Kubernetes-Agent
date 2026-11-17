"""Public AI entry point. Suggestions are never executed."""
from app.ai.analyzer import analyze_investigation

__all__ = ["analyze_investigation"]


def diagnose_cluster(payload=None):
    """Compatibility entry point; pass the phase-two investigation response."""
    if payload is None:
        return {"status": "skipped", "error": "No investigation evidence supplied"}
    return analyze_investigation(payload)
