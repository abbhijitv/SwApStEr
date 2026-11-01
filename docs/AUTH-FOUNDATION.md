# Supabase authentication foundation — Prompt 3A

Prompt 3B now adds account screens and email callbacks on top of this foundation;
see [account UI and manual Supabase testing](AUTH-UI.md). Prompt 3C-1 now adds
[staged account ownership and approval APIs](ACCOUNT-MARKETPLACE.md); frontend
integration remains Prompt 3C-2. The historical phase description below describes 3A.

This phase adds account-session plumbing and a separately authenticated FastAPI
`GET /auth/me`. It does not add signup/login pages, account provisioning, listing
ownership mapping, account negotiation access, approval changes, or deployment.
SQLite, PostgreSQL configuration, and existing record schemas are unchanged.

## Configuration

Existing root `.env` and `frontend/.env.local` are preserved. Configure these
manually for the same authorized Supabase project when ready:

```dotenv
# Root .env: FastAPI only
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
SUPABASE_AUTH_LEGACY_HS256=false
```

```dotenv
# frontend/.env.local: browser-safe settings only
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_PUBLIC_KEY
NEXT_PUBLIC_API_URL=http://localhost:8000
```

The backend intentionally requires its unprefixed settings; merely placing
`NEXT_PUBLIC_*` values in the root `.env` does not configure FastAPI authentication.
Use the Supabase **project HTTP URL**, not a PostgreSQL connection string. Modern
publishable keys are required; legacy anon JWT API keys, service-role keys, secret
API keys, and JWT signing secrets are not configuration inputs to this foundation.
No service-role/admin client or local signing secret is used.

URLs must be HTTPS project origins without credentials, paths, queries, or
fragments. Local HTTP Supabase origins are allowed only in development. Real
deployed account API URLs must use HTTPS; the transport helper rejects insecure
remote URLs. Public Next.js settings are bundled at build time, so restart/rebuild
after changing them. No live Supabase credentials are needed to run the tests.

If both frontend Supabase values are absent/empty, client factories return `null`
and the proxy passes public/demo routes through without network requests. Partial
or invalid configuration throws a generic configuration error rather than
creating an authenticated fallback. Backend missing bearer credentials return
401 with `WWW-Authenticate: Bearer`; requests supplying credentials when backend
configuration is absent/invalid return a generic 503. They never fall back to a
demo cookie, frontend user ID, or publishable API key.

## Next.js sessions

- `frontend/lib/supabase/browser.ts` creates the browser client with
  `@supabase/ssr`. It uses the SDK's cookie storage and PKCE session behavior.
- `frontend/lib/supabase/server.ts` creates a new client **per request** using
  Next.js 16's asynchronous `cookies()`. Server Actions and Route Handlers can
  persist cookie changes; Server Components cannot. `getVerifiedUser()` uses
  `auth.getUser()`, not a cookie/session user object, for a verified identity.
- `frontend/proxy.ts` and its reusable helper verify/refresh sessions through
  `auth.getClaims()`. They copy refreshed cookies to both the forwarded request
  and response and preserve SDK cache headers. Configured responses are private
  and non-cacheable and vary by Cookie. Public routes remain public: this phase
  adds no login redirects or page-access policy.
- SDK auth cookies are distinct from `campus_session`, scoped to `/`, SameSite
  Lax, and Secure in production. **They are JavaScript-readable**, as required
  by the Supabase browser client; this is not an HttpOnly BFF implementation.
  Future UI must retain XSS protection, avoid token logging, validate redirect
  destinations, and protect state-changing server actions appropriately.
- `frontend/lib/api/authenticated.ts` obtains an access token only for transport
  and calls `/auth/me` with `Authorization: Bearer <access_token>`, `cache:
  no-store`, and `credentials: omit`. `getSession()` is not used as proof of
  identity. FastAPI decides identity. This helper never calls demo endpoints or
  retries with a demo cookie when authentication fails.

These choices follow [Supabase's SSR client guidance](https://supabase.com/docs/guides/auth/server-side/creating-a-client)
and [its Next.js proxy example](https://github.com/supabase/supabase/blob/master/examples/auth/nextjs/lib/supabase/proxy.ts).
Future account responses and any Route Handler that sets session cookies must
also remain private/non-cacheable. Do not use ISR or shared CDN caching for
personalized responses.

## FastAPI identity verification

`backend.auth.authenticated_user` is the reusable dependency. It accepts only an
HTTP Bearer access token. It does not inspect demo cookies or accept user IDs,
roles, email addresses, JWT payloads, or API keys supplied as identity parameters.

For **ES256/RS256**, it obtains the signing key from the configured project's
`SUPABASE_URL/auth/v1/.well-known/jwks.json`. Algorithms are a fixed server-side
allowlist. A token's untrusted header is used only to select a key/verification
path; it never establishes identity. `kid` must be present, the JWK algorithm
must match, and signature verification must succeed. Token-provided `jku`, `jwk`,
`x5u`, and critical-header instructions are rejected, so tokens cannot redirect
key discovery. PyJWT performs cryptographic validation and issuer/audience/time
checks; the application also validates required claim types and identity.

For **legacy HS256**, set `SUPABASE_AUTH_LEGACY_HS256=true` explicitly only when
needed. The backend sends the **exact presented token** to the configured
project's authenticated `/auth/v1/user` endpoint, with its publishable key in
`apikey`. It accepts neither redirects nor non-200 responses. Only after this
trusted service has validated the token does it parse the now-authenticated
payload to enforce the local issuer/audience/time/role contract. The verified
subject must equal the UUID returned by Auth, whose role must also be
`authenticated`. There is no signature-disabled JWT decode or shared-secret
fallback. This follows Supabase's recommended Auth-server validation for
[legacy symmetric tokens](https://supabase.com/docs/guides/auth/jwts#verifying-a-jwt-from-supabase).

Both paths require the exact configured issuer ending in `/auth/v1`, audience
`authenticated` (or an audience array containing it), non-expired numeric `exp`,
non-future numeric `iat`, valid optional `nbf`, role `authenticated`, and a
canonical nonzero UUID subject. Anonymous-sign-in accounts are rejected in this
foundation. `anon` and `service_role` tokens are rejected. Missing/invalid tokens
produce generic 401 responses; configuration/upstream connectivity failures
produce generic 503 responses. Account responses/errors are non-cacheable.

`GET /auth/me` returns only:

```json
{"id": "verified-supabase-user-uuid", "role": "authenticated"}
```

It returns no access/refresh tokens, user metadata, email, demo profile, database
records, listing ownership, or private constraints. There is no new database
lookup or account table.

JWKS are cached for five minutes per worker; individual key caching is disabled
so keys cannot outlive that set. Refresh attempts use a 30-second cooldown, and
network operations have five-second timeouts. An unknown key may be rejected
during propagation/cooldown. Offline JWT verification does not establish that a
user is still active on every request, instantly revoke signed access tokens, or
guarantee immediate signing-key revocation across upstream caches. Plan rotation,
logout/revocation requirements, worker restarts/cache invalidation, request rate
limits, and monitoring before rollout. No tokens or raw upstream errors should
be logged. See [Supabase signing-key behavior](https://supabase.com/docs/guides/auth/signing-keys).

## Demo/account separation and rollout boundary

The existing marketplace still uses local demo profiles and `campus_session`.
Those profiles are **not** Supabase accounts. No mapping between a Supabase UUID
and a student/listing/negotiation/approval ID was introduced. Demo switching cannot
mint an access token, change `/auth/me`, or select another authenticated user.

Demo identity-protected routes and `/demo/session` switching explicitly reject
requests carrying an Authorization header, even if a demo cookie is present.
Normal cookie-only local demo requests retain their existing ownership and dual
approval rules. Public listing reads remain public.

When server-side Supabase settings are present and `APP_ENV` is not development,
demo endpoints are disabled even if legacy `PUBLIC_DEMO_MODE=true` is set. A
historical hosted demo without Supabase configuration retains its earlier
behavior; this prompt neither changes its deployment settings nor enables a
public account rollout. **Never deploy real account workflows with
`APP_ENV=development`. Existing demo listing/negotiation/approval endpoints are
not safe for real public accounts and must not be reused as account APIs.**

## Deferred to Prompt 3B / 3C

- **3B:** Signup/login/logout UI, verified callback/code exchange, email/password
  or OAuth flows, password reset, redirect allowlisting, account UX and protected
  navigation. Clients/proxy alone do not implement these workflows.
- **3C:** Durable authenticated profiles, explicit migration/mapping of ownership,
  account-scoped listing/negotiation/history APIs, authenticated independent
  approval authorization, cross-worker concurrency, and retirement/isolation of
  demo writes. Supabase RLS, database role/access configuration and public Data API
  exposure need review before storing private data remotely.

No migrations, live data copies, Supabase project/settings changes, production
deployments, public rollout, or authentication UI are performed by 3A.
The backend's existing CORS allowlist still permits `http://localhost:3000` only;
an authorized hosted frontend origin and Supabase redirect/site settings must be
configured and verified in the later rollout phase, not inferred from this work.

## Verification

```sh
.venv/bin/python -m pytest backend/tests -q
npm run typecheck --prefix frontend
npm run build --prefix frontend
npm run test:e2e --prefix frontend -- tests/supabase-foundation.spec.ts
```

Tests use generated signing keys and synthetic tokens with mocked official JWKS
and Auth responses; frontend tests exercise a real SDK cookie refresh against
mocked HTTP. No real Supabase login, session, JWKS response, or network integration
has been verified. Existing SQLite tests use a temporary database.

Recorded results: **225 backend tests passed**, including **75 authentication
tests** that also passed separately; **7 frontend foundation tests passed**;
TypeScript, the production build, and `pip check` passed. An isolated smoke test
on spare ports returned HTTP 200 for `/`, `/marketplace`, `/b2b`, and backend
health/docs/listings, and Chrome rendered live temporary listings and initialized
the demo session. The spare-port browser test used a test-only CORS bridge; the
unchanged backend CORS policy was checked against its supported localhost origin.
The full existing browser suite was not rerun because its fixed ports were
occupied by the developer's servers. Those servers were left running, and all
temporary smoke resources were cleaned up. Database and local configuration
checksums were unchanged. The backend's unprefixed Supabase settings still need
to be supplied locally before `/auth/me` can validate a real Supabase session.
