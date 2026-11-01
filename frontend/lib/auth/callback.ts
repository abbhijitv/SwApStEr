import {createServerClient} from '@supabase/ssr';
import {NextRequest, NextResponse} from 'next/server';
import {supabaseConfig, authCookieOptions} from '../supabase/config';
import {safeAuthDestination} from './flow';

export async function completeAuth(request: NextRequest, flow: 'code' | 'token') {
  // Relative Location prevents Host/X-Forwarded-Host from becoming a redirect origin.
  const response = new NextResponse(null, {status: 303, headers: {'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer', 'Location': '/auth/error?reason=invalid-link'}});
  let config;
  try {config = supabaseConfig();} catch {config = null;}
  if (!config) {response.headers.set('Location', '/auth/error?reason=configuration'); return response;}
  const params = request.nextUrl.searchParams;
  const name = flow === 'code' ? 'code' : 'token_hash';
  const value = params.get(name);
  const type = params.get('type');
  const flowId = params.get('sb_flow_id');
  if (!value || value.length > 2048 || params.getAll(name).length !== 1 || params.has('error') || params.has(flow === 'code' ? 'token_hash' : 'code') || (flow === 'token' && (params.getAll('type').length !== 1 || (type !== 'email' && type !== 'recovery'))) || (flow === 'code' && params.has('sb_flow_id') && (params.getAll('sb_flow_id').length !== 1 || !flowId || !/^[a-zA-Z0-9_-]{8,64}$/.test(flowId)))) return response;
  const client = createServerClient(config.url, config.publishableKey, {
    cookieOptions: authCookieOptions,
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(values, headers) {
        values.forEach(({name, value, options}) => {request.cookies.set(name, value); response.cookies.set(name, value, options);});
        Object.entries(headers).forEach(([key, value]) => response.headers.set(key, value));
      },
    },
  });
  try {
    const {error} = flow === 'code' ? await client.auth.exchangeCodeForSession(value, flowId ? {flowId} : undefined) : await client.auth.verifyOtp({token_hash: value, type: type as 'email' | 'recovery'});
    if (error) return response;
    const {data, error: invalid} = await client.auth.getUser();
    if (invalid || !data.user || data.user.is_anonymous) {await client.auth.signOut({scope: 'local'}); return response;}
    response.headers.set('Location', type === 'recovery' ? '/reset-password' : safeAuthDestination(params.get('next')));
  } catch {
    // No raw Auth errors, tokens, or user-controlled redirect parameters in the response.
  }
  return response;
}
