import {createServerClient} from '@supabase/ssr';
import {NextResponse, type NextRequest} from 'next/server';
import {authCookieOptions, supabaseConfig} from './config';

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({request});
  const config = supabaseConfig();
  if (!config) return response; // The existing public demo needs no Supabase.
  const refreshHeaders = new Headers();
  const supabase = createServerClient(config.url, config.publishableKey, {
    cookieOptions: authCookieOptions,
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({name, value}) => request.cookies.set(name, value));
        const previousCookies = response.cookies.getAll();
        response = NextResponse.next({request});
        previousCookies.forEach(cookie => response.cookies.set(cookie));
        cookiesToSet.forEach(({name, value, options}) => response.cookies.set(name, value, options));
        Object.entries(headers).forEach(([name, value]) => refreshHeaders.set(name, value));
        refreshHeaders.forEach((value, name) => response.headers.set(name, value));
      },
    },
  });
  // This verifies/refreshes the session. Public routes remain public in 3A.
  // It does not authorize marketplace ownership or create a demo identity.
  await supabase.auth.getClaims();
  if (!response.headers.has('Cache-Control')) response.headers.set('Cache-Control', 'private, no-store');
  const vary = response.headers.get('Vary');
  if (!vary?.toLowerCase().split(',').map(value => value.trim()).includes('cookie')) response.headers.set('Vary', vary ? `${vary}, Cookie` : 'Cookie');
  return response;
}
