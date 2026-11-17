import re


def collect_logs(executor, pod_result, raw_pods, max_requests=12):
    if not pod_result["ok"]:
        return {"ok": False, "error": "Pod inspection unavailable"}
    targets = {(p["namespace"], p["name"]) for p in pod_result["problematic_pods"]}
    entries, requested = [], 0
    truncated = False
    for pod in raw_pods.get("data", {}).get("items", []):
        meta = pod["metadata"]
        if (meta["namespace"], meta["name"]) not in targets:
            continue
        status = pod.get("status", {})
        for cs in status.get("initContainerStatuses", []) + status.get("containerStatuses", []):
            modes = [False, True] if cs.get("restartCount", 0) else [False]
            for previous in modes:
                if requested >= max_requests:
                    truncated = True
                    continue
                requested += 1
                response = executor.logs(meta["namespace"], meta["name"], cs["name"], previous)
                entry = {"pod": meta["name"], "namespace": meta["namespace"], "container": cs["name"],
                         "previous": previous, **response}
                if response["ok"]:
                    # Preserve a bounded tail, with keyword matches as observations only.
                    entry["matching_lines"] = [line for line in response["data"].splitlines()
                        if re.search(r"exception|error|failed|connection|environment|startup", line, re.I)][:20]
                entries.append(entry)
    return {"ok": all(e["ok"] for e in entries), "entries": entries, "truncated": truncated,
            "note": "Bounded log tails may contain sensitive application data. No root cause inference."}
