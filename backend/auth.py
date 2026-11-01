"""Supabase account authentication, deliberately separate from demo identities."""
import base64
from dataclasses import dataclass
from functools import lru_cache
import json
import math
import os
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
import jwt
from pydantic import BaseModel, ConfigDict

bearer = HTTPBearer(auto_error=False)
ASYMMETRIC_ALGORITHMS = frozenset({'ES256', 'RS256'})


def auth_http_client():
    return httpx.Client(timeout=5, follow_redirects=False, trust_env=False)


class AccountUser(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    role: Literal['authenticated'] = 'authenticated'


@dataclass(frozen=True)
class AuthSettings:
    url: str
    publishable_key: str
    allow_legacy: bool

    @property
    def issuer(self):
        return self.url + '/auth/v1'


def configuration_error():
    return HTTPException(503, 'Supabase authentication is unavailable or not configured.', headers={'Cache-Control': 'private, no-store'})


def unauthorized():
    return HTTPException(401, 'Invalid or missing access token.', headers={'WWW-Authenticate': 'Bearer', 'Cache-Control': 'private, no-store'})


def auth_settings() -> AuthSettings:
    # Never derive the trusted issuer/JWKS location from an incoming token.
    url = os.getenv('SUPABASE_URL', '').strip().rstrip('/')
    key = os.getenv('SUPABASE_PUBLISHABLE_KEY', '').strip()
    legacy = os.getenv('SUPABASE_AUTH_LEGACY_HS256', 'false').strip().lower()
    try:
        parsed = urlsplit(url)
        _ = parsed.port
        local_http = parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'} and os.getenv('APP_ENV', 'development') == 'development'
        valid = (
            bool(parsed.hostname) and (parsed.scheme == 'https' or local_http)
            and not parsed.username and not parsed.password and not parsed.query
            and not parsed.fragment and not parsed.path
            and not any(char.isspace() for char in url)
        )
    except ValueError:
        valid = False
    if not valid or not key.startswith('sb_publishable_') or any(c.isspace() for c in key) or legacy not in {'true', 'false'}:
        raise configuration_error()
    return AuthSettings(url, key, legacy == 'true')


@lru_cache(maxsize=8)
def jwks_client(issuer: str):
    return jwt.PyJWKClient(
        issuer + '/.well-known/jwks.json',
        timeout=5,
        lifespan=300,
        cache_keys=False,  # Individual keys must not outlive the bounded JWKS cache.
        cooldown_duration=30,
    )


def checked_user(claims: dict, settings: AuthSettings) -> AccountUser:
    """Check application claims only after cryptographic or Auth-server validation."""
    now = time.time()
    if claims.get('iss') != settings.issuer:
        raise unauthorized()
    audience = claims.get('aud')
    if audience != 'authenticated' and not (isinstance(audience, list) and 'authenticated' in audience and all(isinstance(v, str) for v in audience)):
        raise unauthorized()
    for name in ('exp', 'iat'):
        value = claims.get(name)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise unauthorized()
    if claims['exp'] <= now or claims['iat'] > now:
        raise unauthorized()
    if 'nbf' in claims and (type(claims['nbf']) not in (int, float) or not math.isfinite(claims['nbf']) or claims['nbf'] > now):
        raise unauthorized()
    if claims.get('role') != 'authenticated' or claims.get('is_anonymous', False) is not False:
        raise unauthorized()
    try:
        subject = claims['sub']
        if not isinstance(subject, str) or str(UUID(subject)) != subject or UUID(subject).int == 0:
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError):
        raise unauthorized() from None
    return AccountUser(id=subject)


def legacy_user(token: str, settings: AuthSettings) -> AccountUser:
    """HS256 authenticity is verified by Supabase, never by trusting decoded input.

    Only AFTER the exact token succeeds at the trusted Auth /user endpoint do we
    parse its payload to impose our stricter issuer/audience/time/role contract.
    Identity must also match the user returned by that authenticated endpoint.
    No shared JWT secret, API-key-as-user fallback, or unverified JWT decode exists.
    """
    if not settings.allow_legacy:
        raise unauthorized()
    try:
        with auth_http_client() as client:
            response = client.get(settings.issuer + '/user', headers={
                'apikey': settings.publishable_key,
                'Authorization': 'Bearer ' + token,
            })
        if response.status_code in (401, 403):
            raise unauthorized()
        if response.status_code != 200:
            raise configuration_error()
        remote = response.json()
        if not isinstance(remote, dict):
            raise configuration_error()
    except (httpx.HTTPError, ValueError):
        raise configuration_error() from None
    try:
        payload = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if not isinstance(claims, dict):
            raise ValueError
    except (ValueError, UnicodeError, IndexError):
        raise unauthorized() from None
    user = checked_user(claims, settings)
    if remote.get('id') != user.id or remote.get('role') != 'authenticated' or remote.get('is_anonymous', False) is not False:
        raise unauthorized()
    return user


def authenticated_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> AccountUser:
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise unauthorized()
    settings = auth_settings()
    token = credentials.credentials
    if len(token) > 16384 or len(token.split('.')) != 3:
        raise unauthorized()
    try:
        header = jwt.get_unverified_header(token)  # Untrusted routing hints only, never identity.
        algorithm = header.get('alg')
        if any(name in header for name in ('jku', 'x5u', 'jwk', 'crit')):
            raise unauthorized()
        if algorithm == 'HS256':
            return legacy_user(token, settings)
        if algorithm not in ASYMMETRIC_ALGORITHMS or not isinstance(header.get('kid'), str) or not 0 < len(header['kid']) <= 256:
            raise unauthorized()
        signing_key = jwks_client(settings.issuer).get_signing_key_from_jwt(token)
        if signing_key.algorithm_name != algorithm:
            raise unauthorized()
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            issuer=settings.issuer,
            audience='authenticated',
            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
        )
        return checked_user(claims, settings)
    except jwt.PyJWKClientConnectionError:
        raise configuration_error() from None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError):
        raise unauthorized() from None


def reject_account_auth_on_demo(request: Request):
    if 'authorization' in request.headers:
        raise HTTPException(403, 'Account tokens cannot authenticate demo endpoints.')
