def analyze_events(result):
    if not result["ok"]:
        return result
    findings = []
    reasons = {"FailedScheduling", "BackOff", "FailedMount", "FailedPull", "ErrImagePull", "Unhealthy", "Failed"}
    for event in result["data"].get("items", []):
        if event.get("type") == "Warning" or event.get("reason") in reasons:
            findings.append({"namespace": event["metadata"].get("namespace"),
                             "reason": event.get("reason"), "message": event.get("message", "")[:2000],
                             "object": event.get("involvedObject", {}).get("name"),
                             "count": event.get("count", 1),
                             "last_seen": event.get("lastTimestamp") or event.get("eventTime") or event["metadata"].get("creationTimestamp")})
    findings.sort(key=lambda e: e["last_seen"] or "", reverse=True)
    return {"ok": True, "findings": findings[:100], "truncated": len(findings) > 100,
            "note": "Events are historical evidence and may describe resolved problems."}
