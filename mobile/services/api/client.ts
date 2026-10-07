/**
 * Lamba API Client — Core
 *
 * Axios instance with JWT management via SecureStore.
 * All domain modules import from here.
 */

import axios, { AxiosInstance } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { attachSessionInterceptors, createSessionEvents, createSessionManager } from './session';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'lamba_token';
const REFRESH_KEY = 'lamba_refresh_token';
const USER_KEY = 'lamba_user';

// ── Axios Instance ─────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Same server, but WITHOUT the interceptors below: the refresh and logout calls must never
// trigger a renewal themselves.
const bareApi: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Session: renewal after a 401, and the "session ended" notice ─
const sessionEvents = createSessionEvents();

/** Listen for the session ending (renewal refused, or a session that can't be renewed). The root layout sends the user to login. */
export const onSessionEnded = sessionEvents.subscribe;

const session = createSessionManager({
  // These reads throw on a locked keychain on purpose: that must not look like "signed out".
  getAccessToken: () => SecureStore.getItemAsync(TOKEN_KEY),
  getRefreshToken: () => SecureStore.getItemAsync(REFRESH_KEY),
  // Refresh token first: if the second write fails, the old access token still triggers a renewal
  // that uses the new refresh token, instead of replaying one the server has already rotated.
  saveTokens: async (accessToken, refreshToken) => {
    await SecureStore.setItemAsync(REFRESH_KEY, refreshToken);
    await SecureStore.setItemAsync(TOKEN_KEY, accessToken);
  },
  clear: removeToken,
  callRefresh: async (refreshToken) => {
    const { data } = await bareApi.post('/api/v1/auth/refresh', { refresh_token: refreshToken });
    return data;
  },
  onSessionEnded: sessionEvents.emit,
});

// Token on every request; a 401 on a request that carried one renews the session once (shared by all
// parallel requests) and repeats the request. If it can't be renewed the session is cleared and the
// user is sent to login (see onSessionEnded). Guests, the auth endpoints and network errors are left alone.
attachSessionInterceptors(api, {
  getAccessToken: () => SecureStore.getItemAsync(TOKEN_KEY),
  session,
});

/** True when this failed request ended the session (it is already cleared and the user is being sent to login). */
export function isSessionEnded(err: any): boolean {
  return !!err?.sessionEnded;
}

// ── Token & User Persistence ───────────────────────────────────
export async function saveToken(token: string): Promise<void> {
  try { await SecureStore.setItemAsync(TOKEN_KEY, token); } catch {}
}

export async function getToken(): Promise<string | null> {
  try { return await SecureStore.getItemAsync(TOKEN_KEY); } catch { return null; }
}

export async function saveRefreshToken(token: string): Promise<void> {
  try { await SecureStore.setItemAsync(REFRESH_KEY, token); } catch {}
}

export async function getRefreshToken(): Promise<string | null> {
  try { return await SecureStore.getItemAsync(REFRESH_KEY); } catch { return null; }
}

/** Store the tokens and user that sign-in returned, and start a fresh session. */
export async function saveSession(tokens: { access_token: string; refresh_token?: string | null }, user: any): Promise<void> {
  if (tokens.refresh_token) await saveRefreshToken(tokens.refresh_token);
  else { try { await SecureStore.deleteItemAsync(REFRESH_KEY); } catch {} }
  await saveToken(tokens.access_token);
  await saveUser(user);
  session.started();
}

export async function removeToken(): Promise<void> {
  // Each key on its own: a failure on one must not leave the others behind
  for (const key of [TOKEN_KEY, REFRESH_KEY, USER_KEY]) {
    try { await SecureStore.deleteItemAsync(key); } catch {}
  }
}

export async function saveUser(user: any): Promise<void> {
  try { await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user)); } catch {}
}

export async function getUser(): Promise<any | null> {
  try {
    const raw = await SecureStore.getItemAsync(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

/** Sign out on purpose: revoke the session on the server (best effort), then clear it here. */
export async function logout(): Promise<void> {
  const refreshToken = await getRefreshToken();
  session.loggedOut(); // an answer to a renewal still on its way must not sign the user back in
  await removeToken();
  if (refreshToken) {
    try {
      await bareApi.post('/api/v1/auth/logout', { refresh_token: refreshToken }, { timeout: 3000 });
    } catch {
      // Offline: the session simply expires on the server
    }
  }
}

export async function updateProfile(data: { full_name?: string; phone_number?: string }): Promise<any> {
  const { data: result } = await api.patch('/api/v1/customer/profile', data);
  return result;
}

export const apiClient = api;
export default api;
