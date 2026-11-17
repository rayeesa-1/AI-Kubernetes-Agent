# Architecture

Browser → POST /investigate → FastAPI sync route → investigation service → kubectl subprocesses → Kubernetes API.
The browser renders collected evidence. No AI reasoning or root-cause inference runs.

Collectors inspect pods (including init containers and previous OOM termination), bounded logs, Warning events, deployment conditions and Service EndpointSlices. Failures remain explicit in each section. A shared investigation budget bounds command execution, and a per-process lock rejects overlapping requests with HTTP 409.

The backend container joins the kind network through an optional Compose override. It receives a read-only kubeconfig using a short-lived service account token and the cluster CA. The setup script creates the RBAC; the application does not mutate Kubernetes resources.

GET /health remains unchanged. The frontend uses React Query mutations for on-demand requests. Authentication, LLM access, fixes, and realtime updates remain unimplemented.
