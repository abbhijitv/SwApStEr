# Real signup, login, logout, and recovery — Prompt 3B

The account UI uses the Supabase clients and FastAPI verifier from Prompt 3A.
It does not map Supabase users to demo profiles or change listing, negotiation,
approval, SQLite, PostgreSQL, or migration behavior. Nothing is deployed by this
change. Existing demo APIs are still unsuitable for real public-account writes.

## Routes and behavior

| Route | Purpose |
| --- | --- |
| `/signup` | Email, password, confirmation, client validation, loading/error states, check-inbox result |
| `/login` | Password login, invalid/unconfirmed-email errors, resend confirmation, recovery/signup links |
| `/forgot-password` | Neutral recovery-email response that does not disclose whether an account exists |
| `/reset-password` | Requires a remotely verified account session; updates the password and logs out this browser |
| `/account` | Verified account email, account/demo boundary, optional FastAPI `/auth/me` connection check |
| `/auth/callback` | Server-side PKCE code exchange using the browser's verifier cookie |
| `/auth/confirm` | Server-side email/recovery token-hash verification, including cross-browser email flows |
| `/auth/error` | Generic expired/invalid-link or configuration guidance without echoing credentials |

Signup without an immediate session displays confirmation guidance; if the
project has confirmation disabled and Supabase returns a session, signup opens
the account page. This code does not change the project's confirmation policy.
Passwords are not trimmed or manually persisted. Signup/reset forms require 12
characters and matching confirmation; the Supabase server must independently
enforce the intended password policy. Login permits existing shorter passwords.

`AuthProvider` verifies the current account with `auth.getUser()` instead of
trusting the user object from cookie storage. It listens for session changes,
refreshes identity on focus/visibility changes, and clears rejected/expired
identities. Navigation shows the verified email (or account state) and logout.
Cookies persist the session across reloads through the existing SSR proxy. A
different account clears any previous `/auth/me` verification message.

Logout uses `signOut({scope: 'local'})`: it ends this browser's Supabase session,
not the independent local demo session or every other device. A successful
password update also attempts local logout. If that logout fails, the UI states
that the password was updated but the session could not be ended. An already
verified signed-in account may use `/reset-password` to change its own password;
the page is not a separate authorization mechanism. Invalid email links always
go to the error screen, even when another session is already present.

## Local configuration (preserved, never overwritten)

Use the same project values in `frontend/.env.local` as described in
[the foundation guide](AUTH-FOUNDATION.md):

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
NEXT_PUBLIC_API_URL=http://localhost:8000
```

To verify the separate FastAPI connection, also configure the root `.env`:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
SUPABASE_AUTH_LEGACY_HS256=false
```

Only enable the legacy flag if that project's user tokens use HS256. The browser
key is publishable, never a service-role or secret key. Frontend public settings
require a restart/rebuild after edits. Missing or invalid frontend settings show
an account-unavailable message and disable credential submissions while public
and demo pages remain usable; no authenticated fallback identity is created.
Backend failures do not turn a demo cookie into an account credential.

## Supabase settings and email templates: manual, development project only

No project settings, SMTP configuration, emails, or real accounts were changed
by the implementation or automated tests. Before manual testing, use an
authorized development project and review:

1. Enable email/password authentication and choose the intended email-confirmation
   policy. Configure a server-enforced password policy consistent with the UI.
2. Set the Auth **Site URL** to your intended development origin, for example
   `http://localhost:3000`. Add only the required callback URLs to the redirect
   allowlist, including `/auth/callback` and the recovery callback query
   `?next=/reset-password`. HTTPS is required for a future hosted account UI.
   Avoid broad production redirect wildcards. Follow
   [Supabase redirect configuration](https://supabase.com/docs/guides/auth/redirect-urls).
3. For reliable email confirmation across browsers/devices, use a Confirm signup
   template pointing to the server token-hash endpoint:

   ```html
   <a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=email">Confirm your email</a>
   ```

4. For password recovery, use the Reset password template:

   ```html
   <a href="{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&amp;type=recovery">Reset your password</a>
   ```

   These require a correctly configured Site URL. The app calls
   `verifyOtp({token_hash, type})` on the server and verifies the returned account
   before redirecting. This is the supported
   [Supabase password/email flow](https://supabase.com/docs/guides/auth/passwords).
5. If retaining the project's default PKCE email flow instead, signup/recovery
   supply a callback URL and the callback calls `exchangeCodeForSession`. Open
   the link in the browser that initiated it; another browser has no verifier
   cookie. The callback supports a valid optional `sb_flow_id` for scoped SDK
   verifiers, but does not enable experimental redirect flags automatically.
   Default concurrent PKCE attempts may fail if a different pending verifier is
   selected; request a fresh link or use the token-hash email templates. Consult
   [Supabase's email-template guidance](https://supabase.com/docs/guides/auth/auth-email-templates).
6. Verify SMTP delivery, spam handling, send limits, link expiration, resend, and
   email-security scanners with real development emails. Those services cannot
   be established by local mocks. This UI does not include a CAPTCHA widget; if
   the project requires CAPTCHA, add and verify that integration before enabling
   signup/recovery publicly.

Do not apply these instructions to an existing production project without a
separately authorized rollout. The existing CORS policy still accepts
`http://localhost:3000`; no production origins or deployment settings were added.

## Callback and session security

- Callback destinations are limited to `/account` and `/reset-password` and use
  relative Location headers. Absolute URLs, protocol-relative URLs, encoded
  targets, and Host/X-Forwarded-Host values cannot select an external redirect.
- Only email and recovery token-hash types are accepted. Missing, duplicate,
  mixed, unsupported, and failed callback credentials do not redirect to a
  success page. Supabase performs token/code verification; the app additionally
  calls `getUser()` and rejects anonymous accounts before success.
- Auth route responses use private/no-store headers and `Referrer-Policy:
  no-referrer`. Redirects strip codes/token hashes from the resulting URL. No
  passwords, access tokens, refresh tokens, or raw Auth errors are logged by the
  application. Framework/proxy access logs must redact callback query strings
  before live testing/rollout; single-use codes and token hashes are sensitive.
- Sessions remain in SDK-managed cookies, not manually written localStorage.
  Cookies are JavaScript-readable as required by the browser SDK, SameSite Lax,
  and Secure in production. XSS protection and appropriate CSP remain important.
- Account navigation is distinct from the **Demo profile** selector. Neither a
  login nor a demo-profile switch grants ownership of a listing or negotiation.
- `/account` checks identity through Supabase. Its API-check button sends only
  an access token to FastAPI `/auth/me` using the account-only transport, without
  the demo cookie. FastAPI independently verifies the subject; the frontend's
  comparison is a UI consistency check, never proof of authorization.

Offline JWT verification in the backend can continue to accept previously issued
access tokens until expiry. Local logout is not instantaneous revocation of
stolen tokens or all devices. Before public launch, review token lifetime,
revocation, abuse controls, TLS, CORS, callback allowlists, and private-data/RLS
exposure. Account ownership and approval authorization remain Prompt 3C work.

## Verification and tests

```sh
.venv/bin/python -m pytest backend/tests -q
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm run test:e2e --prefix frontend -- tests/auth-callback.spec.ts tests/supabase-foundation.spec.ts
```

`auth-callback.spec.ts` exercises the actual SDK and callback helper with mocked
HTTP, including code/token-hash verification, cookies, safe redirects, malformed
input, expiry and missing configuration. `auth-ui.spec.ts` is opt-in and requires
the isolated local Auth test double, never a real project. The local service in
`tests/support/mock-auth-service.py` uses synthetic in-memory users, signing keys,
passwords, and sessions, disables request logs, and sends no email. It is test
infrastructure and must never be exposed publicly.

Browser testing uses temporary frontend copies and a temporary SQLite database on
spare ports, preserving the developer's running servers. The real FastAPI
`/auth/me` dependency validates synthetic HS256 sessions through the test Auth
service. A test-only CORS bridge supports those spare browser ports; production
CORS remains unchanged. The UI tests cover validation, both confirmation policies,
busy states, login, logout, session persistence/expiry, recovery/reset, resend,
PKCE callbacks, account changes, mobile navigation, missing configuration, and
account/demo separation. Real SMTP, project policies, remote signing-key behavior,
and real email links still require manual Supabase testing.

Recorded local results: **225 backend tests passed**; **38 relevant frontend
authentication tests passed** (17 callback cases, 14 browser UI cases, and the
7 existing foundation tests), with no failures or skips. TypeScript and the
Next.js production build passed, including all new account routes. No real
Supabase users or emails were created. Both local environment files and the
existing database were byte-for-byte unchanged, and all temporary test resources
were cleaned up. Existing developer servers on ports 3000/8000 were preserved.
