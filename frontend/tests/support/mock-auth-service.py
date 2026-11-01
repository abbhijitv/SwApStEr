"""Local test double only. No Supabase project, email delivery, or real credentials.

Run with the project's virtual environment. Request logging is disabled because
Auth URLs and headers can carry synthetic credentials even in test runs.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import time
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4, uuid5, NAMESPACE_DNS

import jwt

SECRET = 'synthetic-auth-ui-signing-secret-for-local-tests-only'
PORT = int(sys.argv[1])
ORIGIN = f'http://localhost:{PORT}'
STATE = {}


def reset():
    STATE.update(users={'member@example.invalid': 'Correct-passphrase-123!'}, refresh={}, revoked=set(), expired=False, signup=None)


def user(email):
    return {'id': str(uuid5(NAMESPACE_DNS, email)), 'email': email, 'aud': 'authenticated', 'role': 'authenticated', 'is_anonymous': False,
            'email_confirmed_at': '2026-01-01T00:00:00Z', 'confirmed_at': '2026-01-01T00:00:00Z', 'created_at': '2026-01-01T00:00:00Z',
            'app_metadata': {'provider': 'email'}, 'user_metadata': {}, 'identities': []}


def session(email):
    now = int(time.time())
    access = jwt.encode({'iss': ORIGIN+'/auth/v1', 'aud': 'authenticated', 'role': 'authenticated', 'sub': user(email)['id'],
                         'email': email, 'iat': now-1, 'exp': now+3600, 'session_id': str(uuid4()), 'is_anonymous': False}, SECRET, algorithm='HS256')
    refresh = 'synthetic-refresh-'+uuid4().hex
    STATE['refresh'][refresh] = email
    return {'access_token': access, 'refresh_token': refresh, 'token_type': 'bearer', 'expires_in': 3600, 'user': user(email)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body=None):
        payload = json.dumps(body).encode() if body is not None else b''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('X-Supabase-Api-Version', '2024-01-01')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin', '*'))
        self.send_header('Access-Control-Allow-Headers', 'authorization, apikey, content-type, x-client-info, x-supabase-api-version')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,PUT,OPTIONS')
        self.send_header('Access-Control-Expose-Headers', 'X-Supabase-Api-Version')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def identity(self):
        value = self.headers.get('Authorization', '')
        if not value.startswith('Bearer ') or STATE['expired'] or value[7:] in STATE['revoked']:
            return None
        try:
            claims = jwt.decode(value[7:], SECRET, algorithms=['HS256'], issuer=ORIGIN+'/auth/v1', audience='authenticated')
            return claims['email']
        except (jwt.PyJWTError, KeyError):
            return None

    def do_OPTIONS(self):
        self.send(204)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.send(200, {'status': 'test-double'})
        if path == '/auth/v1/.well-known/jwks.json':
            return self.send(200, {'keys': []})
        if path == '/auth/v1/user':
            email = self.identity()
            return self.send(200, user(email)) if email else self.send(401, {'code': 'bad_jwt', 'message': 'Synthetic session expired'})
        self.send(404, {'code': 'not_found'})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or '{}')
        except ValueError:
            return self.send(400, {'code': 'bad_json'})
        if path == '/__reset':
            reset()
            return self.send(200, {})
        if path == '/__expire':
            STATE['expired'] = True
            return self.send(200, {})
        if self.headers.get('apikey') != 'sb_publishable_synthetic-only':
            return self.send(401, {'code': 'invalid_api_key'})
        if path == '/auth/v1/signup':
            email = body.get('email', '')
            STATE['users'][email] = body.get('password', '')
            STATE['signup'] = email
            if email == 'instant@example.invalid':
                return self.send(200, session(email))
            return self.send(200, {**user(email), 'email_confirmed_at': None, 'confirmed_at': None})
        if path == '/auth/v1/token':
            grant = parse_qs(urlsplit(self.path).query).get('grant_type', [''])[0]
            email = body.get('email', '')
            if grant == 'password':
                if email == 'unconfirmed@example.invalid':
                    return self.send(400, {'code': 'email_not_confirmed', 'msg': 'Email not confirmed'})
                if STATE['users'].get(email) != body.get('password'):
                    return self.send(400, {'code': 'invalid_credentials', 'msg': 'Invalid credentials'})
                return self.send(200, session(email))
            if grant == 'pkce':
                if body.get('auth_code') != 'valid-code' or not body.get('code_verifier'):
                    return self.send(400, {'code': 'otp_expired', 'msg': 'Expired code'})
                return self.send(200, session(STATE['signup'] or 'member@example.invalid'))
            if grant == 'refresh_token':
                email = STATE['refresh'].get(body.get('refresh_token'))
                if not email or STATE['expired']:
                    return self.send(400, {'code': 'refresh_token_not_found', 'msg': 'Expired session'})
                return self.send(200, session(email))
        if path == '/auth/v1/verify':
            if body.get('token_hash') not in {'confirm-valid', 'recovery-valid'}:
                return self.send(403, {'code': 'otp_expired', 'msg': 'Expired link'})
            return self.send(200, session(STATE['signup'] if body.get('type') == 'email' and STATE['signup'] else 'member@example.invalid'))
        if path in {'/auth/v1/recover', '/auth/v1/resend'}:
            return self.send(200, {})
        if path == '/auth/v1/logout':
            STATE['revoked'].add(self.headers.get('Authorization', '')[7:])
            return self.send(204)
        self.send(404, {'code': 'not_found'})

    def do_PUT(self):
        email = self.identity()
        if not email:
            return self.send(401, {'code': 'bad_jwt'})
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or '{}')
        STATE['users'][email] = body.get('password', STATE['users'][email])
        self.send(200, user(email))


reset()
ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
