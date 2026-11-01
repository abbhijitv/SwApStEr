import {test, expect, type Page} from '@playwright/test';

test.skip(!process.env.AUTH_TEST_SERVICE_URL, 'Run with the isolated local Auth test double; never against a real Supabase project.');
const service = process.env.AUTH_TEST_SERVICE_URL || 'http://localhost:55421';
const email = 'member@example.invalid';
const password = 'Correct-passphrase-123!';

test.beforeEach(async ({page, request}) => {
  await request.post(service+'/__reset');
  // Test-only bridge for the spare frontend port; production CORS is unchanged.
  await page.route('http://localhost:8101/**', async route => {
    const origin = route.request().headers()['origin'] || new URL(process.env.PLAYWRIGHT_BASE_URL!).origin;
    const headers = {'access-control-allow-origin': origin, 'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization, content-type', 'access-control-allow-methods': 'GET,POST,OPTIONS'};
    if (route.request().method() === 'OPTIONS') {await route.fulfill({status: 204, headers}); return;}
    const response = await page.request.fetch(route.request());
    await route.fulfill({response, headers: {...response.headers(), ...headers}});
  });
});

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email address', {exact: true}).fill(email);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText('Signed in', {exact: true})).toBeVisible();
}

test('signup validates confirmation and guides email confirmation without granting demo ownership', async ({page}) => {
  await page.goto('/signup');
  await page.getByLabel('Email address', {exact: true}).fill('new@example.invalid');
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByLabel('Confirm password', {exact: true}).fill('A-different-passphrase!');
  await page.getByRole('button', {name: 'Create account', exact: true}).click();
  await expect(page.locator('.auth-card').getByRole('alert')).toContainText('Passwords do not match');
  await page.getByLabel('Confirm password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Create account', exact: true}).click();
  await expect(page.getByRole('status').filter({hasText: 'Check your inbox'})).toBeVisible();
  await page.goto('/auth/confirm?token_hash=confirm-valid&type=email&next=https://attacker.invalid');
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.locator('.auth-account')).toContainText('new@example.invalid');
  await expect(page.locator('.auth-boundary')).toContainText('not yet connected');
});

test('login, verified API access, navigation, refresh persistence and logout', async ({page}) => {
  await login(page);
  await page.getByRole('button', {name: 'Check secure API connection'}).click();
  await expect(page.getByRole('status').filter({hasText: 'Secure API verified'})).toBeVisible();
  await page.reload();
  await expect(page.getByText('Signed in', {exact: true})).toBeVisible();
  await page.goto('/');
  await expect(page.getByRole('navigation', {name: 'Account navigation'})).toContainText(email);
  await page.getByRole('button', {name: 'Log out', exact: true}).click();
  await expect(page).toHaveURL(/\/login\?notice=signed-out$/);
  await expect(page.getByRole('status').filter({hasText: 'logged out'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', {name: 'Log out', exact: true})).toHaveCount(0);
  await page.goto('/account');
  await expect(page.getByRole('status').filter({hasText: 'session has ended'})).toBeVisible();
});

test('signup handles projects with email confirmation disabled', async ({page}) => {
  await page.goto('/signup');
  await page.getByLabel('Email address', {exact: true}).fill('instant@example.invalid');
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByLabel('Confirm password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Create account', exact: true}).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.locator('.auth-account')).toContainText('instant@example.invalid');
});

test('pending login shows a loading state and prevents duplicate submissions', async ({page}) => {
  let release!: () => void;
  const paused = new Promise<void>(resolve => {release = resolve;});
  await page.route(service+'/auth/v1/token?grant_type=password', async route => {await paused; await route.continue();});
  await page.goto('/login');
  await page.getByLabel('Email address', {exact: true}).fill(email);
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Please wait…', exact: true})).toBeDisabled();
  release();
  await expect(page).toHaveURL(/\/account$/);
});

test('incorrect credentials and unconfirmed email show safe actionable errors', async ({page}) => {
  await page.goto('/login');
  await page.getByLabel('Email address', {exact: true}).fill(email);
  await page.getByLabel('Password', {exact: true}).fill('Wrong-passphrase-123!');
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page.locator('.auth-card').getByRole('alert')).toContainText('email or password is incorrect');
  await page.getByLabel('Email address', {exact: true}).fill('unconfirmed@example.invalid');
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page.locator('.auth-card').getByRole('alert')).toContainText('Confirm your email');
  await page.getByRole('button', {name: 'Resend confirmation email'}).click();
  await expect(page.getByRole('status').filter({hasText: 'new link is on its way'})).toBeVisible();
});

test('recovery email, verified reset, logout and login with the new password', async ({page}) => {
  await page.goto('/forgot-password');
  await page.getByLabel('Email address', {exact: true}).fill(email);
  await page.getByRole('button', {name: 'Send recovery link'}).click();
  await expect(page.getByRole('status').filter({hasText: 'If an account exists'})).toBeVisible();
  await page.goto('/auth/confirm?token_hash=recovery-valid&type=recovery');
  await expect(page).toHaveURL(/\/reset-password$/);
  await page.getByLabel('New password', {exact: true}).fill('A-new-passphrase-456!');
  await page.getByLabel('Confirm password', {exact: true}).fill('A-new-passphrase-456!');
  await page.getByRole('button', {name: 'Update password'}).click();
  await expect(page).toHaveURL(/\/login\?notice=password-updated$/);
  await expect(page.getByRole('status').filter({hasText: 'password has been updated'})).toBeVisible();
  await page.getByLabel('Email address', {exact: true}).fill(email);
  await page.getByLabel('Password', {exact: true}).fill('A-new-passphrase-456!');
  await page.getByRole('button', {name: 'Log in', exact: true}).click();
  await expect(page.getByText('Signed in', {exact: true})).toBeVisible();
});

test('expired links and missing recovery sessions do not enable password changes', async ({page}) => {
  await page.goto('/auth/confirm?token_hash=expired&type=recovery');
  await expect(page).toHaveURL(/\/auth\/error\?reason=invalid-link$/);
  await expect(page.locator('.auth-card').getByRole('alert')).toContainText('invalid, expired, or already used');
  await page.goto('/reset-password');
  await expect(page.locator('.auth-card').getByRole('alert')).toContainText('missing or expired');
  await expect(page.getByRole('button', {name: 'Update password'})).toHaveCount(0);
});

test('PKCE callback uses its verifier cookie and rejects an external return URL', async ({page}) => {
  let callback = '';
  await page.route(service+'/auth/v1/recover**', async route => {
    callback = new URL(route.request().url()).searchParams.get('redirect_to') || '';
    await route.continue();
  });
  await page.goto('/forgot-password');
  await page.getByLabel('Email address', {exact: true}).fill(email);
  await page.getByRole('button', {name: 'Send recovery link'}).click();
  await expect(page.getByRole('status').filter({hasText: 'If an account exists'})).toBeVisible();
  const target = new URL(callback);
  expect((await page.context().cookies()).some(cookie => cookie.name.endsWith('-code-verifier'))).toBeTruthy();
  target.searchParams.set('code', 'valid-code');
  target.searchParams.set('next', 'https://attacker.invalid');
  await page.goto(target.toString());
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText('Signed in', {exact: true})).toBeVisible();
});

test('server-rejected sessions remove stale account navigation on focus', async ({page, request}) => {
  await login(page);
  await request.post(service+'/__expire');
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('button', {name: 'Log out', exact: true})).toHaveCount(0);
  await expect(page.getByRole('status').filter({hasText: 'session has ended'})).toBeVisible();
});

test('a different verified session clears the previous account API result', async ({page, context}) => {
  await login(page);
  await page.getByRole('button', {name: 'Check secure API connection'}).click();
  await expect(page.getByRole('status').filter({hasText: 'Secure API verified'})).toBeVisible();
  const other = await context.newPage();
  await other.goto('/signup');
  await other.getByLabel('Email address', {exact: true}).fill('instant@example.invalid');
  await other.getByLabel('Password', {exact: true}).fill(password);
  await other.getByLabel('Confirm password', {exact: true}).fill(password);
  await other.getByRole('button', {name: 'Create account', exact: true}).click();
  await expect(other).toHaveURL(/\/account$/);
  await page.bringToFront();
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.locator('.auth-account')).toContainText('instant@example.invalid');
  await expect(page.getByRole('status').filter({hasText: 'Secure API verified'})).toHaveCount(0);
  await other.close();
});

test('a demo profile switch does not switch the signed-in Supabase account', async ({page}) => {
  await login(page);
  await page.goto('/marketplace');
  await expect(page.getByLabel('Demo profile', {exact: true})).toBeEnabled();
  await page.getByLabel('Demo profile', {exact: true}).selectOption({label: 'Shorya Moses'});
  await expect(page.getByRole('navigation', {name: 'Account navigation'})).toContainText(email);
  await page.getByRole('navigation', {name: 'Account navigation'}).getByRole('link', {name: email, exact: true}).click();
  await expect(page.locator('.auth-account')).toContainText(email);
});

test('mobile forms fit the viewport and expose accessible navigation', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/signup');
  await expect(page.getByLabel('Email address', {exact: true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path: '../artifacts/auth-signup-mobile.png', fullPage: true});
  await page.getByRole('link', {name: 'Back to login'}).click();
  await expect(page.getByRole('heading', {name: 'Welcome back.'})).toBeVisible();
});

test('mobile marketplace shows separate account navigation and demo identity', async ({page}) => {
  await login(page);
  await page.setViewportSize({width: 390, height: 844});
  await page.goto('/marketplace');
  await expect(page.getByRole('navigation', {name: 'Account navigation'})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Log out', exact: true})).toBeVisible();
  await expect(page.getByLabel('Demo profile', {exact: true})).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path: '../artifacts/auth-marketplace-mobile.png', fullPage: true});
});

test('missing configuration disables account forms while leaving the demo reachable', async ({page}) => {
  test.skip(!process.env.AUTH_TEST_UNCONFIGURED_URL, 'Requires isolated unconfigured frontend');
  await page.goto(process.env.AUTH_TEST_UNCONFIGURED_URL!+'/signup');
  await expect(page.locator('.auth-card').getByRole('alert')).toContainText('unavailable or not configured');
  await expect(page.getByRole('button', {name: 'Create account', exact: true})).toBeDisabled();
  await page.getByRole('link', {name: 'Explore the local demo'}).click();
  await expect(page).toHaveURL(/\/marketplace$/);
  await expect(page.locator('.item-card').first()).toBeVisible();
});
