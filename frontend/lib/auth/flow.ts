/** Fixed destinations: never accept arbitrary origins, encoded paths, or protocol URLs. */
export function safeAuthDestination(value: string | null) {
  return value === '/reset-password' ? '/reset-password' : '/account';
}

export function authErrorMessage(error: {code?: string; status?: number} | null, action = 'sign in') {
  switch (error?.code) {
    case 'invalid_credentials': return 'The email or password is incorrect. Please try again.';
    case 'email_not_confirmed': return 'Confirm your email before logging in. Check your inbox, or request another confirmation link below.';
    case 'weak_password': return 'This password does not meet the account security policy. Use a longer, unique passphrase.';
    case 'same_password': return 'Choose a password you have not used for this account before.';
    case 'reauthentication_needed': return 'For your security, log in again before changing your password.';
    case 'otp_expired': return 'This link has expired or has already been used. Request a new link.';
    case 'over_request_rate_limit':
    case 'over_email_send_rate_limit': return 'Too many attempts. Please wait a few minutes and try again.';
    default: return error?.status === 429 ? 'Too many attempts. Please wait and try again.' : `We could not ${action}. Check your connection and try again.`;
  }
}
