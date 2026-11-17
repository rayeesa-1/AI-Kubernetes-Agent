from datetime import datetime, timezone
from app.core.config import get_settings
from app.kubernetes.executor import KubectlExecutor
from app.kubernetes.pods import inspect_pods
from app.kubernetes.logs import collect_logs
from app.kubernetes.events import analyze_events
from app.kubernetes.deployments import inspect_deployments
from app.kubernetes.network import inspect_network


def investigate_cluster(executor=None, progress=None):
    emit = progress or (lambda stage, state: None)
    settings = get_settings()
    executor = executor or KubectlExecutor(settings)
    emit('pods', 'running')
    raw_pods = executor.get("pods")
    pods = inspect_pods(raw_pods, settings.stuck_pod_seconds)
    emit('pods', 'completed' if pods['ok'] else 'error')
    emit('logs', 'running')
    logs = collect_logs(executor, pods, raw_pods, settings.max_log_requests)
    emit('logs', 'completed' if logs['ok'] else 'error')
    emit('events', 'running')
    events = analyze_events(executor.get("events"))
    emit('events', 'completed' if events['ok'] else 'error')
    emit('deployments', 'running')
    deployments = inspect_deployments(executor.get("deployments"))
    emit('deployments', 'completed' if deployments['ok'] else 'error')
    emit('network', 'running')
    network = inspect_network(executor.get("services"), raw_pods, executor.get("endpointslices"))
    emit('network', 'completed' if network['ok'] else 'error')
    evidence = {"pods": pods, "logs": logs, "events": events, "deployments": deployments, "network": network}
    successful = sum(section["ok"] for section in evidence.values())
    return {"status": "success" if successful == 5 else "partial" if successful else "error",
            "collected_at": datetime.now(timezone.utc).isoformat(), "investigation": evidence}
