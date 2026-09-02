/**
 * Lamba API Client — Core
 *
 * Axios instance with JWT management via SecureStore.
 * All domain modules import from here.
 */

import axios, { AxiosInstance } from 'axios';
import * as SecureStore from 'expo-secure-store';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

const TOKEN_KEY = 'lamba_token';
const USER_KEY = 'lamba_user';

// ── Axios Instance ─────────────────────────────────────────────
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use(async (config) => {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch (err) {
    // Ignore locked keychain errors in background state
  }
  return config;
});

// Auto-clear credentials on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
        await SecureStore.deleteItemAsync(USER_KEY);
      } catch {
        // Ignore keychain lock exceptions
      }
    }
    return Promise.reject(error);
  }
);

// ── Token & User Persistence ───────────────────────────────────
export async function saveToken(token: string): Promise<void> {
  try { await SecureStore.setItemAsync(TOKEN_KEY, token); } catch {}
}

export async function getToken(): Promise<string | null> {
  try { return await SecureStore.getItemAsync(TOKEN_KEY); } catch { return null; }
}

export async function removeToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(USER_KEY);
  } catch {}
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

export async function logout(): Promise<void> {
  await removeToken();
}

export async function updateProfile(data: { full_name?: string; phone_number?: string }): Promise<any> {
  const { data: result } = await api.patch('/api/v1/customer/profile', data);
  return result;
}

export const apiClient = api;
export default api;
