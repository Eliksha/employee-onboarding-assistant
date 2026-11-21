// Dependency-free auth helpers (tested with `node --test`).
// The session itself lives in an HttpOnly cookie that JavaScript cannot read; only the per-session
// CSRF token is held here, in memory (never localStorage/sessionStorage).

export const CSRF_HEADER = 'X-CSRF-Token';

const UNSAFE_METHODS = new Set(['post', 'put', 'patch', 'delete']);

export const isUnsafeMethod = (method) => UNSAFE_METHODS.has(String(method ?? 'get').toLowerCase());

// Login/me/logout handle their own 401s; any other 401 means the session expired.
export const isAuthEndpoint = (url) => /^\/?auth\//.test(String(url ?? '').replace(/^\/api/, ''));

export function loginErrorMessage(error) {
  const status = error?.response?.status;
  if (status === 401) return 'Invalid email or password.';
  if (status === 429) return 'Too many failed sign-in attempts. Please wait a few minutes and try again.';
  if (status === 422) return 'Enter a valid email address and password.';
  if (!error?.response) return 'Cannot reach the OnboardAI server. Check that the backend is running.';
  return 'Sign-in failed. Please try again.';
}

export const SESSION_EXPIRED_NOTICE = 'Your session has ended. Please sign in again.';
export const SIGNED_OUT_NOTICE = 'You have signed out.';
