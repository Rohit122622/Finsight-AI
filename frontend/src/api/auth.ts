



import apiClient, { API_BASE_URL } from "./client";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "../types";

export async function loginApi(data: LoginRequest): Promise<TokenResponse> {
  const resp = await apiClient.post<TokenResponse>("/auth/login", data);
  return resp.data;
}

export async function registerApi(data: RegisterRequest): Promise<TokenResponse> {
  const resp = await apiClient.post<TokenResponse>("/auth/register", data);
  return resp.data;
}

export async function getMeApi(): Promise<User> {
  const resp = await apiClient.get<User>("/auth/me");
  return resp.data;
}

export async function refreshTokensApi(refreshToken: string): Promise<TokenResponse> {
  const resp = await apiClient.post<TokenResponse>("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return resp.data;
}

export async function logoutApi(): Promise<void> {
  await apiClient.post("/auth/logout");
}





export function getGoogleLoginUrl(): string {
  return `${API_BASE_URL}/auth/google/login`;
}
