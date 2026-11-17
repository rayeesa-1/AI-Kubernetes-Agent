"""Registration contracts with simulated InsForge responses; no live accounts."""
import json
import unittest
import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from app.main import app
from app.core.config import Settings
from app.services.insforge import InsForge, get_insforge

USER = {'id': '11111111-1111-4111-8111-111111111111', 'email': 'new@example.com'}
SESSION = {'user': USER, 'accessToken': 'test-access', 'refreshToken': 'test-refresh'}
CONFIG = {'requireEmailVerification': True, 'verifyEmailMethod': 'code', 'disableSignup': False,
          'passwordMinLength': 10, 'requireNumber': True, 'requireLowercase': True,
          'requireUppercase': True, 'requireSpecialChar': True}
CREDENTIALS = {'email': 'new@example.com', 'password': 'LongPassword1!'}

class SignupTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.requests = []
    def tearDown(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.saved)
    def install(self, config=None, result=None, status=200):
        config = CONFIG if config is None else config
        def handler(request):
            self.requests.append(request)
            self.assertNotIn('x-api-key', request.headers)
            if request.url.path == '/api/auth/users':
                self.assertEqual(request.headers.get('authorization'), 'Bearer anon_test-key')
            else:
                self.assertNotIn('authorization', request.headers)
            if request.url.path == '/api/auth/public-config':
                return httpx.Response(200, json=config)
            if request.url.path in ('/api/auth/users', '/api/auth/email/verify'):
                self.assertEqual(request.url.params['client_type'], 'server')
            return httpx.Response(status, json=SESSION if result is None else result)
        settings = Settings(_env_file=None, insforge_url='https://test.insforge.app',
                            insforge_api_key=SecretStr('admin-secret'),
                            insforge_anon_key=SecretStr('anon_test-key'))
        service = InsForge(settings, httpx.MockTransport(handler))
        app.dependency_overrides[get_insforge] = lambda: service
    def test_config_allowlist(self):
        self.install({**CONFIG, 'smtpConfig': {'password': 'private'}, 'allowedRedirectUrls': ['private']})
        response = self.client.get('/auth/config')
        self.assertEqual(response.json(), CONFIG)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertNotIn('private', response.text)
    def test_unverified_signup_never_creates_session_even_with_tokens(self):
        self.install(result={**SESSION, 'requireEmailVerification': True})
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.json(), {'status': 'verification_required', 'verification_method': 'code'})
        self.assertNotIn('set-cookie', response.headers)
        self.assertNotIn('test-access', response.text)
        self.assertNotIn('test-refresh', response.text)
    def test_signup_cannot_inject_admin_fields_or_redirect(self):
        self.install(result={'requireEmailVerification': True, 'accessToken': None})
        self.client.post('/auth/signup', json={**CREDENTIALS, 'autoConfirm': True, 'role': 'project_admin', 'redirectTo': 'https://evil.example'})
        self.assertEqual(self.requests[-1].url.path, '/api/auth/users')
        self.assertEqual(json.loads(self.requests[-1].content), CREDENTIALS)
    def test_disabled_signup_never_creates_user(self):
        self.install({**CONFIG, 'disableSignup': True})
        self.assertEqual(self.client.post('/auth/signup', json=CREDENTIALS).status_code, 403)
        self.assertEqual(len(self.requests), 1)
    def test_password_policy_checked_before_upstream_creation_without_echoing_password(self):
        for password in ['short', 'longpassword1!', 'LONGPASSWORD1!', 'LongPassword!!', 'LongPassword11']:
            with self.subTest(password=password):
                self.install(); self.requests.clear()
                response = self.client.post('/auth/signup', json={**CREDENTIALS, 'password': password})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(password, response.text)
                self.assertEqual(len(self.requests), 1)
    def test_link_signup_redirects_to_allowed_frontend(self):
        self.install({**CONFIG, 'verifyEmailMethod': 'link'}, result={'requireEmailVerification': True})
        response = self.client.post('/auth/signup', json=CREDENTIALS, headers={'Origin': 'http://localhost:3000'})
        self.assertEqual(response.json()['verification_method'], 'link')
        self.assertEqual(json.loads(self.requests[-1].content)['redirectTo'], 'http://localhost:3000/')
    def test_signup_without_verification_sets_private_refresh_cookie(self):
        self.install({**CONFIG, 'requireEmailVerification': False})
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.json()['status'], 'signed_in')
        self.assertEqual(response.json()['access_token'], 'test-access')
        self.assertNotIn('test-refresh', response.text)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('SameSite=strict', response.headers['set-cookie'])
    def test_no_tokens_never_claims_signed_in(self):
        self.install({**CONFIG, 'requireEmailVerification': False}, result={'user': USER})
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.json()['status'], 'sign_in_required')
        self.assertNotIn('set-cookie', response.headers)
    def test_missing_verification_flag_respects_required_config(self):
        self.install(result={'user': USER, 'accessToken': None})
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.json()['status'], 'verification_required')
    def test_required_verification_never_accepts_tokens_when_flag_missing(self):
        self.install(result=SESSION)
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.json()['status'], 'verification_required')
        self.assertNotIn('set-cookie', response.headers)
        self.assertNotIn('test-access', response.text)
    def test_link_method_without_verification_omits_redirect(self):
        self.install({**CONFIG, 'requireEmailVerification': False, 'verifyEmailMethod': 'link'})
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.json()['status'], 'signed_in')
        self.assertNotIn('redirectTo', json.loads(self.requests[-1].content))
    def test_known_registration_errors_have_actionable_safe_messages(self):
        cases = [
            (403, {'error': 'AUTH_SIGNUP_DISABLED'}, 403, 'disabled'),
            (409, {'error': 'AUTH_EMAIL_EXISTS'}, 400, 'already registered'),
            (400, {'error': 'INVALID_INPUT', 'message': 'https://private.example/?token=private is not in the allowed redirect URLs'}, 400, 'http://localhost:3000/'),
            (400, {'error': 'INVALID_INPUT', 'message': 'password: private requirement'}, 400, 'password requirements'),
            (400, {'error': 'AUTH_WEAK_PASSWORD'}, 400, 'password requirements'),
            (500, {'error': 'AUTH_VERIFICATION_EMAIL_DELIVERY_FAILED'}, 503, 'account was created'),
            (429, {'error': 'AUTH_VERIFICATION_EMAIL_DELIVERY_FAILED'}, 503, 'resend'),
            (400, {'error': {'unexpected': ['private']}}, 400, 'HTTP 400'),
            (401, {'error': 'private', 'message': 'secret-token'}, 503, 'INSFORGE_ANON_KEY'),
        ]
        for upstream_status, body, expected_status, text in cases:
            with self.subTest(body=body):
                self.install(result=body, status=upstream_status)
                response = self.client.post('/auth/signup', json=CREDENTIALS)
                self.assertEqual(response.status_code, expected_status)
                self.assertIn(text, response.json()['detail'])
                self.assertNotIn('private', response.text)
                self.assertNotIn('secret-token', response.text)
                self.assertNotIn('set-cookie', response.headers)
    def test_signup_failure_logs_only_sanitized_category(self):
        from loguru import logger
        entries = []
        sink = logger.add(lambda message: entries.append(str(message)))
        try:
            self.install(result={'error': 'AUTH_EMAIL_EXISTS', 'message': 'private-token password admin-secret'}, status=409)
            self.client.post('/auth/signup', json=CREDENTIALS)
        finally:
            logger.remove(sink)
        text = ''.join(entries)
        self.assertIn('category=account_conflict', text)
        for secret in ['private-token', 'admin-secret', 'anon_test-key', CREDENTIALS['password'], USER['email']]:
            self.assertNotIn(secret, text)
    def test_missing_anon_key_stops_before_registration_request(self):
        self.install()
        service = app.dependency_overrides[get_insforge]()
        service.settings.insforge_anon_key = SecretStr('')
        response = self.client.post('/auth/signup', json=CREDENTIALS)
        self.assertEqual(response.status_code, 503)
        self.assertIn('Configure INSFORGE_ANON_KEY', response.json()['detail'])
        self.assertEqual(len(self.requests), 1)
    def test_admin_or_openrouter_key_cannot_replace_anon_key(self):
        for value in ['ik_admin-secret', 'sk-or-secret']:
            self.install()
            service = app.dependency_overrides[get_insforge]()
            service.settings.insforge_anon_key = SecretStr(value)
            self.requests.clear()
            response = self.client.post('/auth/signup', json=CREDENTIALS)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(value, response.text)
            self.assertEqual(len(self.requests), 1)
    def test_email_code_verification_establishes_private_session(self):
        self.install()
        response = self.client.post('/auth/verify-email', json={'email': USER['email'], 'otp': '123456'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.requests[-1].url.path, '/api/auth/email/verify')
        self.assertEqual(response.json()['user'], USER)
        self.assertNotIn('test-refresh', response.text)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
    def test_invalid_code_has_safe_message(self):
        self.install(result={'message': 'private backend dump'}, status=400)
        response = self.client.post('/auth/verify-email', json={'email': USER['email'], 'otp': '123456'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid or expired', response.text)
        self.assertNotIn('private', response.text)
        self.assertNotIn('set-cookie', response.headers)
    def test_invalid_input_never_contacts_provider(self):
        self.install()
        for body in [{'email': USER['email'], 'otp': 'abc123'}, {'email': 'bad', 'otp': '123456'}]:
            self.assertEqual(self.client.post('/auth/verify-email', json=body).status_code, 422)
        self.assertEqual(self.requests, [])
    def test_resend_has_generic_response_and_trusted_redirect(self):
        self.install({**CONFIG, 'verifyEmailMethod': 'link'}, result={'message': 'private details'})
        response = self.client.post('/auth/resend-verification', json={'email': USER['email']})
        self.assertEqual(response.json()['verification_method'], 'link')
        self.assertEqual(self.requests[-1].url.path, '/api/auth/email/send-verification')
        self.assertEqual(json.loads(self.requests[-1].content)['redirectTo'], 'http://localhost:3000/')
        self.assertNotIn('private', response.text)
    def test_rate_limit_preserved(self):
        self.install(result={'message': 'private'}, status=429)
        self.assertEqual(self.client.post('/auth/signup', json=CREDENTIALS).status_code, 429)
    def test_provider_errors_never_expose_credentials_or_bodies(self):
        for code in [400, 403, 409, 422, 500]:
            self.install(result={'message': 'admin-secret upstream SQL password'}, status=code)
            response = self.client.post('/auth/signup', json=CREDENTIALS)
            self.assertGreaterEqual(response.status_code, 400)
            self.assertNotIn('admin-secret', response.text)
            self.assertNotIn('upstream SQL', response.text)
    def test_cross_origin_mutations_blocked_before_provider(self):
        self.install()
        for path in ['/auth/signup', '/auth/verify-email', '/auth/resend-verification']:
            response = self.client.post(path, json={**CREDENTIALS, 'otp': '123456'}, headers={'Origin': 'https://evil.example'})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.requests, [])
    def test_unknown_verification_config_fails_before_user_creation(self):
        self.install({'requireEmailVerification': True, 'verifyEmailMethod': 'unknown'})
        self.assertEqual(self.client.post('/auth/signup', json=CREDENTIALS).status_code, 502)
        self.assertEqual(len(self.requests), 1)

if __name__ == '__main__': unittest.main()
