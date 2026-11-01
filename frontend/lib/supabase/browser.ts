'use client';

import {createBrowserClient} from '@supabase/ssr';
import {authCookieOptions, supabaseConfig} from './config';

export function createClient() {
  const config = supabaseConfig();
  if (!config) return null;
  return createBrowserClient(config.url, config.publishableKey, {cookieOptions: authCookieOptions});
}
