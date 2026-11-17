"""Deterministic collection summary; a successful read does not prove full health."""
def summarize(payload):
    evidence = payload.get('investigation', {})
    sections = ('pods', 'logs', 'events', 'deployments', 'network')
    failed = [key for key in sections if not evidence.get(key, {}).get('ok')]
    findings = bool(evidence.get('pods', {}).get('problematic_pods')
                    or evidence.get('deployments', {}).get('problematic_deployments')
                    or evidence.get('events', {}).get('findings')
                    or evidence.get('network', {}).get('findings'))
    if failed:
        return {'state': 'incomplete', 'message': 'Some checks could not finish. Cluster health is not established.', 'failed_checks': failed}
    if findings:
        return {'state': 'findings', 'message': 'Kubernetes findings collected. Review the evidence and diagnosis.', 'failed_checks': []}
    return {'state': 'no_findings', 'message': 'No critical Kubernetes issues detected by these checks. Active DNS and application connectivity were not tested.', 'failed_checks': []}
