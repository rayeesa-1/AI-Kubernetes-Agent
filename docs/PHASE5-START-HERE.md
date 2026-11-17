# Phase 5: cluster selection and integration testing

This update is for the Windows + Docker Desktop + kind project you uploaded.
It retains FastAPI as orchestrator and InsForge for authentication, history,
and realtime. It does not replace your OpenRouter settings, signup implementation,
secrets, kubeconfig, or Compose file.

## Apply this update

1. Back up your project folder. Extract this ZIP into `ai-kubernetes-agent`, merging
   its `backend`, `frontend`, `deploy`, `scripts`, and `docs` folders. Replace only
   matching files. Do not delete any existing folder or overwrite `.env`.
2. Open **your existing InsForge project > SQL Editor**. Run
   `deploy/insforge-phase5.sql`. It adds three columns and an index; it does not
   delete history or change the existing access policies. Phase 4's table and
   realtime trigger must already exist. No transaction wrapper is used.
3. Open **Windows PowerShell** in your project folder (these helper scripts are
   PowerShell scripts, not Command Prompt commands).
4. Export all Windows kubeconfig contexts:

   ```powershell
   .\scripts\Export-BackendKubeconfig.ps1
   ```

   Review local scripts before running them. If organization policy prevents
   running scripts, follow that policy; do not disable it. A fallback for one
   kind cluster is your previously used `kind export kubeconfig --internal`
   command, but that lists only that cluster in the app.

   The export reads the Windows kubeconfig (including `KUBECONFIG` when set),
   flattens file credentials, preserves the context list and default, and uses
   internal control-plane endpoints for running kind clusters. It does **not**
   change your Windows current context. A context is a named access profile:
   multiple profiles can point to one cluster and are intentionally listed separately.
5. Keep the existing backend Compose settings:

   ```yaml
       environment:
         KUBECONFIG_PATH: /kube/config
         KUBECONFIG: /kube/config
       volumes:
         - ./kind-backend.kubeconfig:/kube/config:ro
       networks:
         - default
         - kind
   ```

   Keep the existing top-level external `kind` network and all your InsForge,
   OpenRouter, CORS, and port settings. This snippet is not a replacement Compose file.
6. Rebuild and start:

   ```powershell
   docker compose up -d --build
   docker compose exec backend kubectl config get-contexts
   ```

7. Sign in at `http://localhost:3000`. Cluster/context cards appear above
   **Investigate Cluster**. Select one and investigate. Check that the context
   matches in the status panel, API result, and history table.

## What the cluster list can and cannot see

The backend lists **every usable context in its mounted kubeconfig**, not every
cluster automatically installed or running on Windows. Re-export and recreate the
backend after adding or removing contexts. A listed context is not proof of reachability.

Running kind clusters normally share Docker's `kind` network, used by this Compose
setup. For another local runtime, a `127.0.0.1` endpoint refers to the backend
container itself. Configure a reachable address **and matching TLS identity**;
do not disable certificate verification. Remote contexts can need VPN routes,
cloud credential plugins, or credentials configured inside the container.
`--flatten` embeds certificate files but does not install credential plugins.
Never upload or commit exported kubeconfigs; they contain credentials.

All authenticated users of this local, administrator-controlled app can select
any mounted context. History remains user-scoped. This is **not** a multi-tenant
cluster authorization system. Mount only clusters these users are permitted to
investigate, preferably using read-only Kubernetes credentials. Keep Compose's
loopback host bindings. Do not expose this development app to the internet.

## End-to-end verification

Use a dedicated kind lab. The helper refuses a non-kind context and an unrelated
namespace that happens to use the same name. No failures are installed automatically.
The scenario manifests have resource limits, disable service-account token mounts,
and use the namespace `ai-agent-lab`.

Start with **one scenario at a time**, for example:

```powershell
.\scripts\Test-Failure.ps1 -Context kind-ai-agent-cluster -Scenario crashloop -Action Apply
.\scripts\Test-Failure.ps1 -Context kind-ai-agent-cluster -Scenario crashloop -Action Check
```

Wait until the expected evidence appears. Image downloads and Kubernetes restart
backoff can take several minutes. Select `kind-ai-agent-cluster` on the dashboard
and click Investigate. Inspect both evidence and diagnosis. The application
only suggests changes; it does not execute AI-generated fixes.

| Scenario argument | Expected Kubernetes evidence | What the AI should explain |
| --- | --- | --- |
| `crashloop` | Error/restarts, eventually CrashLoopBackOff; startup log names missing DATABASE_URL | Required environment configuration is absent; configure it using an appropriate Secret/ConfigMap reference |
| `imagepull` | ErrImagePull/ImagePullBackOff and pull events for an intentionally nonexistent tag | Image retrieval failed; inspect the event to distinguish missing tag from network, registry, or authentication errors |
| `oom` | OOMKilled in current or previous termination state, restarts | Memory limit exceeded; review usage/leaks and size resources appropriately, rather than blindly increasing limits |
| `selector` | Healthy target pod, Service with NoPodsMatchSelector and NoReadyEndpoints | Service selector does not match the deployment's pod labels |

The selector case is most useful with no other test failure active. A failed image
pull caused by TLS/proxy problems is different from an invalid tag; the diagnosis
must follow the actual evidence. Historical warning events and previous OOM states
can remain after cleanup. Do not treat them as proof of an ongoing failure.

Clean up each scenario after testing:

```powershell
.\scripts\Test-Failure.ps1 -Context kind-ai-agent-cluster -Scenario crashloop -Action Cleanup
```

Substitute `imagepull`, `oom`, or `selector` in all three commands for the other cases.
After all tests, optionally delete the **dedicated** lab namespace:

```powershell
kubectl --context kind-ai-agent-cluster delete namespace ai-agent-lab
```

Do not delete other namespaces. A new empty namespace does not erase historical
observations elsewhere in the cluster.

## Acceptance checklist

- [ ] Signed-out requests to `/clusters`, `/investigate`, and history are rejected.
- [ ] Every exported context is listed, including alternate contexts for one cluster.
- [ ] Selecting A sends `{ "context": "A" }` to POST `/investigate`.
- [ ] A run on A does not alter the Windows current context or read cluster B.
- [ ] Actual stage completion updates reach the browser; history and diagnosis retain A.
- [ ] Each real failure above appears in evidence, with supported recommendations.
- [ ] Missing mount, unreachable cluster, and forbidden reads show clear errors.
- [ ] Provider timeout/credits errors preserve collected evidence and a partial history record.
- [ ] Refresh/sign-out/sign-in preserves history; another user cannot read it.
- [ ] Timeouts advise recovery from history rather than implying server cancellation.
- [ ] A no-findings result says no issues were observed by these checks, not that all networking works.

The API still accepts an empty investigation body for older clients: it resolves
and pins the mounted kubeconfig's current context at request start. New clients
send the selected context explicitly. Unknown contexts return 400 before cluster
access or history creation. Clients cannot supply raw kubectl flags or commands.

## Validation performed here

74 backend tests pass, including existing auth, signup, AI validation, read-only
collection, user-isolated history, plus new context isolation and partial-failure
cases. InsForge, LLM and subprocess boundaries are simulated. Frontend TypeScript
and production compilation are checked separately. Test results are in
`docs/PHASE5-VALIDATION.txt`.

There is no Docker daemon, kubectl executable, or access to your laptop/InsForge
credentials in this workspace. Real failure manifests, browser-to-cloud realtime,
SQL application, signup delivery and live AI quality must be verified on your
machine using the checklist above. This update is not a claim of production deployment.

## Useful diagnostics (no secrets)

```powershell
docker compose ps
docker compose exec backend kubectl config get-contexts
docker compose logs --tail 80 backend
```

Do not paste `.env`, kubeconfig content, browser request bodies, or tokens into chat.
