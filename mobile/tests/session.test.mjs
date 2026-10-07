/**
 * Tests for services/api/session.ts: the session renewal logic and the axios interceptors, run with
 * real axios against a fake server. No React Native, no device:   cd mobile && npm test
 *
 * Node strips the TypeScript types from session.ts and runs it as it is (Node 22.18 or newer; older
 * 22.x needs --experimental-strip-types).
 */

import assert from 'node:assert/strict';
import { test } from 'node:test';
import axios, { AxiosError } from 'axios';
import {
  attachSessionInterceptors, createSessionEvents, createSessionManager, isAuthEndpoint, shouldRenew,
} from '../services/api/session.ts';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function httpError(config, status, data = {}) {
  const response = { status, data, headers: {}, config, statusText: '' };
  return new AxiosError('Request failed with status code ' + status, 'ERR_BAD_REQUEST', config, null, response);
}

/**
 * A world with a storage, a fake API behind a real axios instance, and a refresh endpoint:
 *   world.api                 the axios instance with the interceptors attached
 *   world.store               {access, refresh}
 *   world.validAccess         access tokens the fake API accepts
 *   world.refreshCalls        refresh tokens the refresh endpoint received
 *   world.refreshMode         'ok' | 'rejected' | 'network' | 'server_error' | 'slow'
 *   world.ended               how many times the session-ended event fired
 */
function makeWorld({ access = 'access-1', refresh = 'refresh-1', validAccess = [] } = {}) {
  const w = {
    store: { access, refresh },
    validAccess: new Set(validAccess),
    refreshCalls: [],
    requests: [],
    refreshMode: 'ok',
    refreshDelayMs: 30,
    refreshSeq: 1,
    ended: 0,
    rejectEverything: false,
    failReads: false,
    failSave: false,
    slowPaths: new Map(), // url -> ms the fake API takes to answer
  };

  w.api = axios.create({
    baseURL: 'http://fake',
    adapter: async (config) => {
      const auth = config.headers.Authorization ?? config.headers.get?.('Authorization');
      w.requests.push({ url: config.url, auth });
      const delay = w.slowPaths.get(config.url);
      if (delay) await sleep(delay);
      if (config.url.startsWith('/api/v1/auth/signin')) throw httpError(config, 401, { detail: 'Invalid Credentials' });
      if (config.url === '/api/v1/offline') throw new AxiosError('Network Error', 'ERR_NETWORK', config, null);
      const token = (auth ?? '').replace('Bearer ', '');
      if (!w.rejectEverything && (w.validAccess.has(token) || !config.url.startsWith('/api/v1/private') && !config.url.startsWith('/api/v1/auth/me'))) {
        return { data: { ok: true, url: config.url, auth }, status: 200, statusText: 'OK', headers: {}, config };
      }
      throw httpError(config, 401, { detail: 'Invalid or expired token' });
    },
  });

  w.session = createSessionManager({
    getAccessToken: async () => { if (w.failReads) throw new Error('keychain locked'); return w.store.access; },
    getRefreshToken: async () => { if (w.failReads) throw new Error('keychain locked'); return w.store.refresh; },
    saveTokens: async (a, r) => { if (w.failSave) throw new Error('disk full'); w.store.access = a; w.store.refresh = r; },
    clear: async () => { w.store.access = null; w.store.refresh = null; },
    callRefresh: async (refreshToken) => {
      w.refreshCalls.push(refreshToken);
      await sleep(w.refreshDelayMs);
      if (w.refreshMode === 'network') throw new AxiosError('Network Error', 'ERR_NETWORK');
      if (w.refreshMode === 'rejected') throw httpError({}, 401, { detail: 'session ended' });
      if (w.refreshMode === 'server_error') throw httpError({}, 503);
      if (w.refreshMode === 'too_many') throw httpError({}, 429);
      const n = ++w.refreshSeq;
      w.validAccess.add('access-' + n);
      return { access_token: 'access-' + n, refresh_token: 'refresh-' + n };
    },
    onSessionEnded: () => { w.ended++; },
  });

  attachSessionInterceptors(w.api, {
    getAccessToken: async () => w.store.access,
    session: w.session,
  });
  return w;
}

// ─────────────────────────────────────────────────────────────── plain rules
test('auth endpoints never trigger a renewal, except /auth/me', () => {
  for (const url of ['/api/v1/auth/signin', '/api/v1/auth/refresh', '/api/v1/auth/logout', '/api/v1/auth/signup',
    '/api/v1/auth/verify', '/api/v1/auth/forgot-password', '/api/v1/auth/reset-password', 'https://api.lambajo.com/api/v1/auth/signin?x=1']) {
    assert.equal(isAuthEndpoint(url), true, url);
  }
  for (const url of ['/api/v1/auth/me', '/api/v1/customer/search-history', undefined, '/api/v1/merchant/items']) {
    assert.equal(isAuthEndpoint(url), false, String(url));
  }
});

test('shouldRenew: only a 401 on a request that carried a token, once, and not on auth endpoints', () => {
  const ok = { url: '/api/v1/private', sentToken: 't' };
  assert.equal(shouldRenew(401, ok), true);
  assert.equal(shouldRenew(401, { ...ok, url: '/api/v1/auth/me' }), true);
  assert.equal(shouldRenew(401, { url: '/api/v1/private' }), false, 'guest request (no token sent)');
  assert.equal(shouldRenew(401, { ...ok, url: '/api/v1/auth/signin' }), false, 'login screen');
  assert.equal(shouldRenew(401, { ...ok, retried: true }), false, 'already repeated once');
  for (const status of [undefined, 200, 400, 403, 404, 429, 500, 503]) assert.equal(shouldRenew(status, ok), false, String(status));
});

// ─────────────────────────────────────────────────────────────── the interceptors
test('guest requests and network errors are not touched', async () => {
  const w = makeWorld({ access: null, refresh: null });
  await assert.rejects(w.api.get('/api/v1/private'), (e) => e.response.status === 401 && !e.sessionEnded && !e.sessionRenewalUnavailable);
  assert.deepEqual([w.refreshCalls.length, w.ended], [0, 0]);
  const signedIn = makeWorld({ validAccess: ['access-1'] });
  await assert.rejects(signedIn.api.get('/api/v1/offline'), (e) => e.code === 'ERR_NETWORK' && !e.sessionEnded);
  assert.deepEqual([signedIn.refreshCalls.length, signedIn.ended, signedIn.store.access], [0, 0, 'access-1']);
});

test('the login screen: a wrong password 401 does not renew or clear a token that is still stored', async () => {
  const w = makeWorld({ validAccess: [] });
  await assert.rejects(w.api.post('/api/v1/auth/signin', {}), (e) => e.response.status === 401 && !e.sessionEnded);
  assert.deepEqual([w.refreshCalls.length, w.ended, w.store.access], [0, 0, 'access-1']);
});

test('a valid token is sent and nothing else happens', async () => {
  const w = makeWorld({ validAccess: ['access-1'] });
  const res = await w.api.get('/api/v1/private');
  assert.equal(res.data.auth, 'Bearer access-1');
  assert.equal(w.refreshCalls.length, 0);
});

test('an expired access token is renewed once and the request is repeated with the new token', async () => {
  const w = makeWorld(); // access-1 is not valid any more
  const res = await w.api.get('/api/v1/private');
  assert.equal(res.status, 200);
  assert.equal(res.data.auth, 'Bearer access-2');
  assert.deepEqual(w.refreshCalls, ['refresh-1']);
  assert.deepEqual(w.store, { access: 'access-2', refresh: 'refresh-2' });
  assert.equal(w.requests.length, 2);
});

test('parallel requests share ONE refresh call and all succeed', async () => {
  const w = makeWorld();
  const results = await Promise.all(Array.from({ length: 6 }, (_, i) => w.api.get('/api/v1/private?i=' + i)));
  assert.deepEqual(results.map((r) => r.status), [200, 200, 200, 200, 200, 200]);
  assert.equal(w.refreshCalls.length, 1, 'the server rotates the token on every use: a second call would look like theft');
  assert.ok(results.every((r) => r.data.auth === 'Bearer access-2'));
});

test('a request that was in flight during the renewal and fails later does not start another refresh', async () => {
  const w = makeWorld();
  w.slowPaths.set('/api/v1/private/slow', 120); // sent with the old token, answers 401 AFTER the renewal finished
  const slow = w.api.get('/api/v1/private/slow');
  await sleep(10);
  const fast = w.api.get('/api/v1/private/fast');
  const [a, b] = await Promise.all([slow, fast]);
  assert.deepEqual([a.status, b.status], [200, 200]);
  assert.equal(w.refreshCalls.length, 1);
});

test('a refresh refused by the server ends the session once, however many requests failed together', async () => {
  const w = makeWorld();
  w.refreshMode = 'rejected';
  const settled = await Promise.allSettled(Array.from({ length: 5 }, () => w.api.get('/api/v1/private')));
  assert.ok(settled.every((s) => s.status === 'rejected' && s.reason.sessionEnded === true));
  assert.equal(w.refreshCalls.length, 1);
  assert.equal(w.ended, 1, 'one "session ended" message');
  assert.deepEqual(w.store, { access: null, refresh: null });
  // later 401s of requests that were already on their way: no token any more, no second message
  await assert.rejects(w.api.get('/api/v1/private'));
  assert.equal(w.ended, 1);
});

test('no network / 5xx / 429 during the renewal keep the user signed in', async () => {
  for (const mode of ['network', 'server_error', 'too_many']) {
    const w = makeWorld();
    w.refreshMode = mode;
    await assert.rejects(w.api.get('/api/v1/private'), (e) => e.sessionRenewalUnavailable === true && !e.sessionEnded, mode);
    assert.deepEqual([w.ended, w.store.access, w.store.refresh], [0, 'access-1', 'refresh-1'], mode);
    w.refreshMode = 'ok'; // back online: the next request renews and works
    assert.equal((await w.api.get('/api/v1/private')).status, 200, mode);
    assert.equal(w.ended, 0);
  }
});

test('a request that fails again after the renewal is not repeated in a loop', async () => {
  const w = makeWorld();
  w.rejectEverything = true; // even the fresh token is refused
  await assert.rejects(w.api.get('/api/v1/private'), (e) => e.response.status === 401);
  assert.equal(w.refreshCalls.length, 1);
  assert.equal(w.requests.length, 2, 'original + one retry, no more');
});

test('a session from before refresh tokens existed (no refresh token) cannot be renewed: it ends', async () => {
  const w = makeWorld({ refresh: null });
  await assert.rejects(w.api.get('/api/v1/private'), (e) => e.sessionEnded === true);
  assert.deepEqual([w.refreshCalls.length, w.ended, w.store.access], [0, 1, null]);
});

test('GET /auth/me is renewed like any other request (app start)', async () => {
  const w = makeWorld();
  assert.equal((await w.api.get('/api/v1/auth/me')).status, 200);
  const dead = makeWorld();
  dead.refreshMode = 'rejected';
  await assert.rejects(dead.api.get('/api/v1/auth/me'), (e) => e.sessionEnded === true);
  assert.equal(dead.ended, 1);
});

test('a locked keychain is "unavailable", never "signed out"', async () => {
  const w = makeWorld();
  w.failReads = true;
  await assert.rejects(w.api.get('/api/v1/private'));
  assert.equal(w.ended, 0);
  const s = makeWorld();
  s.failSave = true;
  await assert.rejects(s.api.get('/api/v1/private'), (e) => e.sessionRenewalUnavailable === true);
  assert.equal(s.ended, 0);
});

test('signing out while a renewal is on its way drops its answer', async () => {
  const w = makeWorld();
  const request = w.api.get('/api/v1/private');
  await sleep(10);
  w.session.loggedOut();
  w.store.access = null;
  w.store.refresh = null; // what logout() does
  await assert.rejects(request);
  assert.deepEqual(w.store, { access: null, refresh: null }, 'the old session must not come back');
  assert.equal(w.ended, 0, 'a deliberate logout shows no "session ended" message');
});

test('signing in again while a renewal is on its way drops its answer', async () => {
  const w = makeWorld();
  const request = w.api.get('/api/v1/private');
  await sleep(10);
  w.store.access = 'access-NEW';
  w.store.refresh = 'refresh-NEW';
  w.session.started();
  await assert.rejects(request);
  assert.deepEqual(w.store, { access: 'access-NEW', refresh: 'refresh-NEW' });
});

test('after a new sign-in a later end of session is announced again', async () => {
  const w = makeWorld();
  w.refreshMode = 'rejected';
  await assert.rejects(w.api.get('/api/v1/private'));
  assert.equal(w.ended, 1);
  w.store = { access: 'access-9', refresh: 'refresh-9' };
  w.session.started();
  await assert.rejects(w.api.get('/api/v1/private'));
  assert.equal(w.ended, 2);
});

// ─────────────────────────────────────────────────────────────── events
test('session events: an event with nobody listening is kept for the first listener', () => {
  const events = createSessionEvents();
  let calls = 0;
  events.emit(); // nobody yet (e.g. the layout has not mounted)
  const off = events.subscribe(() => calls++);
  assert.equal(calls, 1);
  events.emit();
  assert.equal(calls, 2);
  off();
  events.emit(); // nobody listening again: kept, not delivered
  assert.equal(calls, 2);
  events.subscribe(() => calls++);
  assert.equal(calls, 3);
});
