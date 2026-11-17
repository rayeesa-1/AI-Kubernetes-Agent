def inspect_network(services, pods, slices):
    errors = {name: r["error"] for name, r in (("services", services), ("pods", pods), ("endpointslices", slices)) if not r["ok"]}
    if errors:
        return {"ok": False, "errors": errors, "findings": [], "dns": "Not verified"}
    findings = []
    for service in services["data"].get("items", []):
        meta, spec = service["metadata"], service.get("spec", {})
        if spec.get("type") == "ExternalName" or not spec.get("selector"):
            continue  # These services do not require selector-managed pod endpoints.
        selector = spec["selector"]
        matches = [p for p in pods["data"].get("items", []) if p["metadata"]["namespace"] == meta["namespace"]
                   and all(p["metadata"].get("labels", {}).get(k) == v for k, v in selector.items())]
        endpoints = [ep for sl in slices["data"].get("items", [])
                     if sl["metadata"]["namespace"] == meta["namespace"]
                     and sl["metadata"].get("labels", {}).get("kubernetes.io/service-name") == meta["name"]
                     for ep in sl.get("endpoints", [])]
        reasons = []
        if not matches:
            reasons.append("NoPodsMatchSelector")
        if not any(ep.get("conditions", {}).get("ready") is not False for ep in endpoints):
            reasons.append("NoReadyEndpoints")
        if reasons:
            findings.append({"service": meta["name"], "namespace": meta["namespace"], "observations": reasons})
    dns_pods = [p for p in pods["data"].get("items", []) if p["metadata"].get("namespace") == "kube-system"
                and p["metadata"].get("labels", {}).get("k8s-app") == "kube-dns"]
    return {"ok": True, "findings": findings, "services_checked": len(services["data"].get("items", [])),
            "dns": {"status": "Not verified; no active DNS query performed", "dns_pods_found": len(dns_pods)},
            "note": "Service absence requires an expected-service inventory; no such inventory is configured."}
