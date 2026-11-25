import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isAuthEndpoint, isUnsafeMethod, loginErrorMessage } from './auth.js';

test('CSRF header is attached only to state-changing methods', () => {
  for (const m of ['post', 'PUT', 'patch', 'Delete']) assert.equal(isUnsafeMethod(m), true, m);
  for (const m of ['get', 'HEAD', 'options', undefined]) assert.equal(isUnsafeMethod(m), false, String(m));
});

test('auth endpoints are excluded from the session-expired redirect', () => {
  for (const url of ['/auth/login', 'auth/me', '/api/auth/logout']) assert.equal(isAuthEndpoint(url), true, url);
  for (const url of ['/chat', '/employees/EMP001', '/history', undefined]) assert.equal(isAuthEndpoint(url), false, String(url));
});

test('login errors are generic and never reveal whether an email exists', () => {
  assert.equal(loginErrorMessage({ response: { status: 401 } }), 'Invalid email or password.');
  assert.match(loginErrorMessage({ response: { status: 429 } }), /Too many failed sign-in attempts/);
  assert.match(loginErrorMessage({}), /Cannot reach the OnboardAI server/);
  assert.equal(loginErrorMessage({ response: { status: 500 } }), 'Sign-in failed. Please try again.');
});
