/** Public project settings only. Never add service-role keys or JWT secrets here. */
export function supabaseConfig() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url && !publishableKey) return null;
  try {
    const parsed = new URL(url || '');
    const local = process.env.NODE_ENV === 'development' && ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname);
    if ((!local && parsed.protocol !== 'https:') || !['http:', 'https:'].includes(parsed.protocol)
      || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/'
      || !publishableKey?.startsWith('sb_publishable_') || /\s/.test(publishableKey)) throw new Error();
    return {url: parsed.origin, publishableKey};
  } catch {
    throw new Error('Supabase authentication configuration is invalid. Supply a project URL and publishable key.');
  }
}

export const authCookieOptions = {
  path: '/',
  sameSite: 'lax' as const,
  secure: process.env.NODE_ENV === 'production',
};
