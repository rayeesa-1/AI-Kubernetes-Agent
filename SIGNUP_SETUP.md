# InsForge signup update

This update adds self-service registration to your existing phase-4 application.
It preserves the current login/session, dashboard, investigation, AI, history, and realtime code.

## Install on Windows

1. Back up your existing project folder.
2. Extract this ZIP into a separate temporary folder.
3. Copy the extracted `backend` and `frontend` folders into:
   `C:\Users\rzsharif\Documents\my\ai-kubernetes-agent`
4. Choose **Replace the files in the destination** when Windows asks. Merge the folders;
   do not delete your existing backend or frontend folders. The ZIP contains only six
   new/changed files, listed below.
5. Keep your existing `.env`, Dockerfiles, Compose configuration, SQL migration,
   kubeconfig, and dependencies. None are included or replaced by this update.
6. In a terminal opened in the project folder, run:

```cmd
docker compose up -d --build
```

7. Open http://localhost:3000 and hard-refresh with Ctrl+F5.
   Sign out first if you already have a session. You will see **Don't have an account? Sign up**.

## InsForge configuration

Continue using your existing backend environment variables:

```env
INSFORGE_URL=your-project-api-url
INSFORGE_API_KEY=your-existing-server-only-project-key
SESSION_COOKIE_SECURE=false
```

- Public signup must be enabled in the intended InsForge project's authentication settings
  (`disableSignup=false`). This update respects the project's setting; it does not change it.
- Leave email verification enabled if that is how you configured your project. The app reads
  the current verification method and password requirements from InsForge at runtime.
- For **code verification**, the app asks for the six-digit email code and establishes
  a session after successful verification.
- For **link verification**, add the exact local return URL `http://localhost:3000/` to
  the project's allowed redirect URLs. The email link must verify through InsForge first,
  then return to the app. The user signs in afterward; URL parameters alone cannot sign in.
- An email is sent by InsForge, not by FastAPI. If email delivery fails, check InsForge's
  authentication/email configuration and delivery limits, and check your spam folder.
- The UI has **Verify an existing account** and **Resend verification email** for recovery.
- No additional SQL migration, SDK package, or frontend InsForge project/admin key is needed.

## What users can do

An app user can create an account, verify email when required, and access the existing dashboard.
As in your current app, every authenticated user can investigate the configured cluster;
this update does not add per-user cluster permissions. History remains scoped to each user.
Suggested kubectl fixes remain suggestions; registration never executes cluster commands.

## Changed files

- `backend/app/api/auth.py`: adds GET `/auth/config`, POST `/auth/signup`,
  POST `/auth/verify-email`, and POST `/auth/resend-verification`.
- `backend/app/services/insforge.py`: safe fixed messages for rejected auth requests and rate limits.
- `frontend/src/app/page.tsx`: signup form, confirm password, verification/recovery UI,
  link return handling, and password requirements from the project.
- `frontend/src/hooks/use-auth.ts`: registration, verification, and resend actions.
- `frontend/src/services/api.ts`: excludes public auth actions from automatic session-refresh retries.
- `backend/tests/test_signup.py`: 17 new signup/verification regression tests.

Registration and verification use InsForge's public auth endpoints without an administrator key.
The backend does not forward client-supplied roles, auto-confirm flags, or redirect destinations.
Refresh tokens stay in the existing HttpOnly cookie; access tokens stay in browser memory.
Passwords are not persisted or logged by this application.

## Verification

1. Open the login page while signed out and select **Sign up**.
2. Submit mismatched passwords: the app must reject them without creating an account.
3. Register with an unused email address and a password matching the displayed requirements.
4. Complete the project's configured verification flow if required.
5. Confirm the user appears under Authentication in the intended InsForge project.
6. Confirm login, page refresh, logout, and a normal investigation still work.
7. If signup is disabled in InsForge, the form must display that registration is disabled.

Automated checks completed: all 64 backend tests passed (47 existing plus 17 new),
and the Next.js production build including TypeScript checks passed.
Provider responses were simulated; no live user or email was created during testing.
Browser automation could not run because the test browser download was unavailable.
Actual InsForge project configuration and email delivery must be verified on your laptop.

Run backend tests locally from `backend` after installing `requirements.txt`:

```cmd
python -m unittest discover -s tests -v
```

Run the frontend production check from `frontend` after `npm ci`:

```cmd
npm run build
```

If signup fails, inspect the response to `/auth/signup` and the backend logs. Do not share
passwords, tokens, your populated `.env`, or kubeconfig files.

## Rollback

Restore the five modified source files from your backup, remove the added signup test,
and rebuild both services. No database changes need to be reversed.
