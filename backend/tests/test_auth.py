"""Real signed JWTs; trusted JWKS/Auth HTTP responses are isolated from the network."""
import io
import json
import time
from unittest.mock import Mock
from urllib.error import URLError

from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

from backend import auth
from backend.main import app

PROJECT = 'https://auth-test.example.invalid'
USER = '1c8d6d81-b94a-49f8-b381-58f98349bf7b'
OTHER = '32285050-a200-4dbb-8243-9efcc04587a4'
PUBLISHABLE = 'sb_publishable_synthetic-test-key'
HS_SECRET = 'synthetic-test-signing-secret-with-at-least-32-bytes'


@pytest.fixture(scope='module')
def keys():
    private = {'ES256': ec.generate_private_key(ec.SECP256R1()), 'RS256': rsa.generate_private_key(public_exponent=65537, key_size=2048)}
    jwks = []
    for algorithm, key in private.items():
        item = json.loads((jwt.algorithms.ECAlgorithm if algorithm == 'ES256' else jwt.algorithms.RSAAlgorithm).to_jwk(key.public_key()))
        item.update(kid=algorithm + '-key', alg=algorithm, use='sig')
        jwks.append(item)
    return private, {'keys': jwks}


@pytest.fixture(autouse=True)
def configured(monkeypatch, keys):
    monkeypatch.setenv('SUPABASE_URL', PROJECT)
    monkeypatch.setenv('SUPABASE_PUBLISHABLE_KEY', PUBLISHABLE)
    monkeypatch.setenv('SUPABASE_AUTH_LEGACY_HS256', 'false')
    auth.jwks_client.cache_clear()
    opener = Mock()
    opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(keys[1]).encode())
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: opener)
    # Every test must explicitly opt into a mocked legacy service, never real HTTP.
    monkeypatch.setattr(auth, 'auth_http_client', Mock(side_effect=AssertionError('Unexpected Auth request')))
    yield opener
    auth.jwks_client.cache_clear()


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def claims(**overrides):
    now = int(time.time())
    return {'iss': PROJECT + '/auth/v1', 'aud': 'authenticated', 'sub': USER, 'exp': now + 300,
            'iat': now - 10, 'role': 'authenticated', 'email': 'private@example.invalid',
            'user_metadata': {'private': 'not-returned'}, **overrides}


def token(keys, algorithm='ES256', payload=None, headers=None):
    key = HS_SECRET if algorithm == 'HS256' else keys[0][algorithm]
    return jwt.encode(payload if payload is not None else claims(), key, algorithm=algorithm,
                      headers={'kid': algorithm + '-key', **(headers or {})})


def request(client, value):
    return client.get('/auth/me', headers={'Authorization': 'Bearer ' + value})


def legacy_service(monkeypatch, handler):
    original = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(auth, 'auth_http_client', lambda: original(transport=transport, follow_redirects=False))
    monkeypatch.setenv('SUPABASE_AUTH_LEGACY_HS256', 'true')


@pytest.mark.parametrize('algorithm', ['ES256', 'RS256'])
def test_verified_account_only_safe_identity_and_trusted_jwks(client, keys, configured, algorithm):
    response = request(client, token(keys, algorithm))
    assert response.status_code == 200, response.text
    assert response.json() == {'id': USER, 'role': 'authenticated'}
    assert response.headers['cache-control'] == 'private, no-store'
    assert configured.open.call_args.args[0].full_url == PROJECT + '/auth/v1/.well-known/jwks.json'
    assert request(client, token(keys, algorithm)).status_code == 200
    assert configured.open.call_count == 1


@pytest.mark.parametrize('changes', [
    {'iss': 'https://attacker.example.invalid/auth/v1'}, {'iss': PROJECT + '/auth/v1/'},
    {'aud': 'another-service'}, {'aud': ['anon']}, {'aud': None},
    {'exp': int(time.time()) - 20}, {'exp': True}, {'exp': '9999999999'}, {'exp': 10**400},
    {'iat': int(time.time()) + 600}, {'iat': None}, {'nbf': int(time.time()) + 600},
    {'role': 'anon'}, {'role': 'service_role'}, {'role': None},
    {'sub': ''}, {'sub': 'student-a'}, {'sub': None}, {'sub': '00000000-0000-0000-0000-000000000000'},
    {'is_anonymous': True}, {'is_anonymous': 'false'},
])
def test_rejects_incorrect_claims_even_with_valid_signature(client, keys, changes):
    assert request(client, token(keys, payload=claims(**changes))).status_code == 401


@pytest.mark.parametrize('missing', ['exp', 'iat', 'iss', 'aud', 'sub', 'role'])
def test_required_claims(client, keys, missing):
    payload = claims()
    del payload[missing]
    assert request(client, token(keys, payload=payload)).status_code == 401


def test_invalid_signature_and_hmac_key_confusion_are_rejected(client, keys):
    forged = jwt.encode(claims(), ec.generate_private_key(ec.SECP256R1()), algorithm='ES256', headers={'kid': 'ES256-key'})
    assert request(client, forged).status_code == 401
    assert request(client, token(keys, 'HS256')).status_code == 401  # No automatic legacy fallback.
    assert request(client, jwt.encode(claims(), '', algorithm='none')).status_code == 401


@pytest.mark.parametrize('value', ['not-a-token', 'a.b.c', PUBLISHABLE, 'sb_secret_synthetic-test-key', 'x' * 17000])
def test_api_keys_and_malformed_tokens_are_not_user_authentication(client, value):
    assert request(client, value).status_code == 401


@pytest.mark.parametrize('headers', [{}, {'Authorization': 'Bearer'}, {'Authorization': 'Basic value'}, {'X-User-ID': USER}, {'apikey': PUBLISHABLE}])
def test_missing_bearer_never_falls_back_to_demo_or_frontend_identity(client, headers):
    client.post('/demo/session', json={'student': 'student-a'})
    response = client.get('/auth/me', headers=headers)
    assert response.status_code == 401 and response.headers['www-authenticate'] == 'Bearer'


def test_frontend_id_and_demo_cookie_cannot_override_verified_subject(client, keys):
    client.post('/demo/session', json={'student': 'student-b'})
    response = client.get('/auth/me?user_id=' + OTHER, headers={'Authorization': 'Bearer ' + token(keys), 'X-User-ID': OTHER})
    assert response.json() == {'id': USER, 'role': 'authenticated'}
    assert client.get('/demo/session').json()['student'] == 'student-b'
    assert client.get('/demo/session', headers={'Authorization': 'Bearer ' + token(keys)}).status_code == 403
    assert client.post('/demo/session', json={'student': 'student-a'}, headers={'Authorization': 'Bearer ' + token(keys)}).status_code == 403
    assert client.get('/demo/session').json()['student'] == 'student-b'


@pytest.mark.parametrize('headers', [{'kid': 'unknown'}, {'jku': 'https://attacker.invalid/jwks'}, {'jwk': {}}, {'x5u': 'https://attacker.invalid/cert'}, {'crit': ['custom']}, {'kid': ''}])
def test_token_cannot_choose_an_untrusted_key_source(client, keys, configured, headers):
    assert request(client, token(keys, headers=headers)).status_code == 401
    for call in configured.open.call_args_list:
        assert call.args[0].full_url == PROJECT + '/auth/v1/.well-known/jwks.json'


def test_jwks_outage_fails_closed(client, keys, configured):
    configured.open.side_effect = URLError('synthetic outage')
    response = request(client, token(keys))
    assert response.status_code == 503
    assert 'synthetic' not in response.text and USER not in response.text


@pytest.mark.parametrize('variable,value', [
    ('SUPABASE_URL', ''), ('SUPABASE_PUBLISHABLE_KEY', ''),
    ('SUPABASE_URL', 'http://external.example.invalid'), ('SUPABASE_URL', 'https://user:password@example.invalid'),
    ('SUPABASE_URL', 'https://example.invalid/wrong-path'), ('SUPABASE_URL', 'https://example.invalid?query=1'),
    ('SUPABASE_PUBLISHABLE_KEY', 'sb_secret_not-a-browser-key'), ('SUPABASE_AUTH_LEGACY_HS256', 'maybe'),
])
def test_invalid_configuration_fails_closed(client, keys, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    assert request(client, token(keys)).status_code == 503


def test_absent_supabase_configuration_preserves_local_demo(client, keys, monkeypatch):
    monkeypatch.delenv('SUPABASE_URL')
    monkeypatch.delenv('SUPABASE_PUBLISHABLE_KEY')
    assert request(client, token(keys)).status_code == 503
    assert client.get('/health').status_code == 200
    assert client.get('/listings').status_code == 200
    assert client.post('/demo/session', json={'student': 'student-a'}).status_code == 200


def test_hosted_accounts_disable_legacy_public_demo_override(client, keys, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('PUBLIC_DEMO_MODE', 'true')
    assert request(client, token(keys)).status_code == 200
    assert client.get('/students').status_code == 403
    assert client.post('/demo/session', json={'student': 'student-a'}).status_code == 403
    assert client.get('/negotiations').status_code == 403


def test_legacy_token_is_verified_by_trusted_auth_service_before_use(client, keys, monkeypatch):
    def handler(req):
        assert str(req.url) == PROJECT + '/auth/v1/user'
        assert req.headers['apikey'] == PUBLISHABLE
        verified = jwt.decode(req.headers['Authorization'][7:], HS_SECRET, algorithms=['HS256'], issuer=PROJECT + '/auth/v1', audience='authenticated')
        return httpx.Response(200, json={'id': verified['sub'], 'role': 'authenticated', 'email': 'never-returned@example.invalid'})
    legacy_service(monkeypatch, handler)
    assert request(client, token(keys, 'HS256')).json() == {'id': USER, 'role': 'authenticated'}


@pytest.mark.parametrize('changes', [{'iss': 'wrong'}, {'aud': 'wrong'}, {'exp': 1}, {'role': 'service_role'}, {'sub': OTHER}])
def test_legacy_still_enforces_local_claim_contract_after_auth_server_success(client, keys, monkeypatch, changes):
    legacy_service(monkeypatch, lambda req: httpx.Response(200, json={'id': USER, 'role': 'authenticated'}))
    assert request(client, token(keys, 'HS256', claims(**changes))).status_code == 401


def test_legacy_invalid_signature_rejected_by_auth_service(client, keys, monkeypatch):
    def handler(req):
        try:
            jwt.decode(req.headers['Authorization'][7:], HS_SECRET, algorithms=['HS256'], audience='authenticated')
        except jwt.PyJWTError:
            return httpx.Response(401, json={'message': 'invalid signature'})
        return httpx.Response(200, json={'id': USER, 'role': 'authenticated'})
    legacy_service(monkeypatch, handler)
    forged = jwt.encode(claims(), 'different-synthetic-secret-with-at-least-32-bytes', algorithm='HS256')
    assert request(client, forged).status_code == 401


@pytest.mark.parametrize('status,expected', [(401, 401), (403, 401), (302, 503), (429, 503), (500, 503)])
def test_legacy_auth_rejection_or_outage_never_falls_back(client, keys, monkeypatch, status, expected):
    legacy_service(monkeypatch, lambda req: httpx.Response(status, json={'id': USER, 'role': 'authenticated'}))
    assert request(client, token(keys, 'HS256')).status_code == expected


def test_legacy_transport_failure_fails_closed(client, keys, monkeypatch):
    def handler(req):
        raise httpx.ConnectError('synthetic offline condition')
    legacy_service(monkeypatch, handler)
    assert request(client, token(keys, 'HS256')).status_code == 503


@pytest.mark.parametrize('body,expected', [(None, 503), ([], 503), ({'id': OTHER, 'role': 'authenticated'}, 401), ({'id': USER, 'role': 'service_role'}, 401)])
def test_legacy_service_response_must_identify_the_same_authenticated_user(client, keys, monkeypatch, body, expected):
    legacy_service(monkeypatch, lambda req: httpx.Response(200, json=body))
    assert request(client, token(keys, 'HS256')).status_code == expected
