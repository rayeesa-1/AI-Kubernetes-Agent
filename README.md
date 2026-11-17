# AI Kubernetes Agent

Phase 4 adds a login-protected dashboard, actual investigation progress through InsForge
Realtime, per-user investigation history, and diagnosis display.

**Start here: [Phase 4 setup](docs/phase-4-dashboard.md).** InsForge requires one-time
project/database/user setup before the new dashboard can investigate. Preserve your
existing local `.env` and `kind-backend.kubeconfig`; they are excluded from this ZIP.

# Phase 3 update

Start with **docs/phase-3-ai.md** for Windows setup and testing. See **docs/phase-3-validation.md** for completed checks and remaining live verification.

The AI reasoning layer is now included. Read **[docs/phase-3-ai.md](docs/phase-3-ai.md)** after the phase-two connectivity setup. Configure credentials privately to enable diagnosis; the endpoint continues returning evidence without a key. Suggested commands are never executed.

## Earlier project documentation

On-demand Kubernetes evidence collection with a Next.js frontend and FastAPI backend. Health checks work without a cluster; investigations require a configured cluster. AI reasoning remains a placeholder. No cloud account or model API key is required.

## Requirements

Choose either Docker with Compose v2, or Python 3.12+ and Node.js 24 LTS with npm. A remote development environment can be used if your laptop lacks disk space. Creating these files does not install anything on your laptop.

## Run with Docker

From the project root, with Docker running:

```sh
docker compose up --build
```

Open http://localhost:3000 and http://localhost:8000/health. API documentation is at http://localhost:8000/docs.

Stop with Ctrl+C, then `docker compose down`.

The defaults work without creating .env files. For Compose overrides, create a root `.env` with variables referenced in docker-compose.yml. `backend/.env` is used for direct Python runs, not automatically imported by Compose. Model keys can remain empty. The base Compose file does not mount kubeconfig; use the kind override described below for investigations.

## Run directly on Windows (without Docker)

Open PowerShell in the project root. Start the backend:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second PowerShell window at the project root:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

If PowerShell blocks npm.ps1, use `npm.cmd` for these commands. Virtual environment activation is unnecessary.

## Run directly on Linux or a remote workspace

Backend terminal, from the project root:

```sh
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend terminal, from the project root:

```sh
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

For remote workspaces, forward ports 3000 and 8000. Set frontend NEXT_PUBLIC_API_BASE_URL to the browser-accessible backend URL and backend CORS_ORIGINS to a JSON array containing the browser-accessible frontend origin. Restart the backend and dev frontend after edits. For Docker production builds, change NEXT_PUBLIC_API_BASE_URL in the root .env and rebuild the frontend: Next.js embeds public variables at build time. Keep secrets out of NEXT_PUBLIC_ variables.

## Verify

Visit `/health` or run:

```sh
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"healthy","service":"ai-kubernetes-agent"}
```

The homepage reports Ready only when the backend health request succeeds. An unavailable backend shows an error and retry button. Investigate Cluster requests evidence from POST /investigate and displays the structured result.

Frontend checks: `npm run typecheck` and `npm run build` from frontend/.

## Layout

- backend/app/: api, core, kubernetes, ai, services, models
- frontend/src/: app, components, services, hooks, types
- docs/: architecture notes
- prompts/: phase instructions

This is a modular starting point, not a production deployment. Application authentication belongs to a later phase. Read-only cluster permissions are supplied in deploy/investigator-rbac.yaml.


## Phase 2: Kubernetes evidence collection

Implemented: `POST /investigate`, bounded logs, pod/event/deployment/Service
inspection, structured partial errors, and a frontend evidence display. No AI or
InsForge integration is enabled.

**Windows + kind:** follow [the phase-two guide](docs/phase-2-windows.md) before
running an investigation. The base Compose file still supports phase-one startup;
cluster access uses the additional `docker-compose.kind.yml` file.
