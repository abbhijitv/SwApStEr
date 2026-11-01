import 'server-only';

import {createServerClient} from '@supabase/ssr';
import {cookies} from 'next/headers';
import {authCookieOptions, supabaseConfig} from './config';

/** Create per request; never share a server client across users. */
export async function createClient() {
  const config = supabaseConfig();
  if (!config) return null;
  const cookieStore = await cookies();
  return createServerClient(config.url, config.publishableKey, {
    cookieOptions: authCookieOptions,
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({name, value, options}) => cookieStore.set(name, value, options));
        } catch {
          // Server Components cannot write cookies; proxy.ts persists refreshes.
          // Route Handlers / Server Actions can persist them through this adapter.
        }
      },
    },
  });
}

/** Authorization must use verified identity, never the getSession() user object. */
export async function getVerifiedUser() {
  const client = await createClient();
  if (!client) return null;
  const {data, error} = await client.auth.getUser();
  if (error || !data.user) return null;
  return data.user;
}
