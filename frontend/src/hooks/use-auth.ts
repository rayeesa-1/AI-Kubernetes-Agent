"use client";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, refreshSession, setToken } from "@/services/api";
import type { User } from "@/types/investigation";

export type VerificationMethod = "code" | "link";
type RegistrationResult = {
  status: "signed_in" | "verification_required" | "sign_in_required";
  verification_method?: VerificationMethod;
  user?: User;
  access_token?: string;
};

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const cache = useQueryClient();
  useEffect(() => {
    let active = true;
    const expired = () => {setUser(null); cache.clear(); setError("Session expired. Please sign in again.");};
    window.addEventListener("agent:signed-out", expired);
    refreshSession().then(data => {if (active) setUser(data.user);})
      .catch(() => { /* No stored session: show sign-in. */ })
      .finally(() => {if (active) setLoading(false);});
    return () => {active = false; window.removeEventListener("agent:signed-out", expired);};
  }, [cache]);
  async function login(email: string, password: string) {
    setError(""); setLoading(true);
    try {
      const {data} = await api.post("/auth/login", {email, password});
      setToken(data.access_token); cache.clear(); setUser(data.user);
    } catch (err) {setError(errorMessage(err));}
    finally {setLoading(false);}
  }
  async function logout() {
    setLoading(true);
    try {await api.post("/auth/logout");}
    catch (err) {setError(errorMessage(err));}
    finally {setToken(""); setUser(null); cache.clear(); setLoading(false);}
  }
  async function signup(email: string, password: string): Promise<RegistrationResult | null> {
    setError(""); setLoading(true);
    try {
      const {data} = await api.post<RegistrationResult>("/auth/signup", {email, password});
      if (data.status === "signed_in" && data.access_token && data.user) {
        setToken(data.access_token); cache.clear(); setUser(data.user);
      }
      return data;
    } catch (err) {setError(errorMessage(err)); return null;}
    finally {setLoading(false);}
  }
  async function verifyEmail(email: string, otp: string) {
    setError(""); setLoading(true);
    try {
      const {data} = await api.post<{user: User; access_token: string}>("/auth/verify-email", {email, otp});
      setToken(data.access_token); cache.clear(); setUser(data.user);
      return true;
    } catch (err) {setError(errorMessage(err)); return false;}
    finally {setLoading(false);}
  }
  async function resendVerification(email: string): Promise<VerificationMethod | null> {
    setError(""); setLoading(true);
    try {
      const {data} = await api.post<{verification_method: VerificationMethod}>("/auth/resend-verification", {email});
      return data.verification_method;
    } catch (err) {setError(errorMessage(err)); return null;}
    finally {setLoading(false);}
  }
  return {user, loading, error, login, logout, signup, verifyEmail, resendVerification,
    clearError: () => setError("")};
}
