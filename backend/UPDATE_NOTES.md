# AI response validation update

## Install on Windows

1. Back up your existing backend folder.
2. Extract this archive's contents INTO your project's backend folder. The archive contains app/, tests/, Dockerfile, and requirements.txt directly; avoid creating backend/backend.
3. Keep your root .env, docker-compose.yml, and kind-backend.kubeconfig as they are. No keys or cluster credentials are included here.
4. From the project root run:

```powershell
docker compose up -d --build --no-deps backend
```

5. Execute POST /investigate from http://localhost:8000/docs.

## Changes

- Clarifies required diagnosis field names, list types, integer confidence, and evidence reference paths.
- Includes a complete formatting example and instructions for healthy or inconclusive collected evidence.
- Accepts a single JSON Markdown fence while still strictly validating the underlying JSON.
- Allows one correction completion when schema, evidence references, or suggested commands are invalid. Existing HTTP transport retries remain bounded separately. The correction can consume one additional model completion and free-tier quota.
- Returns and logs a safe validation_detail if correction also fails. It identifies the failed rule without logging raw model answers, credentials, or evidence contents.
- Preserves investigation evidence and the existing response shape. No commands are executed by the AI layer.

## Verification

34 automated tests passed, including existing API and investigation tests and five new regression tests. Provider requests and Kubernetes commands are mocked. No live request was made with your API key, and your Windows cluster was not accessed here.

The original warning did not expose the exact model output or failed rule. These changes improve response handling and make remaining failures diagnosable; they cannot guarantee that every free model returns a valid answer.

If diagnosis remains null, share ai.validation_detail or the corresponding backend warning, without sharing keys or raw sensitive logs.
