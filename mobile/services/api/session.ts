/**
 * Session renewal logic, kept free of React Native imports so `node --test` can run it
 * (see mobile/tests/session.test.mjs). client.ts wires it to SecureStore, axios and the navigation.
 *
 * Erasable TypeScript only (no enums, namespaces or parameter properties): Node strips the types and
 * runs this file as it is. Type-only imports are fine; runtime imports are not.
 */

import type { AxiosInstance, InternalAxiosRequestConfig } from 'axios';

export type RenewResult = 'renewed' | 'ended' | 'unavailable';

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

export interface SessionDeps {
  /** Storage reads may throw (locked keychain): that is "unavailable", not "signed out". */
  getAccessToken(): Promise<string | null>;
  getRefreshToken(): Promise<string | null>;
  saveTokens(accessToken: string, refreshToken: string): Promise<void>;
  clear(): Promise<void>;
  callRefresh(refreshToken: string): Promise<RefreshResponse>;
  onSessionEnded(): void;
}

// Answers that mean "this refresh token is no good" (401 is the server's answer; the others cover
// a damaged token in storage). Anything else (no network, timeout, 429, 5xx) says nothing about
// the session, so the user stays signed in.
const REJECTED = [400, 401, 403, 422];

/** Auth endpoints answer 401 for wrong passwords and dead refresh tokens: never renew on those. /auth/me is the exception. */
export function isAuthEndpoint(url?: string): boolean {
  if (!url) return false;
  const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0];
  return path.startsWith('/api/v1/auth/') && !path.startsWith('/api/v1/auth/me');
}

/**
 * Should a failed request trigger a renewal? Only a 401 on a request that actually carried a token
 * (guests and signed-out screens are left alone), once per request, and not for the auth endpoints.
 */
export function shouldRenew(
  status: number | undefined,
  request: { url?: string; sentToken?: string; retried?: boolean },
): boolean {
  return status === 401 && !!request.sentToken && !request.retried && !isAuthEndpoint(request.url);
}

export function createSessionManager(deps: SessionDeps) {
  let inflight: Promise<RenewResult> | null = null;
  // Bumped when a session starts or ends. A refresh answer that arrives after that belongs to a
  // session that is gone and must not be stored (it would sign the old user back in).
  let version = 0;
  let endedAnnounced = false;

  async function end(): Promise<RenewResult> {
    version++;
    await deps.clear().catch(() => {});
    if (!endedAnnounced) {
      endedAnnounced = true; // one message however many requests failed together
      deps.onSessionEnded();
    }
    return 'ended';
  }

  async function run(sentToken: string): Promise<RenewResult> {
    let current: string | null;
    let refreshToken: string | null;
    try {
      current = await deps.getAccessToken();
      if (current === null) return 'ended'; // already signed out (logout, or ended by another request)
      if (current !== sentToken) return 'renewed'; // another request renewed while this one was in flight
      refreshToken = await deps.getRefreshToken();
    } catch {
      return 'unavailable';
    }
    if (!refreshToken) return end(); // a session from before refresh tokens existed: it can't be renewed

    const startedAt = version;
    let answer: RefreshResponse;
    try {
      answer = await deps.callRefresh(refreshToken);
    } catch (err: any) {
      if (version !== startedAt) return 'ended';
      return REJECTED.includes(err?.response?.status) ? end() : 'unavailable';
    }
    if (version !== startedAt) return 'ended'; // signed out or in again meanwhile: drop this answer
    try {
      await deps.saveTokens(answer.access_token, answer.refresh_token);
    } catch {
      return 'unavailable';
    }
    return 'renewed';
  }

  return {
    /**
     * Renew the session after a 401 on a request that was sent with `sentToken`.
     * Parallel callers share ONE refresh call (the server rotates the token on every use, so a second
     * call with the same token would look like a stolen one).
     */
    renew(sentToken: string): Promise<RenewResult> {
      if (!inflight) {
        inflight = run(sentToken).finally(() => {
          inflight = null;
        });
      }
      return inflight;
    },
    /** A new session was saved (sign-in). */
    started(): void {
      version++;
      endedAnnounced = false;
    },
    /** The user signed out on purpose: drop any refresh that is still on its way. */
    loggedOut(): void {
      version++;
    },
  };
}

/** One-to-many notification for "the session ended". An event with nobody listening yet is kept for the first listener. */
export function createSessionEvents() {
  const listeners = new Set<() => void>();
  let pending = false;
  return {
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      if (pending) {
        pending = false;
        listener();
      }
      return () => {
        listeners.delete(listener);
      };
    },
    emit(): void {
      if (listeners.size === 0) {
        pending = true;
        return;
      }
      listeners.forEach((l) => l());
    },
  };
}

/** Request config with the bookkeeping the 401 handler needs. */
interface LambaRequestConfig extends InternalAxiosRequestConfig {
  lambaSentToken?: string; // the access token this request carried (none: a guest request)
  lambaRetried?: boolean; // already repeated once after a renewal
}

/**
 * Put the token on every request, and handle a 401 on a request that carried one: renew once (shared by
 * all parallel requests) and repeat the request. If the session can't be renewed the error is rejected
 * with `sessionEnded` set (the session is already cleared and announced); if the renewal could not be
 * attempted or checked (no network...) it is rejected with `sessionRenewalUnavailable` and the user stays
 * signed in. Guests, the auth endpoints and every other error are passed through untouched.
 */
export function attachSessionInterceptors(
  api: AxiosInstance,
  options: { getAccessToken(): Promise<string | null>; session: ReturnType<typeof createSessionManager> },
): void {
  api.interceptors.request.use(async (config) => {
    try {
      const token = await options.getAccessToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
        (config as LambaRequestConfig).lambaSentToken = token;
      }
    } catch {
      // Ignore locked keychain errors in background state
    }
    return config;
  });

  api.interceptors.response.use(
    (response) => response,
    async (error) => {
      const config = error.config as LambaRequestConfig | undefined;
      if (config && shouldRenew(error.response?.status, {
        url: config.url, sentToken: config.lambaSentToken, retried: config.lambaRetried,
      })) {
        const outcome = await options.session.renew(config.lambaSentToken as string);
        if (outcome === 'renewed') {
          config.lambaRetried = true;
          return api.request(config);
        }
        // For callers that must tell "signed out" from "couldn't check" (app start)
        if (outcome === 'ended') error.sessionEnded = true;
        else error.sessionRenewalUnavailable = true;
      }
      return Promise.reject(error);
    },
  );
}
