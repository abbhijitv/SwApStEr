'use client';

import Link from 'next/link';
import {useRouter, useSearchParams} from 'next/navigation';
import {FormEvent, Suspense, useEffect, useRef, useState} from 'react';
import {ArrowRight, CheckCircle2, LockKeyhole, ShoppingBag, Sparkles} from 'lucide-react';
import {useAuth} from './auth-provider';
import {AccountNav} from './account-nav';
import {authErrorMessage, safeAuthDestination} from '../../lib/auth/flow';
import {getAccountUser} from '../../lib/api/authenticated';

type Mode = 'signup' | 'login' | 'forgot' | 'reset' | 'account' | 'error';
const titles: Record<Mode, string> = {signup: 'Your next great deal starts here.', login: 'Welcome back.', forgot: 'Forgot your password?', reset: 'Choose a new password.', account: 'Your SwApStEr account.', error: 'Let’s get you back on track.'};
const descriptions: Record<Mode, string> = {signup: 'Create an account with your email. You stay in control.', login: 'Log in to manage your account.', forgot: 'We’ll send a secure link to help you get back in.', reset: 'Make it unique. A longer passphrase is a great choice.', account: 'Manage your session and check your secure API connection.', error: 'Authentication links can expire or be used only once.'};

export function AuthScreen({mode}: {mode: Mode}) {
  return <div className="auth-page">
    <header className="auth-header"><Link className="brand" href="/"><span className="brand-icon"><ShoppingBag size={21}/></span>SwApStEr</Link><AccountNav/></header>
    <main className="auth-layout"><aside className="auth-intro"><div className="eyebrow"><Sparkles size={15}/> YOUR ACCOUNT. YOUR CHOICE.</div><h1>Good finds.<br/>Better connections.</h1><p>A simpler way to buy, sell, and rent, with AI that works within your limits.</p><div className="auth-promise"><LockKeyhole size={20}/><span>Your credentials stay with Supabase Auth. You decide when to make a deal.</span></div><Link href="/marketplace">Explore the local demo <ArrowRight size={16}/></Link></aside>
      <section className="auth-card" aria-label={titles[mode]}><h2>{titles[mode]}</h2><p className="auth-description">{descriptions[mode]}</p><Suspense fallback={<p role="status">Loading account…</p>}><AuthContent mode={mode}/></Suspense></section>
    </main><footer className="auth-footer">SwApStEr · Your terms. Your final say.</footer>
  </div>;
}

function AuthContent({mode}: {mode: Mode}) {
  const {client, user, loading, configured, refresh, logout} = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [complete, setComplete] = useState(false);
  const [apiState, setApiState] = useState('');
  const apiGeneration = useRef(0);
  useEffect(() => {apiGeneration.current++; setApiState(''); if (mode === 'account') setBusy(false);}, [user?.id, mode]);
  const unavailable = !loading && !configured;
  const reason = params.get('reason');
  const notice = params.get('notice');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const email = String(data.get('email') || '').trim();
    const password = String(data.get('password') || '');
    setError(''); setMessage('');
    if ((mode === 'signup' || mode === 'reset') && password !== data.get('confirm')) {setError('Passwords do not match. Please enter the same password twice.'); form.querySelector<HTMLInputElement>('[name=confirm]')?.focus(); return;}
    setBusy(true);
    try {
      if (mode === 'signup') {
        const {data: result, error: failure} = await client.auth.signUp({email, password, options: {emailRedirectTo: `${window.location.origin}/auth/callback`}});
        if (failure && failure.code !== 'user_already_exists') {setError(authErrorMessage(failure, 'create your account')); return;}
        form.reset();
        if (result.session) {await refresh(); router.replace('/account'); router.refresh();}
        else {setComplete(true); setMessage('Check your inbox for a confirmation link. If you already have an account, log in or reset your password.');}
      } else if (mode === 'login') {
        const {error: failure} = await client.auth.signInWithPassword({email, password});
        if (failure) {setError(authErrorMessage(failure)); return;}
        form.reset(); await refresh(); router.replace(safeAuthDestination(params.get('next'))); router.refresh();
      } else if (mode === 'forgot') {
        const {error: failure} = await client.auth.resetPasswordForEmail(email, {redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`});
        if (failure && failure.code !== 'user_not_found') {setError(authErrorMessage(failure, 'send a recovery link')); return;}
        form.reset(); setComplete(true); setMessage('If an account exists for that address, a recovery link is on its way. Check your inbox and spam folder.');
      } else if (mode === 'reset') {
        const {data: verified, error: invalid} = await client.auth.getUser();
        if (invalid || !verified.user || verified.user.is_anonymous) {setError('Your recovery session has expired. Request a new recovery link.'); return;}
        const {error: failure} = await client.auth.updateUser({password});
        if (failure) {setError(authErrorMessage(failure, 'update your password')); return;}
        form.reset();
        try {await logout(); router.replace('/login?notice=password-updated'); router.refresh();}
        catch {setComplete(true); setMessage('Your password was updated. We could not end this session; use Log out when your connection is restored.');}
      }
    } catch {setError('We could not connect to account authentication. Please try again.');}
    finally {setBusy(false);}
  }

  async function resendConfirmation() {
    const field = document.querySelector<HTMLInputElement>('#auth-email');
    if (!client || !field?.reportValidity()) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const {error: failure} = await client.auth.resend({type: 'signup', email: field.value.trim(), options: {emailRedirectTo: `${window.location.origin}/auth/callback`}});
      if (failure) setError(authErrorMessage(failure, 'send a confirmation link'));
      else setMessage('If confirmation is needed for that address, a new link is on its way.');
    } catch {setError('We could not send a confirmation link. Please try again.');}
    finally {setBusy(false);}
  }

  if (loading) return <p className="auth-loading" role="status">Checking your session…</p>;
  if (mode === 'error') return <><div className="auth-alert" role="alert">{reason === 'configuration' ? 'Account authentication is not configured. You can still browse the local demo.' : 'This authentication link is invalid, expired, or already used. Request a new link and try again.'}</div><div className="auth-links"><Link href="/login">Back to login</Link><Link href="/forgot-password">Request a recovery link</Link></div></>;
  if (mode === 'account') return <>
    {unavailable ? <ConfigurationNotice/> : !user ? <><div className="auth-alert" role="status">Your session has ended, or you are not logged in.</div><Link className="primary full" href="/login?next=/account">Log in to your account <ArrowRight size={16}/></Link></> : <>
      <div className="auth-account"><CheckCircle2 size={24}/><div><strong>Signed in</strong><p>{user.email || 'Authenticated account'}</p></div></div>
      <p className="auth-boundary">Your real account is not yet connected to marketplace listings or negotiations. The local marketplace still uses separate demo profiles.</p>
      <button className="secondary full" disabled={busy} onClick={async () => {if (!client) return; const current = ++apiGeneration.current; setBusy(true); setApiState('Checking the secure API…'); try {const verified = await getAccountUser(client); if (apiGeneration.current === current) setApiState(verified.id === user.id ? 'Secure API verified your account.' : 'The API identity does not match this session. Please log out and try again.');} catch (failure) {if (apiGeneration.current === current) setApiState((failure as Error).message);} finally {if (apiGeneration.current === current) setBusy(false);}}}>Check secure API connection</button>
      {apiState && <p className="auth-feedback" role="status">{apiState}</p>}
    </>}
    <Link className="auth-demo-link" href="/marketplace">Continue to the separate local demo <ArrowRight size={15}/></Link>
  </>;
  if (mode === 'reset' && !user && !unavailable) return <><div className="auth-alert" role="alert">Your recovery session is missing or expired. Request a new recovery link.</div><Link className="primary full" href="/forgot-password">Request a recovery link</Link></>;
  return <>
    {unavailable && <ConfigurationNotice/>}
    {notice === 'signed-out' && <p className="auth-success" role="status">You have been logged out of this browser.</p>}
    {notice === 'password-updated' && <p className="auth-success" role="status">Your password has been updated. Log in with your new password.</p>}
    {user && (mode === 'login' || mode === 'signup') && <p className="auth-feedback">Already signed in as {user.email || 'an account'}. <Link href="/account">View your account</Link>.</p>}
    {message && <p className="auth-success" role="status">{message}</p>}
    {error && <p className="auth-alert" role="alert">{error}</p>}
    {!complete && <form className="auth-form" onSubmit={submit} aria-busy={busy}>
      {mode !== 'reset' && <label htmlFor="auth-email">Email address<input id="auth-email" name="email" type="email" autoComplete="email" required maxLength={254} disabled={busy || unavailable}/></label>}
      {mode !== 'forgot' && <label htmlFor="auth-password">{mode === 'reset' ? 'New password' : 'Password'}<input id="auth-password" name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'login' ? 1 : 12} maxLength={mode === 'login' ? undefined : 128} aria-describedby={mode === 'login' ? undefined : 'password-guidance'} disabled={busy || unavailable}/></label>}
      {(mode === 'signup' || mode === 'reset') && <><p className="auth-hint" id="password-guidance">Use at least 12 characters. Choose a unique passphrase.</p><label htmlFor="auth-confirm">Confirm password<input id="auth-confirm" name="confirm" type="password" autoComplete="new-password" required minLength={12} maxLength={128} disabled={busy || unavailable}/></label></>}
      <button className="primary full" disabled={busy || unavailable}>{busy ? 'Please wait…' : mode === 'signup' ? 'Create account' : mode === 'login' ? 'Log in' : mode === 'forgot' ? 'Send recovery link' : 'Update password'}<ArrowRight size={16}/></button>
    </form>}
    <div className="auth-links">{mode === 'login' ? <><Link href="/signup">Create an account</Link><Link href="/forgot-password">Forgot password?</Link><button type="button" disabled={busy || unavailable} onClick={resendConfirmation}>Resend confirmation email</button></> : <Link href="/login">Back to login</Link>}</div>
    <p className="auth-hint auth-separation">Account sign-in does not switch your local demo identity.</p>
  </>;
}

function ConfigurationNotice() {
  return <p className="auth-alert" role="alert">Account authentication is unavailable or not configured. You can still use the local demo. A developer must configure the public Supabase project URL and publishable key.</p>;
}
