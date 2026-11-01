import {test, expect} from '@playwright/test';
import {NextRequest} from 'next/server';
import {generateKeyPairSync, sign} from 'node:crypto';
import type {SupabaseClient} from '@supabase/supabase-js';
import {supabaseConfig} from '../lib/supabase/config';
import {createClient} from '../lib/supabase/browser';
import {updateSession} from '../lib/supabase/proxy';
import {getAccountUser} from '../lib/api/authenticated';

const envKeys = ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', 'NEXT_PUBLIC_API_URL'] as const;
let saved: Record<string, string | undefined>;
let originalFetch: typeof fetch;
test.beforeEach(() => {
  saved = Object.fromEntries(envKeys.map(key => [key, process.env[key]]));
  envKeys.forEach(key => delete process.env[key]);
  originalFetch = global.fetch;
  global.fetch = async () => {throw new Error('Unexpected network request');};
});
test.afterEach(() => {
  for (const key of envKeys) {
    if (saved[key] === undefined) delete process.env[key];
    else process.env[key] = saved[key];
  }
  global.fetch = originalFetch;
});

test('unconfigured browser client and proxy preserve the public demo without network', async () => {
  expect(supabaseConfig()).toBeNull();
  expect(createClient()).toBeNull();
  const response = await updateSession(new NextRequest('http://localhost:3000/marketplace', {headers: {cookie: 'campus_session=synthetic-demo-token'}}));
  expect(response.headers.get('x-middleware-next')).toBe('1');
  expect(response.headers.get('location')).toBeNull();
  expect(response.cookies.getAll()).toEqual([]);
});

test('partial configuration and privileged API keys fail closed without exposing their values', () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://auth-test.example.invalid';
  expect(() => createClient()).toThrow('configuration is invalid');
  for (const key of ['sb_secret_synthetic-only', 'legacy-service-role-jwt', '']) {
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = key;
    expect(() => supabaseConfig()).toThrow('configuration is invalid');
  }
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_synthetic-only';
  for (const url of ['http://external.example.invalid', 'https://user:password@example.invalid', 'https://example.invalid/path', 'https://example.invalid?query=1']) {
    process.env.NEXT_PUBLIC_SUPABASE_URL = url;
    expect(() => supabaseConfig()).toThrow('configuration is invalid');
  }
});

test('configured anonymous public request does not redirect to an unimplemented login page', async () => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://auth-test.example.invalid';
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_synthetic-only';
  const response = await updateSession(new NextRequest('http://localhost:3000/b2b'));
  expect(response.headers.get('x-middleware-next')).toBe('1');
  expect(response.headers.get('cache-control')).toBe('private, no-store');
  expect(response.headers.get('location')).toBeNull();
});

test('SSR proxy refreshes expired cookies and preserves SDK response headers', async () => {
  const project = 'https://auth-test.example.invalid';
  const user = {id: '1c8d6d81-b94a-49f8-b381-58f98349bf7b', aud: 'authenticated', role: 'authenticated'};
  process.env.NEXT_PUBLIC_SUPABASE_URL = project;
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_synthetic-only';
  const {privateKey, publicKey} = generateKeyPairSync('ec', {namedCurve: 'prime256v1'});
  const makeToken = (expires: number) => {
    const header = Buffer.from(JSON.stringify({alg: 'ES256', typ: 'JWT', kid: 'test-key'})).toString('base64url');
    const payload = Buffer.from(JSON.stringify({iss: project + '/auth/v1', sub: user.id, aud: 'authenticated', role: 'authenticated', iat: Math.floor(Date.now()/1000)-60, exp: expires})).toString('base64url');
    return `${header}.${payload}.${sign('sha256', Buffer.from(`${header}.${payload}`), {key: privateKey, dsaEncoding: 'ieee-p1363'}).toString('base64url')}`;
  };
  const now = Math.floor(Date.now()/1000);
  const refreshed = makeToken(now + 3600);
  const session = {access_token: makeToken(now - 60), refresh_token: 'synthetic-refresh', token_type: 'bearer', expires_at: now-60, expires_in: 3600, user};
  const cookieName = 'sb-auth-test-auth-token';
  const oldCookie = 'base64-' + Buffer.from(JSON.stringify(session)).toString('base64url');
  const calls: string[] = [];
  global.fetch = async (input) => {
    const url = String(input);
    calls.push(url);
    if (url === project + '/auth/v1/token?grant_type=refresh_token') return Response.json({access_token: refreshed, refresh_token: 'new-synthetic-refresh', token_type: 'bearer', expires_in: 3600, user});
    if (url === project + '/auth/v1/.well-known/jwks.json') return Response.json({keys: [{...publicKey.export({format: 'jwk'}), kid: 'test-key', alg: 'ES256', use: 'sig'}]});
    throw new Error('Unexpected Auth URL');
  };
  const response = await updateSession(new NextRequest('http://localhost:3000/marketplace', {headers: {cookie: `${cookieName}=${oldCookie}; campus_session=synthetic-demo-token`}}));
  expect(calls).toContain(project + '/auth/v1/token?grant_type=refresh_token');
  expect(response.cookies.getAll().some(cookie => cookie.name.startsWith(cookieName) && cookie.value !== oldCookie)).toBeTruthy();
  expect(response.cookies.getAll().some(cookie => cookie.name === 'campus_session')).toBeFalsy();
  expect(response.headers.get('x-middleware-request-cookie')).toContain('campus_session=synthetic-demo-token');
  expect(response.headers.get('cache-control')).toContain('private');
  expect(response.headers.get('cache-control')).toContain('no-store');
  expect(response.headers.get('pragma')).toBe('no-cache');
  expect(response.headers.get('expires')).toBe('0');
  expect(response.headers.get('vary')).toBe('Cookie');
});

function transportClient(accessToken?: string) {
  return {auth: {getSession: async () => ({data: {session: accessToken ? {access_token: accessToken} : null}, error: null})}} as unknown as SupabaseClient;
}

test('account API transports a token without demo credentials or a frontend user ID', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'https://api.example.invalid';
  let calls = 0;
  global.fetch = async (input, init) => {
    calls++;
    expect(String(input)).toBe('https://api.example.invalid/auth/me');
    expect(init?.credentials).toBe('omit');
    expect(init?.cache).toBe('no-store');
    expect(Object.fromEntries(new Headers(init?.headers))).toEqual({authorization: 'Bearer synthetic-access-token'});
    return Response.json({id: 'verified-by-backend', role: 'authenticated'});
  };
  expect(await getAccountUser(transportClient('synthetic-access-token'))).toEqual({id: 'verified-by-backend', role: 'authenticated'});
  expect(calls).toBe(1);
});

test('missing or rejected account sessions never fall back to demo identity', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'https://api.example.invalid';
  await expect(getAccountUser(transportClient())).rejects.toThrow('Sign in');
  let calls = 0;
  global.fetch = async () => {calls++; return new Response(null, {status: 401});};
  await expect(getAccountUser(transportClient('invalid-token'))).rejects.toThrow('invalid or expired');
  expect(calls).toBe(1);
});

test('account bearer tokens are never sent to an insecure remote API', async () => {
  process.env.NEXT_PUBLIC_API_URL = 'http://api.example.invalid';
  await expect(getAccountUser(transportClient('synthetic-access-token'))).rejects.toThrow('secure account API URL');
});
