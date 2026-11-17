from typing import Annotated
import re
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, SecretStr
from app.core.config import get_settings
from app.services.insforge import InsForge, get_insforge

router = APIRouter(prefix='/auth', tags=['auth'])
bearer = HTTPBearer(auto_error=False)
COOKIE = 'agent_refresh'

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr

class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

class SignupCredentials(EmailRequest):
    password: SecretStr

class VerificationRequest(EmailRequest):
    otp: str = Field(pattern=r'^[0-9]{6}$')

def trusted_origin(request: Request):
    origin = request.headers.get('origin')
    # Browser session mutations must originate from our UI. CLI requests have no Origin.
    if origin and origin not in get_settings().cors_origins:
        raise HTTPException(403, 'Origin is not allowed')

def public_auth_config(service: InsForge):
    data = service.request('GET', '/api/auth/public-config')
    if not isinstance(data, dict) or type(data.get('requireEmailVerification')) is not bool:
        raise HTTPException(502, 'InsForge returned an invalid authentication configuration')
    method = data.get('verifyEmailMethod')
    if method not in ('code', 'link'):
        raise HTTPException(502, 'InsForge verification method is not supported')
    minimum = data.get('passwordMinLength', 8)
    if type(minimum) is not int or not 1 <= minimum <= 1024:
        minimum = 8
    return {'requireEmailVerification': data['requireEmailVerification'],
            'verifyEmailMethod': method, 'disableSignup': data.get('disableSignup') is True,
            'passwordMinLength': minimum,
            **{rule: data.get(rule) is True for rule in
               ('requireNumber', 'requireLowercase', 'requireUppercase', 'requireSpecialChar')}}

def verification_redirect(request: Request):
    # Never accept an arbitrary redirect destination from a registration payload.
    origins = get_settings().cors_origins
    origin = request.headers.get('origin') or (origins[0] if origins else None)
    if not origin or origin not in origins:
        raise HTTPException(503, 'Configure the frontend origin for verification links')
    return origin.rstrip('/') + '/'

@router.get('/config')
def auth_config(response: Response, service: Annotated[InsForge, Depends(get_insforge)]):
    response.headers['Cache-Control'] = 'no-store'
    return public_auth_config(service)

@router.post('/signup', dependencies=[Depends(trusted_origin)])
def signup(body: SignupCredentials, request: Request, response: Response,
           service: Annotated[InsForge, Depends(get_insforge)]):
    response.headers['Cache-Control'] = 'no-store'
    config = public_auth_config(service)
    if config['disableSignup']:
        raise HTTPException(403, 'New account registration is disabled for this project.')
    password = body.password.get_secret_value()
    if not config['passwordMinLength'] <= len(password) <= 1024:
        raise HTTPException(400, f"Use a password of at least {config['passwordMinLength']} characters (maximum 1024).")
    for rule, pattern, description in [
        ('requireNumber', r'[0-9]', 'a number'),
        ('requireLowercase', r'[a-z]', 'a lowercase letter'),
        ('requireUppercase', r'[A-Z]', 'an uppercase letter'),
        ('requireSpecialChar', r'[^A-Za-z0-9]', 'a special character'),
    ]:
        if config[rule] and not re.search(pattern, password):
            raise HTTPException(400, f'Your password must include {description}.')
    payload = {'email': body.email.strip(), 'password': password}
    if config['requireEmailVerification'] and config['verifyEmailMethod'] == 'link':
        payload['redirectTo'] = verification_redirect(request)
    # Public signup only: no admin key, autoConfirm, role, or client-controlled redirect.
    data = service.request('POST', '/api/auth/users', params={'client_type': 'server'},
                           json=payload, auth_action='signup')
    if not isinstance(data, dict):
        raise HTTPException(502, 'InsForge returned an invalid signup response')
    if data.get('requireEmailVerification') is True or config['requireEmailVerification']:
        return {'status': 'verification_required', 'verification_method': config['verifyEmailMethod']}
    if data.get('accessToken') and data.get('refreshToken'):
        return {'status': 'signed_in', **save_session(data, response)}
    # Some deployments omit the verification flag; do not assume an account is verified.
    if config['requireEmailVerification']:
        return {'status': 'verification_required', 'verification_method': config['verifyEmailMethod']}
    return {'status': 'sign_in_required'}

@router.post('/verify-email', dependencies=[Depends(trusted_origin)])
def verify_email(body: VerificationRequest, response: Response,
                 service: Annotated[InsForge, Depends(get_insforge)]):
    data = service.request('POST', '/api/auth/email/verify', params={'client_type': 'server'},
                           json={'email': body.email, 'otp': body.otp}, auth_action='verify')
    return {'status': 'signed_in', **save_session(data, response)}

@router.post('/resend-verification', dependencies=[Depends(trusted_origin)])
def resend_verification(body: EmailRequest, request: Request, response: Response,
                        service: Annotated[InsForge, Depends(get_insforge)]):
    response.headers['Cache-Control'] = 'no-store'
    config = public_auth_config(service)
    payload = {'email': body.email}
    if config['verifyEmailMethod'] == 'link':
        payload['redirectTo'] = verification_redirect(request)
    service.request('POST', '/api/auth/email/send-verification', json=payload, auth_action='resend')
    return {'status': 'sent', 'verification_method': config['verifyEmailMethod'],
            'message': 'If verification is available for this address, an email has been sent.'}

def save_session(data, response: Response):
    if not isinstance(data, dict) or not data.get('accessToken') or not data.get('refreshToken'):
        raise HTTPException(502, 'InsForge did not return a complete session')
    response.set_cookie(COOKIE, data['refreshToken'], httponly=True, samesite='strict',
                        secure=get_settings().session_cookie_secure, path='/auth', max_age=60*60*24*7)
    response.headers['Cache-Control'] = 'no-store'
    return {'user': data.get('user'), 'access_token': data['accessToken']}

def require_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                 service: Annotated[InsForge, Depends(get_insforge)]):
    if credentials is None:
        raise HTTPException(401, 'Sign in to investigate the cluster', headers={'WWW-Authenticate': 'Bearer'})
    return service.user(credentials.credentials)

@router.post('/login', dependencies=[Depends(trusted_origin)])
def login(body: Credentials, response: Response, service: Annotated[InsForge, Depends(get_insforge)]):
    data = service.request('POST', '/api/auth/sessions', params={'client_type': 'server'},
                           json={'email': body.email, 'password': body.password.get_secret_value(), 'method': 'password'})
    return save_session(data, response)

@router.post('/refresh', dependencies=[Depends(trusted_origin)])
def refresh(request: Request, response: Response, service: Annotated[InsForge, Depends(get_insforge)]):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, 'Sign in to continue')
    data = service.request('POST', '/api/auth/refresh', params={'client_type': 'server'}, json={'refreshToken': token})
    return save_session(data, response)

@router.post('/logout', dependencies=[Depends(trusted_origin)])
def logout(request: Request, response: Response, service: Annotated[InsForge, Depends(get_insforge)]):
    token = request.cookies.get(COOKIE)
    # Local sign-out always clears the cookie, even if upstream is unavailable.
    if token:
        try:
            service.request('POST', '/api/auth/logout', params={'client_type': 'server'}, json={'refreshToken': token})
        except HTTPException:
            pass
    response.delete_cookie(COOKIE, path='/auth', httponly=True, samesite='strict',
                           secure=get_settings().session_cookie_secure)
    response.headers['Cache-Control'] = 'no-store'
    return {'status': 'signed_out'}

@router.get('/me')
def me(user: Annotated[dict, Depends(require_user)], response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'user': user, 'realtime_url': get_settings().insforge_url}
