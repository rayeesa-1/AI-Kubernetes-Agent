import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.main import app
from app.api.auth import require_user
from app.core.config import Settings
from app.services.insforge import InsForge, get_insforge
from app.services.history import InvestigationHistory
from app.services.investigation import investigate_cluster

USER = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'

def settings():
    return Settings(_env_file=None, insforge_url='https://test.insforge.app', insforge_api_key=SecretStr('server-private-key'))

def adapter(handler):
    return InsForge(settings(), httpx.MockTransport(handler))

class DashboardSecurityTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.saved)
    def test_unauthenticated_requests_never_start_collection(self):
        with patch('app.api.investigate.investigate_cluster') as collect:
            for method, path in [('POST','/investigate'), ('GET','/investigations'), ('GET',f'/investigations/{uuid4()}')]:
                self.assertEqual(self.client.request(method, path).status_code, 401)
        collect.assert_not_called()
        self.assertEqual(self.client.get('/health').status_code, 200)
    def test_invalid_token_is_verified_upstream(self):
        def handler(request):
            self.assertEqual(request.url.path, '/api/auth/sessions/current')
            self.assertEqual(request.headers['Authorization'], 'Bearer forged-token')
            return httpx.Response(401, text='private upstream body')
        app.dependency_overrides[get_insforge] = lambda: adapter(handler)
        response = self.client.get('/investigations', headers={'Authorization':'Bearer forged-token'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('private', response.text)
    def test_history_query_is_scoped_to_verified_user_and_cross_user_id_is_404(self):
        run_id = str(uuid4())
        def handler(request):
            if request.url.path == '/api/auth/sessions/current':
                return httpx.Response(200, json={'user': {'id': USER, 'email':'a@example.com','role':'authenticated'}})
            self.assertEqual(request.headers['x-api-key'], 'server-private-key')
            self.assertEqual(request.url.params['user_id'], f'eq.{USER}')
            self.assertEqual(request.url.params['id'], f'eq.{run_id}')
            self.assertNotIn('Authorization', request.headers)
            return httpx.Response(200, json=[])
        app.dependency_overrides[get_insforge] = lambda: adapter(handler)
        response = self.client.get(f'/investigations/{run_id}', headers={'Authorization':'Bearer user-token'})
        self.assertEqual(response.status_code, 404)
    def test_anonymous_role_not_accepted_as_user(self):
        app.dependency_overrides[get_insforge] = lambda: adapter(lambda request: httpx.Response(200,
            json={'user': {'id': USER, 'role':'anon'}}))
        self.assertEqual(self.client.get('/investigations',headers={'Authorization':'Bearer anon'}).status_code,403)
    def test_login_keeps_refresh_private_and_rotates_cookie(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.params['client_type'], 'server')
            token = 'refresh-two' if request.url.path.endswith('/refresh') else 'refresh-one'
            return httpx.Response(200,json={'user':{'id':USER,'email':'a@example.com'},'accessToken':'access-token','refreshToken':token})
        app.dependency_overrides[get_insforge] = lambda: adapter(handler)
        login = self.client.post('/auth/login',json={'email':'a@example.com','password':'secret'})
        self.assertEqual(login.status_code,200)
        self.assertNotIn('refresh-one',login.text)
        cookie = login.headers['set-cookie']
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=strict',cookie)
        refresh = self.client.post('/auth/refresh')
        self.assertEqual(refresh.status_code,200)
        self.assertIn('refresh-two',refresh.headers['set-cookie'])
        self.assertIn(b'refresh-one',calls[-1].content)
    def test_cross_origin_cookie_mutation_is_blocked(self):
        for path in ['/auth/login','/auth/refresh','/auth/logout']:
            result = self.client.post(path,headers={'Origin':'https://evil.example'},json={'email':'a@example.com','password':'secret'})
            self.assertEqual(result.status_code,403)
    def test_cors_allows_ui_authorization_headers(self):
        response = self.client.options('/investigate',headers={'Origin':'http://localhost:3000',
            'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,x-investigation-id'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['access-control-allow-credentials'],'true')
    def test_logout_clears_cookie_when_provider_fails(self):
        service = MagicMock()
        service.request.side_effect = HTTPException(503,'unavailable')
        app.dependency_overrides[get_insforge] = lambda: service
        self.client.cookies.set('agent_refresh','refresh-one',path='/auth')
        response = self.client.post('/auth/logout')
        self.assertEqual(response.status_code,200)
        self.assertIn('Max-Age=0',response.headers['set-cookie'])
    def test_missing_history_configuration_does_not_start_cluster_work(self):
        app.dependency_overrides[require_user] = lambda: {'id':USER}
        service = MagicMock()
        service.records.side_effect = HTTPException(503,'Configure InsForge')
        app.dependency_overrides[get_insforge] = lambda: service
        with patch('app.api.investigate.resolve_context', return_value={'context':'test','cluster':'test'}), patch('app.api.investigate.investigate_cluster') as collect:
            self.assertEqual(self.client.post('/investigate').status_code,503)
        collect.assert_not_called()

class ProgressTests(unittest.TestCase):
    def test_progress_reflects_real_collector_order_and_failure(self):
        class Executor:
            def get(self, resource):
                return {'ok':False,'error':'Forbidden'} if resource == 'events' else {'ok':True,'data':{'items':[]}}
        states = []
        result = investigate_cluster(Executor(),progress=lambda stage,state: states.append((stage,state)))
        self.assertEqual(result['status'],'partial')
        self.assertEqual(states,[('pods','running'),('pods','completed'),('logs','running'),('logs','completed'),
            ('events','running'),('events','error'),('deployments','running'),('deployments','completed'),
            ('network','running'),('network','completed')])
    def test_failed_persistence_does_not_discard_result(self):
        service = MagicMock()
        service.records.side_effect = HTTPException(503,'offline')
        history = InvestigationHistory(USER,uuid4(),service)
        history.update('ai','error')
        status = history.finish({'status':'success','ai':{'status':'error','error':'Provider unavailable'},'diagnosis':None})
        self.assertEqual(status,'partial')
        self.assertTrue(history.warning)
    def test_success_and_ai_failure_are_saved_with_different_statuses(self):
        service=MagicMock()
        history=InvestigationHistory(USER,uuid4(),service)
        history.start()
        self.assertEqual(history.finish({'status':'success','ai':{'status':'success'},'diagnosis':{'root_cause':'No observed failure','confidence':75}}),'completed')
        saved=service.records.call_args.kwargs['values']
        self.assertEqual(saved['confidence'],75)
        self.assertNotIn('investigation',saved)
        self.assertEqual(history.finish({'status':'success','ai':{'status':'error'},'diagnosis':None}),'partial')
    def test_upstream_errors_do_not_expose_keys_or_bodies(self):
        service=adapter(lambda request: httpx.Response(500,text='private database password server-private-key'))
        with self.assertRaises(HTTPException) as caught:
            service.records('GET',USER)
        self.assertNotIn('private',caught.exception.detail)

if __name__ == '__main__': unittest.main()
