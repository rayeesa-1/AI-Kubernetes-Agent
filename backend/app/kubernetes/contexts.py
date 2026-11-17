"""Read context labels, never return kubeconfig credentials or change current-context."""
from fastapi import HTTPException
from app.core.config import get_settings
from app.kubernetes.executor import KubectlExecutor


def list_contexts():
    result = KubectlExecutor(get_settings()).run(['config', 'view', '-o', 'json'], as_json=True)
    if not result['ok']:
        raise HTTPException(503, result['error'])
    config = result['data']
    if not isinstance(config, dict):
        raise HTTPException(503, 'Unable to read kubeconfig contexts.')
    cluster_names = {entry.get('name') for entry in config.get('clusters', [])}
    rows = []
    for entry in config.get('contexts', []):
        name, context = entry.get('name'), entry.get('context', {})
        cluster = context.get('cluster')
        if not isinstance(name, str) or not name or cluster not in cluster_names:
            continue
        rows.append({'context': name, 'cluster': cluster,
                     'namespace': context.get('namespace', 'default'),
                     'current': name == config.get('current-context')})
    return rows


def resolve_context(name=None):
    contexts = list_contexts()
    if not contexts:
        raise HTTPException(503, 'No clusters found. Export your Windows kubeconfig and mount it into the backend.')
    if name is None:
        name = next((row['context'] for row in contexts if row['current']), None)
    selected = next((row for row in contexts if row['context'] == name), None)
    if not selected:
        raise HTTPException(400, 'Select a context listed in the mounted kubeconfig, then retry.')
    return selected
