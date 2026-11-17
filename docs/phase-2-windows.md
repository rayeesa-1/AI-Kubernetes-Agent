# Phase 2: Windows + Docker Desktop + kind

This extends the original app. No OpenRouter or InsForge API key is required.
The app gathers evidence only; it neither diagnoses root causes nor modifies workloads.
Use only on clusters you are authorized to inspect. Logs may contain sensitive data.
Keep the unauthenticated app bound to localhost, as provided in Compose.

## 1. Prerequisites

Docker Desktop must run Linux containers. PowerShell must have kind and kubectl on PATH.
A kind cluster must already exist. Free adequate disk space for image builds first.
Run all commands from the project root, not Windows/system32.

```powershell
kind get clusters
kubectl get nodes
```

## 2. Connect the backend to your cluster

Replace `ai-agent` below with the EXACT name printed by `kind get clusters`.
This explicitly uses context `kind-ai-agent`, so another active context is not changed.

```powershell
.\scripts\Connect-Kind.ps1 -ClusterName ai-agent
```

The script creates an `ai-investigator` namespace, a service account and read-only
cluster role/binding. It requests an 8-hour token and writes `.kube/kind-config.json`.
The cluster determines the actual token expiry. Rerun the script to renew it.
The file includes a credential: never share or commit it. It is ignored by Git.
Admin credentials are used only in memory for setup, not passed to the application.
No permission to list Secrets, modify resources or execute in pods is granted.

If PowerShell blocks script execution, review the script first and follow your
organization's policy. You can run its reviewed commands individually; do not change
machine execution policy just for this project.

The script prints a command such as `$env:KUBECTL_VERSION='v1.35.0'`.
Run that printed command in the same PowerShell window. This selects kubectl to match
the server; the Dockerfile's default is v1.35.0 if the variable is not set.

## 3. Build and verify from inside the backend

```powershell
docker compose -f docker-compose.yml -f docker-compose.kind.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.kind.yml exec backend kubectl --kubeconfig /app/kube/config get pods -A
docker compose -f docker-compose.yml -f docker-compose.kind.yml exec backend kubectl --kubeconfig /app/kube/config auth can-i delete pods --all-namespaces
```

The first kubectl command should list pods. The permission test should print `no`
(and can return a nonzero exit code, which is expected for this check).
Always include both Compose files for this kind configuration.

Why the extra Compose file? The backend joins the external `kind` Docker network.
Its kubeconfig uses kind's INTERNAL control-plane hostname and port, with the
original CA and TLS verification. A Windows localhost kubeconfig does not generally
work inside another container. No insecure TLS flags, host-wide API exposure,
Docker socket mounts, or copied source repositories are needed.
This assumes kind uses its default Docker network named `kind`.

## 4. Run an investigation

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/investigate' | ConvertTo-Json -Depth 30
```

Or open http://localhost:3000 and click **Investigate Cluster**.
http://localhost:8000/docs also exposes the new endpoint.
A healthy cluster can correctly return empty findings.

`status` means collection status, not cluster health:
- `success`: all collectors completed.
- `partial`: some collectors failed; examine each section's error.
- `error`: no collector completed successfully.

Pod `healthy` reflects the observed pod states; historical OOM kills and Warning
events may describe resolved issues. Transient Pending/NotReady pods are observations,
not a root-cause diagnosis. ContainerCreating is flagged only after 300 seconds
(configurable via STUCK_POD_SECONDS; age uses pod creation time as an approximation).
Logs include init containers, multiple containers and previous instances where available.
Log attempts are capped at 12; each reads at most 80 lines / 12,000 bytes.
An image-pull failure may have no logs: inspect pod states and events instead.
DNS is explicitly marked unverified; no exec/probe workloads are created.
Service checks use EndpointSlices and skip selectorless / ExternalName services.

## Troubleshooting

- `Unauthorized`: renew the token by rerunning the setup script.
- `Forbidden`: reapply the supplied RBAC using your cluster admin context.
- Missing kubeconfig: run setup before starting with the kind Compose override.
- Connection refused / hostname failure: check Docker Desktop, `kind get clusters`,
  and that both Compose files are used. Rerun setup if the cluster was recreated.
- `kubectl` missing in backend: rebuild the backend image.
- API 409: wait for the active investigation to finish. The lock is per process;
  run the supplied single-worker configuration for this local development phase.

## Tests

From `backend`, install requirements and run:

```powershell
python -m unittest discover -s tests -v
```

Tests use fake kubectl responses; they do not require a cluster or API key.
Live Docker/kind verification must be run on your Windows machine.
