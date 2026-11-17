import axios from "axios";
import type { HealthResponse } from "@/types/health";
import type { User } from "@/types/investigation";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000",
  timeout: 15000,
  withCredentials: true,
});
let accessToken = ""; // Memory only. Refresh token stays in the backend's HttpOnly cookie.
let refreshPromise: Promise<{user: User; access_token: string}> | null = null;
export function setToken(token: string) { accessToken = token; }
export function getToken() { return accessToken; }
export async function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = api.post<{user: User; access_token: string}>("/auth/refresh")
      .then(({data}) => {setToken(data.access_token); return data;})
      .finally(() => {refreshPromise = null;});
  }
  return refreshPromise;
}
api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});
api.interceptors.response.use(response => response, async error => {
  const config = error.config;
  if (error.response?.status === 401 && config && !["/auth/login", "/auth/refresh", "/auth/logout", "/auth/signup", "/auth/verify-email", "/auth/resend-verification", "/auth/config"].includes(config.url) && !config._retried) {
    config._retried = true;
    try { await refreshSession(); }
    catch {
      setToken("");
      window.dispatchEvent(new Event("agent:signed-out"));
      return Promise.reject(error);
    }
    return api.request(config);
  }
  return Promise.reject(error);
});
export async function getHealth(): Promise<HealthResponse> {
  return (await api.get<HealthResponse>("/health")).data;
}
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED") return "Request timed out. The investigation may still be running; refresh history before retrying.";
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (error.response?.status === 422) return "Check the email address and verification code format, then try again.";
    return "Cannot reach the service. Check Docker Desktop and your network, then retry.";
  }
  return error instanceof Error ? error.message : "Something went wrong. Please retry.";
}
