'use client';

import {createContext, useCallback, useContext, useEffect, useRef, useState} from 'react';
import type {SupabaseClient, User} from '@supabase/supabase-js';
import {createClient} from '../../lib/supabase/browser';

type AuthState = {client: SupabaseClient | null; user: User | null; loading: boolean; configured: boolean; refresh: () => Promise<void>; logout: () => Promise<void>};
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({children}: {children: React.ReactNode}) {
  const [client, setClient] = useState<SupabaseClient | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    if (!client) return;
    const current = ++generation.current;
    try {
      const {data, error} = await client.auth.getUser();
      if (generation.current === current) setUser(error || data.user?.is_anonymous ? null : data.user);
    } catch {
      if (generation.current === current) setUser(null);
    } finally {
      if (generation.current === current) setLoading(false);
    }
  }, [client]);
  useEffect(() => {
    try {const value = createClient(); setClient(value); if (!value) setLoading(false);}
    catch {setLoading(false);}
  }, []);
  useEffect(() => {
    if (!client) return;
    void refresh();
    const {data: {subscription}} = client.auth.onAuthStateChange(event => {
      if (event === 'SIGNED_OUT') {generation.current++; setUser(null); setLoading(false);}
      else queueMicrotask(() => {void refresh();}); // Avoid awaiting SDK calls inside its auth lock.
    });
    const check = () => {if (!document.hidden) void refresh();};
    window.addEventListener('focus', check);
    document.addEventListener('visibilitychange', check);
    return () => {generation.current++; subscription.unsubscribe(); window.removeEventListener('focus', check); document.removeEventListener('visibilitychange', check);};
  }, [client, refresh]);
  const logout = useCallback(async () => {
    if (!client) throw new Error('Account authentication is unavailable.');
    const {error} = await client.auth.signOut({scope: 'local'});
    if (error) throw new Error('We could not log out. Check your connection and try again.');
    generation.current++; setUser(null); setLoading(false);
  }, [client]);
  return <AuthContext.Provider value={{client, user, loading, configured: !!client, refresh, logout}}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('Account components require AuthProvider.');
  return value;
}
