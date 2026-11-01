import type {SupabaseClient} from '@supabase/supabase-js';

export type AccountUser = {id: string; role: 'authenticated'};

/** Account-only transport. Never use this helper against the demo API. */
export async function getAccountUser(client: SupabaseClient): Promise<AccountUser> {
  // getSession supplies a transport token, not a trusted identity decision.
  const {data, error} = await client.auth.getSession();
  if (error || !data.session?.access_token) throw new Error('Sign in to continue.');
  const base = new URL(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');
  const local = process.env.NODE_ENV !== 'production' && ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname);
  if ((base.protocol !== 'https:' && !(local && base.protocol === 'http:')) || base.username || base.password || base.search || base.hash) throw new Error('Configure a secure account API URL.');
  const response = await fetch(`${base.toString().replace(/\/$/, '')}/auth/me`, {
    headers: {Authorization: `Bearer ${data.session.access_token}`},
    credentials: 'omit', // Never mix the campus_session cookie into account auth.
    cache: 'no-store',
  });
  if (!response.ok) throw new Error(response.status === 401 ? 'Your session is invalid or expired.' : 'Account authentication is unavailable.');
  return response.json();
}
