def inspect_deployments(result):
    if not result["ok"]:
        return result
    findings = []
    for deployment in result["data"].get("items", []):
        meta, status = deployment["metadata"], deployment.get("status", {})
        desired = deployment.get("spec", {}).get("replicas", 1)
        conditions = [{k: c.get(k) for k in ("type", "status", "reason", "message")} for c in status.get("conditions", [])]
        unhealthy = (status.get("availableReplicas", 0) < desired or status.get("updatedReplicas", 0) < desired
                     or status.get("observedGeneration", 0) < meta.get("generation", 1)
                     or any((c["type"] == "Progressing" and c["status"] == "False")
                            or (c["type"] == "ReplicaFailure" and c["status"] == "True") for c in conditions))
        if unhealthy:
            findings.append({"name": meta["name"], "namespace": meta["namespace"], "desired": desired,
                             "available": status.get("availableReplicas", 0),
                             "unavailable": status.get("unavailableReplicas", 0),
                             "updated": status.get("updatedReplicas", 0), "conditions": conditions})
    return {"ok": True, "healthy": not findings, "problematic_deployments": findings}
