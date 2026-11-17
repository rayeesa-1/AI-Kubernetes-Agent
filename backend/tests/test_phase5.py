"""Integration contracts with mocked InsForge, Kubernetes and LLM boundaries."""
import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from app.main import app
from app.api.auth import require_user
from app.services.insforge import get_insforge
from app.core.config import Settings
from app.kubernetes.contexts import list_contexts, resolve_context
from app.kubernetes.executor import KubectlExecutor
from app.services.summary import summarize

CONFIG = {'current-context': 'dev', 'clusters': [{'name': 'dev-cluster'}, {'name': 'test-cluster'}],
          'contexts': [{'name': name, 'context': {'cluster': cluster, 'user': 'hidden'}}
                       for name, cluster in [('dev', 'dev-cluster'), ('test', 'test-cluster')]],
          'users': [{'name': 'hidden', 'user': {'token': 'never-return-this'}}]}
SELECTED = {'context': 'test', 'cluster': 'test-cluster', 'namespace': 'default', 'current': False}
USER = {'id': '11111111-1111-4111-8111-111111111111'}

class ContextTests(unittest.TestCase):
    def test_inventory_does_not_return_credentials(self):
        with patch.object(KubectlExecutor, 'run', return_value={'ok': True, 'data': CONFIG}):
            rows = list_contexts()
            self.assertEqual([r['context'] for r in rows], ['dev', 'test'])
            self.assertNotIn('never-return-this', json.dumps(rows))
            self.assertNotIn('user', rows[0])
            self.assertEqual(resolve_context()['context'], 'dev')
            with self.assertRaises(Exception) as error: resolve_context('--server=evil')
            self.assertEqual(error.exception.status_code, 400)
    def test_context_is_explicit_and_does_not_mutate_kubeconfig(self):
        def run(context):
            executor = KubectlExecutor(Settings(_env_file=None), context=context)
            executor.get('pods')
            executor.logs('ns', 'pod', 'app')
        with patch('app.kubernetes.executor.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '{"items":[]}', '')) as sub:
            with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(run, ['dev', 'test']))
            commands = [call.args[0] for call in sub.call_args_list]
            self.assertEqual(len(commands), 4)
            self.assertEqual({cmd[cmd.index('--context')+1] for cmd in commands}, {'dev', 'test'})
            self.assertTrue(all('use-context' not in cmd for cmd in commands))
    def test_missing_mount_is_actionable(self):
        executor = KubectlExecutor(Settings(_env_file=None, kubeconfig_path='/missing/config'))
        self.assertIn('mount', executor.get('pods')['error'])
    def test_raw_stderr_not_exposed(self):
        error = KubectlExecutor.friendly_error('connection refused https://private?token=secret')
        self.assertNotIn('secret', error)
        self.assertIn('network', error)

class Phase5FlowTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        self.service = MagicMock()
        self.service.records.return_value = [{}]
        app.dependency_overrides[require_user] = lambda: USER
        app.dependency_overrides[get_insforge] = lambda: self.service
        self.client = TestClient(app)
    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.saved)
    def test_clusters_require_auth(self):
        app.dependency_overrides.pop(require_user)
        self.assertEqual(self.client.get('/clusters').status_code, 401)
    def test_unknown_context_does_not_touch_cluster_or_history(self):
        with patch.object(KubectlExecutor, 'run', return_value={'ok':True,'data':CONFIG}), patch('app.api.investigate.investigate_cluster') as collect:
            response = self.client.post('/investigate', json={'context':'not-in-config'})
        self.assertEqual(response.status_code,400)
        collect.assert_not_called()
        self.service.records.assert_not_called()
    def test_selected_context_flows_through_collection_history_and_response(self):
        def collect(executor, progress):
            self.assertEqual(executor.context, 'test')
            for stage in ['pods','logs','events','deployments','network']:
                progress(stage, 'running'); progress(stage, 'completed')
            return {'status':'success','investigation':{s:{'ok':True} for s in ['pods','logs','events','deployments','network']}}
        with patch('app.api.investigate.resolve_context', return_value=SELECTED), patch('app.api.investigate.investigate_cluster', side_effect=collect), patch('app.api.investigate.analyze_investigation', return_value={'status':'success','diagnosis':{'root_cause':'No failure observed','confidence':70}}):
            response = self.client.post('/investigate', json={'context':'test'})
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['cluster']['context'],'test')
        self.assertEqual(data['summary']['state'],'no_findings')
        self.assertEqual(data['run_status'],'completed')
        writes=self.service.records.call_args_list
        self.assertEqual(writes[0].kwargs['values']['cluster_context'],'test')
        self.assertEqual(writes[-1].kwargs['values']['status'],'completed')
        self.assertTrue(all(c.args[1] == USER['id'] for c in writes))
    def test_ai_failure_keeps_evidence_and_partial_history(self):
        with patch('app.api.investigate.resolve_context',return_value=SELECTED), patch('app.api.investigate.investigate_cluster',return_value={'status':'partial','investigation':{'pods':{'ok':False,'error':'Cluster unreachable'}}}), patch('app.api.investigate.analyze_investigation',return_value={'status':'error','error':'Provider timed out'}):
            response=self.client.post('/investigate',json={'context':'test'})
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['run_status'],'partial')
        self.assertEqual(data['ai']['error'],'Provider timed out')
        self.assertEqual(data['summary']['state'],'incomplete')
        self.assertIn('pods',data['investigation'])
    def test_unexpected_failure_is_sanitized_and_persisted(self):
        with patch('app.api.investigate.resolve_context',return_value=SELECTED), patch('app.api.investigate.investigate_cluster',side_effect=RuntimeError('private-token')):
            response=self.client.post('/investigate',json={'context':'test'})
        self.assertEqual(response.status_code,500)
        self.assertNotIn('private-token',response.text)
        self.assertEqual(self.service.records.call_args.kwargs['values']['status'],'error')
    def test_unknown_fields_not_interpreted_as_kubectl_flags(self):
        self.assertEqual(self.client.post('/investigate',json={'context':'test','server':'evil'}).status_code,422)

if __name__ == '__main__': unittest.main()
