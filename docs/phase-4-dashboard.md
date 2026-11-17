# Phase 4: login, dashboard, progress, and history

## What changed

The Next.js homepage is now a login screen and protected dashboard. FastAPI remains
the orchestrator: the existing inspectors and AI analyzer are preserved. The collector
has an optional progress callback; it does not change the evidence payload.

InsForge provides authentication, PostgreSQL history, and Socket.IO realtime only.
OpenRouter still handles AI using your existing server-side key and model.

A finished check means collection completed, not necessarily that the resource is healthy.
No repair commands are executed. Confidence remains an uncalibrated model estimate.

## Before starting

Keep your working local project as a backup. Merge the supplied files into that project;
do NOT delete or overwrite your local `.env` or `kind-backend.kubeconfig`.
The ZIP intentionally does not contain those files. Docker Desktop and your kind cluster
must remain running, using the existing read-only kubeconfig mount and kind network.

You need an InsForge project with Auth, Database, Realtime, a SQL editor, and a server-only
project API key. The model gateway is not used. Availability depends on your project/plan.
This environment cannot provision or test your live InsForge account.

## 1. Configure InsForge

Use a dedicated InsForge project for this local demo. In its SQL editor, review and run
`deploy/insforge-phase4.sql`. This creates the history table, ownership policies,
realtime channel pattern, and progress trigger. All statements run in a transaction.
If your hosted project's SQL editor refuses operations on realtime schema objects,
use its supported admin/CLI flow with the same policies; do not replace them with
public access. Review the SQL error and project version before proceeding.

Provision a verified email/password user using the project's Authentication dashboard
(or your organization's supported admin process). Disable public signups for this
cluster administration demo. This UI deliberately has login only, not self-registration.
Every admitted user can investigate the SAME configured cluster. History and realtime
updates are isolated by user, but Kubernetes access is not isolated by tenant.
Do not admit untrusted users or point this tutorial at a production cluster.

## 2. Configure your project-root .env

Append these lines next to the existing OpenRouter settings:

```env
INSFORGE_URL=https://YOUR-PROJECT.insforge.app
INSFORGE_API_KEY=YOUR-SERVER-ONLY-PROJECT-API-KEY
SESSION_COOKIE_SECURE=false
```

Use your project API URL, not the dashboard website URL. The project admin API key is
NOT an OpenRouter key, anonymous token, user password, or frontend/public key. Never
paste either key into chat or commit it. The frontend receives no admin key.
Leave `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and your kind settings unchanged.
For HTTPS hosting set SESSION_COOKIE_SECURE=true; local HTTP uses false.

## 3. Build and open the dashboard

In PowerShell, from your project folder:

```powershell
docker compose up -d --build
```

Open http://localhost:3000 (use localhost consistently, not 127.0.0.1).
Sign in with the provisioned InsForge user's email and password. Click
**Investigate Cluster**. Each stage updates when the backend actually runs it.
The dashboard displays diagnosis, AI/provider errors, evidence, and recent history.
Reload the page: the HttpOnly refresh cookie restores the login session.
Sign out: the refresh cookie is cleared and user-specific client caches are discarded.

Only the FastAPI URL is a public build-time frontend setting; InsForge URL is
returned to authenticated users by `/auth/me`, so no public InsForge key is needed.

## 4. API behavior

- `GET /health` stays public and its existing response is unchanged.
- `POST /auth/login` accepts `{ "email": "...", "password": "..." }`.
- `POST /auth/refresh` rotates the refresh cookie and returns an access token.
- `POST /auth/logout` clears the local session and attempts upstream revocation.
- `GET /auth/me` verifies the bearer token against InsForge.
- `POST /investigate` now requires a valid InsForge **user** bearer token.
- `GET /investigations` returns up to 20 of that user's latest runs.
- `GET /investigations/{uuid}` returns that user's run, or 404.

In FastAPI `/docs`, sign in through POST /auth/login, then enter the returned
access_token into **Authorize**. Do not use the OpenRouter or project admin key there.
The UI handles this automatically. Breaking change required by authentication:
unauthenticated investigation calls now receive HTTP 401.

The existing investigation/status/AI/diagnosis fields remain. Added fields are
investigation_id, run_status, and history_saved. run_status distinguishes completed,
partial (collection or AI failure), and error. The original status still describes
collection only, so an HTTP 200 is not a guarantee of AI success.

History stores timestamps, all-namespaces scope, root cause, confidence, diagnosis,
progress, and status; raw logs/evidence are not stored in InsForge. The current
collector remains cluster-wide; no namespace filter is implied.

## Recovery and limits

The browser subscribes to its private user channel before/during investigations and
recovers durable state on reconnect. Realtime events are ordered by a revision number;
old events cannot regress the displayed step state. Realtime sends progress only;
final diagnosis is fetched through authenticated FastAPI endpoints.

If realtime fails, a visible warning is shown, the POST still returns its real result,
and Refresh history recovers stored progress. There are no timed/fake checkmarks.
If the request times out, the backend may still be running: refresh history before
starting another run. No automatic POST retry occurs for network/timeouts.
If the backend restarts during a run, its record may remain running; the UI explicitly
shows that it may be interrupted. This tutorial does not add a job queue or resume jobs.
Keep one Uvicorn worker: the inherited concurrent-run lock is process-local.

If initial history creation fails, investigation does not start (503). Later persistence
failures do not discard evidence or diagnosis; history_saved=false warns the UI. A
stored terminal state can be stale when that final write failed.

Login uses FastAPI as a BFF for InsForge's documented `client_type=server` flow.
Access tokens are in browser memory only; refresh tokens use an HttpOnly, SameSite=Strict
cookie scoped to /auth. Cookie-mutating browser requests check Origin. API reads and
investigations validate bearer tokens against InsForge; no local JWT decoding is trusted.
The browser's Socket.IO handshake uses its short-lived user token, never an admin key.
CORS permits the configured UI origin, credentials, Authorization, and X-Investigation-ID.

## Validation performed for this delivery

- 47 backend tests passed against mocked InsForge and LLM responses.
- TypeScript checking and the Next.js production build passed.
- The Kubernetes inspector and AI implementation files are unchanged from the upload.
- Live InsForge SQL/RLS/realtime behavior needs the acceptance checks below.
- Automated browser execution could not run because this workspace blocks the browser's
  required local socket operations; no visual or browser-session check is claimed.

## Checks

```bash
cd backend
python -m unittest discover -s tests -v
cd ../frontend
npm ci
npm run typecheck
npm run build
```

Backend tests use simulated InsForge/provider responses and verify auth rejection,
owner-scoped queries, progress/error behavior, plus existing collector/AI regression tests.
They do not substitute for applying SQL and testing a real InsForge project.

Live acceptance checks (after configuring InsForge):

1. Logged-out POST /investigate and history reads return 401; health returns 200.
2. Sign in, start a check, verify actual stage transitions and diagnosis.
3. Reload, view the saved diagnosis, then sign out and back in.
4. Use two accounts: neither should read the other's run UUID (404), history, or channel.
5. Try an expired token: refresh or sign-in occurs; protected data stays hidden.
6. Disconnect the socket: warning appears, POST still completes, reconnect/history recovers.
7. Simulate AI failure: evidence remains and history shows partial, not successful diagnosis.

## References used for the adapter

- https://docs.insforge.dev/sdks/rest/auth
- https://docs.insforge.dev/sdks/rest/database
- https://docs.insforge.dev/sdks/rest/realtime
- https://insforge.dev/blog/insforge-realtime
