'use client';

import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useState} from 'react';
import {useAuth} from './auth-provider';

export function AccountNav() {
  const {user, loading, logout} = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function signOut() {
    setBusy(true); setError('');
    try {await logout(); router.replace('/login?notice=signed-out'); router.refresh();}
    catch {setError('Logout failed. Please try again.');}
    finally {setBusy(false);}
  }
  return <nav className="account-nav" aria-label="Account navigation">
    <Link href="/marketplace/account">Real marketplace</Link>
    {loading ? <span className="account-checking" role="status">Checking account…</span> : user ? <>
      <Link className="account-email" href="/account" title={user.email || 'Your account'}>{user.email || 'Your account'}</Link>
      <button className="account-logout" disabled={busy} onClick={signOut}>{busy ? 'Logging out…' : 'Log out'}</button>
    </> : <><Link href="/login">Log in</Link><Link className="account-signup" href="/signup">Sign up</Link></>}
    {error && <span className="account-nav-error" role="alert">{error}</span>}
  </nav>;
}
