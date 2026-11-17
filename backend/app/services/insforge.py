"""Small InsForge REST adapter. Tokens and upstream response bodies are never logged."""
from uuid import UUID
import httpx
from fastapi import HTTPException
from loguru import logger
from app.core.config import get_settings


def registration_error(response):
    """Classify known provider errors; never return/log a raw provider message."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    code = body.get('error')
    message = body.get('message')
    message = message.lower() if isinstance(message, str) else ''
    if response.status_code == 401:
        return (503, 'project_credential_rejected',
                'InsForge rejected the project anonymous key. Check INSFORGE_ANON_KEY belongs to the same project as INSFORGE_URL, then recreate the backend container.')
    if code == 'AUTH_VERIFICATION_EMAIL_DELIVERY_FAILED':
        return (503, 'verification_delivery_failed',
                'The account was created, but the verification email could not be sent. '
                'Use Verify an existing account to resend it. The administrator should check InsForge email delivery settings.')
    if code == 'AUTH_SIGNUP_DISABLED':
        return 403, 'signup_disabled', 'New account registration is disabled in this InsForge project.'
    if code == 'AUTH_EMAIL_EXISTS' or response.status_code == 409:
        return (400, 'account_conflict',
                'Registration could not be completed. If you already registered this email, sign in or use Verify an existing account.')
    if code == 'AUTH_WEAK_PASSWORD':
        return 400, 'password_policy', 'Your password does not meet the InsForge project password requirements.'
    if code == 'INVALID_INPUT':
        if 'redirect' in message and ('allowed' in message or 'required' in message):
            return (400, 'verification_redirect',
                    'Email verification redirect is not configured. In InsForge Authentication settings, '
                    'allow http://localhost:3000/ as a verification redirect for this local app, then retry.')
        if 'password' in message:
            return 400, 'password_policy', 'Your password does not meet the InsForge project password requirements.'
        if 'email' in message:
            return 400, 'email_format', 'InsForge rejected the email format. Check the address and try again.'
    if response.status_code == 429:
        return 429, 'rate_limited', 'Too many attempts. Please wait before trying again.'
    if response.status_code >= 500:
        return 503, 'provider_unavailable', 'InsForge registration is temporarily unavailable. Please try again later.'
    return (400, 'registration_rejected',
            f'InsForge rejected registration (HTTP {response.status_code}). '
            'Check whether this email is already registered and whether public signup is enabled.')


class InsForge:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport

    def request(self, method, path, *, token=None, admin=False, auth_action=None, **kwargs):
        url = self.settings.insforge_url.rstrip('/')
        if not url:
            raise HTTPException(503, 'Configure INSFORGE_URL to enable login and history')
        headers = {'Content-Type': 'application/json'}
        if admin:
            key = self.settings.insforge_api_key.get_secret_value()
            if not key:
                raise HTTPException(503, 'Configure the server-only INSFORGE_API_KEY for history')
            headers['X-API-Key'] = key
            headers['Prefer'] = 'return=representation'
        elif token:
            headers['Authorization'] = f'Bearer {token}'
        elif auth_action == 'signup':
            # Registration uses the anon identity, never the history/admin key.
            key = self.settings.insforge_anon_key.get_secret_value().strip()
            if not key:
                raise HTTPException(503, 'Configure INSFORGE_ANON_KEY with your InsForge project anonymous key to enable signup.')
            if not key.startswith('anon_'):
                raise HTTPException(503, 'INSFORGE_ANON_KEY must be the project anonymous key (anon_...), not the admin API key or OpenRouter key.')
            headers['Authorization'] = f'Bearer {key}'
        try:
            with httpx.Client(timeout=10, transport=self.transport) as client:
                response = client.request(method, url + path, headers=headers, **kwargs)
        except httpx.RequestError:
            raise HTTPException(503, 'InsForge connection unavailable') from None
        if auth_action == 'signup' and response.status_code >= 400:
            status, category, detail = registration_error(response)
            logger.warning('InsForge signup rejected: upstream_status={} category={}', response.status_code, category)
            raise HTTPException(status, detail)
        if auth_action and response.status_code in (400, 401, 403, 409, 422, 429):
            # Fixed messages only: never forward upstream bodies or credentials.
            if response.status_code == 429:
                raise HTTPException(429, 'Too many attempts. Please wait before trying again.')
            messages = {
                'signup': 'Could not create the account. Check the email and password requirements, or sign in if already registered. Signup may be disabled by the project administrator.',
                'verify': 'The verification code is invalid or expired. Check the code or request a new one.',
                'resend': 'Could not send verification email. Please wait and try again.',
            }
            raise HTTPException(400, messages.get(auth_action, 'Authentication request was rejected.'))
        if response.status_code in (401, 403) and not admin:
            raise HTTPException(401, 'Session expired, invalid credentials, or account requires verification')
        if response.status_code >= 400:
            # Do not surface SQL, raw upstream bodies, credentials, or passwords.
            raise HTTPException(503, f'InsForge request failed (HTTP {response.status_code}); check project setup')
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise HTTPException(502, 'InsForge returned an invalid response') from None

    def user(self, token):
        data = self.request('GET', '/api/auth/sessions/current', token=token)
        user = data.get('user') if isinstance(data, dict) else None
        try:
            user_id = str(UUID(user['id']))
        except (TypeError, KeyError, ValueError, AttributeError):
            raise HTTPException(401, 'A valid user session is required') from None
        if user.get('role') not in (None, 'authenticated'):
            raise HTTPException(403, 'A user session is required')
        return {'id': user_id, 'email': user.get('email', '')}

    def records(self, method, user_id, *, run_id=None, values=None, limit=20):
        # Every admin-key query is also scoped to the verified caller.
        params = {'user_id': f'eq.{UUID(user_id)}'}
        if run_id:
            params['id'] = f'eq.{UUID(str(run_id))}'
        if method == 'GET':
            params.update(order='created_at.desc', limit=str(limit))
        if method == 'POST':
            values = [{**values, 'user_id': str(UUID(user_id))}]
            params = {}
        result = self.request(method, '/api/database/records/investigations', admin=True,
                              params=params, **({'json': values} if values is not None else {}))
        if not isinstance(result, list):
            raise HTTPException(502, 'InsForge history response was invalid')
        if method in ('POST', 'PATCH') and len(result) != 1:
            raise HTTPException(503, 'History write was not confirmed')
        return result

def get_insforge():
    return InsForge()
