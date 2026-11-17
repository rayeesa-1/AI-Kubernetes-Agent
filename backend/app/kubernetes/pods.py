from datetime import datetime, timezone


def age_seconds(timestamp):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds()
    except (ValueError, TypeError, AttributeError):
        return 0


def inspect_pods(result, stuck_seconds=300):
    if not result["ok"]:
        return result
    problematic = []
    for pod in result["data"].get("items", []):
        meta, status = pod["metadata"], pod.get("status", {})
        reasons = []
        phase = status.get("phase", "Unknown")
        if phase in {"Pending", "Failed", "Unknown"}:
            reasons.append(phase)
        containers = []
        for cs in status.get("initContainerStatuses", []) + status.get("containerStatuses", []):
            containers.append({"name": cs["name"], "ready": cs.get("ready", False),
                               "restart_count": cs.get("restartCount", 0)})
            state = cs.get("state", {})
            waiting = state.get("waiting", {}).get("reason")
            if waiting and (waiting != "ContainerCreating" or age_seconds(meta.get("creationTimestamp")) >= stuck_seconds):
                reasons.append(waiting)
            for key in ("state", "lastState"):
                terminated = cs.get(key, {}).get("terminated", {})
                if terminated.get("reason") == "OOMKilled" or (key == "state" and terminated.get("exitCode", 0) != 0):
                    reasons.append(terminated.get("reason", "Error"))
        if phase == "Running" and any(c.get("type") == "Ready" and c.get("status") == "False" for c in status.get("conditions", [])):
            reasons.append("NotReady")
        if reasons:
            problematic.append({"name": meta["name"], "namespace": meta["namespace"],
                                "status": list(dict.fromkeys(reasons)), "phase": phase,
                                "containers": containers})
    return {"ok": True, "healthy": not problematic, "total": len(result["data"].get("items", [])),
            "problematic_pods": problematic}
