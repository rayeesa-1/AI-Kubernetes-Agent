# Phase 3: AI reasoning via OpenRouter

The existing POST /investigate endpoint now collects evidence and optionally adds a
validated diagnosis. The original investigation, errors, timestamp, and collection
status remain intact. No frontend edits were made for phase three; use the API or FastAPI /docs
to inspect the diagnosis. Existing frontend behavior is preserved. There is no authentication,
history, realtime behavior, deployment, InsForge SDK, or automated remediation.

## Private configuration

Copy `.env.example` to `.env` in the project root. Populate these locally:

```dotenv
OPENROUTER_API_KEY=<your actual OpenRouter key supplied through InsForge>
OPENROUTER_MODEL=<an available model supporting JSON object output>
```

Do not paste a real key into chat. An InsForge application/anonymous/project key is
not necessarily an OpenRouter API key. This implementation calls OpenRouter directly
using the supplied OpenRouter credential, as requested. If InsForge only provides a
proxy endpoint rather than a usable OpenRouter key, obtain that endpoint's documented
authentication contract before changing this client; no undocumented proxy is assumed.

Compose reads secrets from the root .env. Native Python uses backend/.env instead.
The key stays server-side and is never passed to Next.js. Keep .env and runtime/
private. OpenRouter requests may incur provider charges.

## Windows: start and verify

From the project root in PowerShell:

```powershell
Copy-Item .env.example .env
```

Skip that copy if you already have a populated root `.env`; edit it instead.
Set the two OpenRouter values in your editor. Do not type the key into chat or commit it.
Keep the existing cluster; do not create a second one. Replace `ai-agent` with the
actual cluster name from `kind get clusters`.

```powershell
.\scripts\Connect-Kind.ps1 -ClusterName ai-agent
```

Run the `$env:KUBECTL_VERSION=...` command printed by that script, then:

```powershell
docker compose -f docker-compose.yml -f docker-compose.kind.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.kind.yml exec backend kubectl --kubeconfig /app/kube/config get pods -A
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/investigate" | ConvertTo-Json -Depth 30
```

Compose automatically reads the project-root `.env`. Always include both Compose files
for this kind setup. If your organization restricts PowerShell scripts, follow its
policy; the read-only setup commands are in `scripts/Connect-Kind.ps1` for review.
The setup token is temporary: rerun the script when it expires.

Alternatively open http://localhost:8000/docs, expand POST /investigate, choose
Try it out, then Execute. The existing frontend has not been changed.

Expected output retains `investigation` and adds `diagnosis` plus `ai` metadata.
Without a configured key/model, `diagnosis` is null and `ai.status` is
`not_configured`; collection still works. With a valid configured key/model and
successful AI call, `ai.status` is `success` and `diagnosis` contains the result.
No live model call was performed while producing this update.

## Response contract

Top-level `status` remains the evidence collection status (success/partial/error).
`diagnosis` is the validated object, or null if AI was skipped, unconfigured, or failed.
`ai.status` is success/not_configured/skipped/error and `ai.error` explains failures.
`ai.commands_executed` is false for successful diagnoses. Suggestions are never run.
A successful diagnosis includes:
- root_cause, explanation, fix
- kubectl_commands (list) and kubectl_command (first command, compatibility field)
- prevention_recommendation
- confidence (integer 0..100), confidence_reasoning
- evidence_references (JSON pointers into the investigation object), missing_evidence

If the cluster appears healthy, the model is instructed to report no demonstrated
failure rather than invent an incident. Sparse evidence should produce uncertainty
and next checks rather than an unsupported fix. Multiple incidents can be discussed
in explanation, while this beginner version returns one primary diagnosis.

## Boundaries and errors

A stable system prompt and temperature=0 reduce variability but do not guarantee
identical or correct diagnoses. Pydantic strictly validates JSON and confidence
ranges, rejects extra fields and malformed responses, checks evidence references
exist in the bounded evidence sent, and rejects shell chaining in commands. These
checks do not prove the diagnosis or suggested command is correct. Review every
recommendation manually. No generated command is sent to the kubectl executor.

Confidence is an uncalibrated model estimate: capped at 60 for incomplete collection,
75 for acknowledged missing evidence, and 20 without valid evidence references.
References validate existence, not semantic support for a claim.

All five sections are included in the prompt with explicit limits (12 list entries,
2,000 characters/string, 12,000 characters/section). Oversized sections are marked
omitted; raw evidence remains in the HTTP response. Common credential patterns and
the exact configured key are redacted before transmission. Redaction is best-effort,
not a guarantee that arbitrary application logs are secret-free. Only use cluster
logs you are authorized to share with the configured LLM provider. Kubernetes logs
and events are treated as untrusted data, not instructions; LLM prompt injection
cannot be ruled out, which is another reason suggestions require human review.

HTTPX handles timeouts and up to two retries (three attempts), with bounded
exponential backoff, for transport errors, 408, 429, and selected 5xx statuses.
401/402/403 and incompatible model requests return sanitized errors without retries.
Malformed, truncated, invalid-schema, or unsupported-command responses fail cleanly.
No upstream body, credential, prompt, or log evidence is logged by the AI layer.
Timeout is per HTTPX I/O operation, not a guaranteed end-to-end wall-clock deadline.

## Verification

From backend/: `python -m unittest discover -s tests -v`.
Tests use HTTPX mock transports and mocked kubectl responses; they never spend LLM
credits or change a cluster. Live OpenRouter credentials and Docker are not available
in the authoring environment; confirm connectivity and a live diagnosis on your machine.

Official API documentation:
https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request
https://openrouter.ai/docs/api-reference/parameters
