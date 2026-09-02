/**
 * Lamba API — Auth
 */

import api, { saveToken, saveUser } from './client';

// ── Types ──────────────────────────────────────────────────────
export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  role: 'customer' | 'merchant';
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserResponse;
}

export interface SignUpRequest {
  email?: string;
  phone_number?: string;
  password: string;
  user_type: 'customer' | 'merchant';
}

export interface SignUpResponse {
  user_id: string;
  message: string;
  channel: 'email' | 'sms';
}

export interface VerifyRequest {
  user_id: string;
  verification_code: string;
}

export interface VerifyResponse {
  verified: boolean;
  message: string;
}

export interface SignInRequest {
  email_or_phone: string;
  password: string;
}

export interface SignInUserInfo {
  id: string;
  email: string | null;
  phone_number: string | null;
  full_name: string | null;
  user_type: 'customer' | 'merchant';
  verified: boolean;
  created_at: string;
}

export interface SignInResponse {
  access_token: string;
  token_type: string;
  user: SignInUserInfo;
}

// ── Functions ──────────────────────────────────────────────────
export async function signUp(data: SignUpRequest): Promise<SignUpResponse> {
  const { data: resp } = await api.post<SignUpResponse>('/api/v1/auth/signup', data);
  return resp;
}

export async function verifyCode(data: VerifyRequest): Promise<VerifyResponse> {
  const { data: resp } = await api.post<VerifyResponse>('/api/v1/auth/verify', data);
  return resp;
}

export async function signIn(emailOrPhone: string, password: string): Promise<SignInResponse> {
  const { data } = await api.post<SignInResponse>('/api/v1/auth/signin', {
    email_or_phone: emailOrPhone,
    password,
  });
  await saveToken(data.access_token);
  await saveUser(data.user);
  return data;
}
