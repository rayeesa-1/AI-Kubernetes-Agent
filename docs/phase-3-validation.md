# Phase 3 validation

29 backend tests passed using Python 3.12 and unittest: 11 existing investigation
tests and 18 AI/API tests.

Covered: HTTPX request format; bounded retries for transient HTTP/transport failures;
non-retryable auth/billing errors; invalid or truncated completions; strict diagnosis
schema; evidence references; command syntax checks; confidence caps; secret-pattern
redaction; bounded prompts; evidence preservation; health and investigation routes;
and no automatic command execution by the AI layer.

Frontend and Kubernetes collection modules are unchanged from the phase-two baseline.

Model calls use HTTPX mock transports or mocked completions. No paid model call
was made, and no private credentials are included. Docker builds, Windows PowerShell
execution, your live kind cluster, and live OpenRouter access were not exercised here.
Follow docs/phase-3-ai.md for verification on your Windows laptop.
