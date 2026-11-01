import {test, expect} from '@playwright/test';
import {NextRequest} from 'next/server';
import {createHmac} from 'node:crypto';
import {completeAuth} from '../lib/auth/callback';
import {safeAuthDestination} from '../lib/auth/flow';
import {updateSession} from '../lib/supabase/proxy';

const project = 'https://auth-test.example.invalid';
const id = '1c8d6d81-b94a-49f8-b381-58f98349bf7b';
const user = {id, email: 'account@example.invalid', aud: 'authenticated', role: 'authenticated'};
let saved: Record<string, string | undefined>;
let originalFetch: typeof fetch;
test.beforeEach(() => {
  saved = {url: process.env.NEXT_PUBLIC_SUPABASE_URL, key: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY};
  process.env.NEXT_PUBLIC_SUPABASE_URL = project;
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_synthetic-only';
  originalFetch = global.fetch;
  global.fetch = async () => {throw new Error('Unexpected network request');};
});
test.afterEach(() => {
  for (const [key, value] of Object.entries({NEXT_PUBLIC_SUPABASE_URL: saved.url, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: saved.key})) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  global.fetch = originalFetch;
});

function session() {
  const now = Math.floor(Date.now()/1000);
  const header = Buffer.from(JSON.stringify({alg: 'HS256', typ: 'JWT'})).toString('base64url');
  const payload = Buffer.from(JSON.stringify({iss: project+'/auth/v1', sub: id, aud: 'authenticated', role: 'authenticated', exp: now+3600, iat: now-1})).toString('base64url');
  const jwt = `${header}.${payload}.${createHmac('sha256', 'synthetic-only-test-secret').update(`${header}.${payload}`).digest('base64url')}`;
  return {access_token: jwt, refresh_token: 'synthetic-refresh-secret', token_type: 'bearer', expires_in: 3600, user};
}

function mockAuth(valid = true) {
  global.fetch = async input => {
    const url = String(input);
    if (url === project+'/auth/v1/verify' || url === project+'/auth/v1/token?grant_type=pkce') return valid ? Response.json(session()) : Response.json({code: 'otp_expired', msg: 'synthetic-expired'}, {status: 403});
    if (url === project+'/auth/v1/user') return Response.json(user);
    if (url.startsWith(project+'/auth/v1/logout')) return new Response(null, {status: 204});
    throw new Error('Unexpected Auth URL');
  };
}

for (const value of ['https://attacker.invalid', '//attacker.invalid', '/\\attacker.invalid', '%2F%2Fattacker.invalid', '/account?next=https://attacker.invalid', '/marketplace', null]) {
  test(`return target is confined to the account flow: ${value}`, () => {expect(safeAuthDestination(value)).toBe('/account');});
}

test('email confirmation sets session cookies, strips link credentials, and rejects an external return target', async () => {
  mockAuth();
  const response = await completeAuth(new NextRequest('https://app.example.invalid/auth/confirm?token_hash=synthetic-token-hash&type=email&next=https://attacker.invalid'), 'token');
  expect(response.status).toBe(303);
  expect(response.headers.get('location')).toBe('/account');
  expect(response.cookies.getAll().some(cookie => cookie.name.startsWith('sb-auth-test-auth-token'))).toBeTruthy();
  expect(await response.text()).toBe('');
  expect(response.headers.get('referrer-policy')).toBe('no-referrer');
  expect(response.headers.get('cache-control')).toContain('no-store');
});

test('recovery token hash selects only the reset screen', async () => {
  mockAuth();
  const response = await completeAuth(new NextRequest('https://app.example.invalid/auth/confirm?token_hash=synthetic&type=recovery&next=//attacker.invalid'), 'token');
  expect(response.headers.get('location')).toBe('/reset-password');
});

test('PKCE callback exchanges a code using its verifier cookie and returns a relative redirect', async () => {
  mockAuth();
  const verifier = 'base64-'+Buffer.from(JSON.stringify('synthetic-verifier')).toString('base64url');
  const response = await completeAuth(new NextRequest('https://app.example.invalid/auth/callback?code=synthetic-code&next=/reset-password&sb_flow_id=synthetic-flow', {headers: {cookie: `sb-auth-test-auth-token-flow-synthetic-flow-code-verifier=${verifier}`, 'x-forwarded-host': 'attacker.invalid'}}), 'code');
  expect(response.headers.get('location')).toBe('/reset-password');
  expect(response.cookies.getAll().some(cookie => cookie.name === 'sb-auth-test-auth-token' && !!cookie.value)).toBeTruthy();
});

for (const query of ['', '?token_hash=synthetic&type=invite', '?token_hash=one&token_hash=two&type=email', '?token_hash=synthetic&type=email&code=mixed', '?token_hash=synthetic&type=email&error=bad']) {
  test(`malformed or unsupported confirmation stays closed: ${query}`, async () => {
    const response = await completeAuth(new NextRequest('https://app.example.invalid/auth/confirm'+query), 'token');
    expect(response.headers.get('location')).toBe('/auth/error?reason=invalid-link');
    expect(response.cookies.getAll()).toEqual([]);
  });
}

test('expired link returns a generic error without echoing tokens or upstream details', async () => {
  mockAuth(false);
  const response = await completeAuth(new NextRequest('https://app.example.invalid/auth/confirm?token_hash=synthetic-secret&type=recovery'), 'token');
  expect(response.headers.get('location')).toBe('/auth/error?reason=invalid-link');
  expect(await response.text()).toBe('');
});

test('missing config gives a safe callback error and invalid config leaves public pages usable', async () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = '';
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = '';
  expect((await completeAuth(new NextRequest('https://app.example.invalid/auth/callback?code=synthetic'), 'code')).headers.get('location')).toBe('/auth/error?reason=configuration');
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://auth-test.example.invalid';
  const response = await updateSession(new NextRequest('https://app.example.invalid/login'));
  expect(response.headers.get('x-middleware-next')).toBe('1');
  expect(response.cookies.getAll()).toEqual([]);
  expect(response.headers.get('cache-control')).toContain('no-store');
});
