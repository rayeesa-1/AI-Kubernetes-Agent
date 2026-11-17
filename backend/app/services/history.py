from datetime import datetime, timezone
from fastapi import HTTPException
from loguru import logger
from app.services.insforge import InsForge

STAGES = ['pods', 'logs', 'events', 'deployments', 'network', 'ai']

class InvestigationHistory:
    def __init__(self, user_id, run_id, service=None, cluster=None):
        self.user_id, self.run_id = user_id, str(run_id)
        self.service = service or InsForge()
        self.progress = {stage: 'pending' for stage in STAGES}
        self.warning = False
        self.revision = 0
        self.cluster = cluster or {}

    def start(self):
        self.service.records('POST', self.user_id, values={
            'id': self.run_id, 'status': 'running', 'namespace': 'All namespaces',
            'progress': self.progress, 'revision': 0,
            'cluster_context': self.cluster.get('context'), 'cluster_name': self.cluster.get('cluster')})

    def update(self, stage, state):
        self.progress[stage] = state
        self.revision += 1
        try:
            self.service.records('PATCH', self.user_id, run_id=self.run_id,
                                 values={'progress': dict(self.progress), 'revision': self.revision})
        except HTTPException:
            self.warning = True
            logger.warning('Investigation progress persistence unavailable')

    def finish(self, result=None, failed=False):
        if failed:
            self.progress = {stage: ('error' if state == 'running' else state)
                             for stage, state in self.progress.items()}
        diagnosis = (result or {}).get('diagnosis')
        ai = (result or {}).get('ai', {})
        status = 'error' if failed else ('completed' if (result or {}).get('status') == 'success'
                    and ai.get('status') == 'success' else 'partial')
        self.revision += 1
        values = {'status': status, 'progress': dict(self.progress), 'revision': self.revision,
                  'completed_at': datetime.now(timezone.utc).isoformat(),
                  'root_cause': (diagnosis or {}).get('root_cause'),
                  'confidence': (diagnosis or {}).get('confidence'), 'diagnosis': diagnosis,
                  'summary': (result or {}).get('summary'),
                  'ai_error': 'Investigation failed; retry or check backend logs' if failed else ai.get('error')}
        try:
            self.service.records('PATCH', self.user_id, run_id=self.run_id, values=values)
        except HTTPException:
            self.warning = True
            logger.warning('Investigation final history write unavailable')
        return status
