"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth, type VerificationMethod } from "@/hooks/use-auth";
import { Dashboard } from "@/components/dashboard";
import { api, errorMessage } from "@/services/api";

type AuthConfig = {
  disableSignup: boolean; passwordMinLength: number; verifyEmailMethod: VerificationMethod;
  requireNumber: boolean; requireLowercase: boolean; requireUppercase: boolean; requireSpecialChar: boolean;
};
type Mode = "login" | "signup" | "verify";

export default function Home() {
  const auth = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [otp, setOtp] = useState("");
  const [method, setMethod] = useState<VerificationMethod>("code");
  const [notice, setNotice] = useState("");
  const [formError, setFormError] = useState("");
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(0);
  const remaining = Math.max(0, Math.ceil((resendAt - now) / 1000));

  async function loadConfig() {
    setConfigError("");
    try {setConfig((await api.get<AuthConfig>("/auth/config")).data);}
    catch (err) {setConfigError(errorMessage(err));}
  }
  useEffect(() => {void loadConfig();}, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("insforge_type") !== "verify_email") return;
    setNotice(url.searchParams.get("insforge_status") === "success"
      ? "Email verified. Sign in to continue."
      : "Verification link failed. Request another verification email below.");
    // Informational only: the redirect does not establish a session.
    ["insforge_status", "insforge_type", "insforge_error"].forEach(key => url.searchParams.delete(key));
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }, []);
  useEffect(() => {
    if (!resendAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [resendAt]);
  function cooldown() {const time = Date.now(); setNow(time); setResendAt(time + 60000);}
  function switchMode(next: Mode) {
    setMode(next); setPassword(""); setConfirm(""); setOtp("");
    setNotice(""); setFormError(""); auth.clearError();
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setFormError(""); setNotice("");
    const address = email.trim();
    if (mode === "login") {await auth.login(address, password); setPassword(""); return;}
    if (mode === "verify") {await auth.verifyEmail(address, otp); setOtp(""); return;}
    if (password !== confirm) {setFormError("Passwords do not match."); return;}
    if (!config || config.disableSignup) {setFormError("Account registration is not available."); return;}
    const result = await auth.signup(address, password);
    setPassword(""); setConfirm("");
    if (!result) return;
    if (result.status === "verification_required") {
      setMethod(result.verification_method || config.verifyEmailMethod);
      setMode("verify"); cooldown();
      setNotice("Check your email to finish verification.");
    } else if (result.status === "sign_in_required") {
      setMode("login"); setNotice("Registration received. Sign in with your email and password.");
    }
  }
  async function resend() {
    setFormError(""); setNotice("");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {setFormError("Enter your email address first."); return;}
    const selected = await auth.resendVerification(email.trim());
    if (selected) {
      setMethod(selected); setMode("verify"); cooldown();
      setNotice("If verification is available for this address, an email has been sent. Check your spam folder too.");
    }
  }
  if (auth.user) return <Dashboard key={auth.user.id} user={auth.user} onLogout={() => void auth.logout()}/>;
  const signup = mode === "signup", verifying = mode === "verify";
  const rules = config ? [
    `at least ${config.passwordMinLength} characters`,
    ...(config.requireNumber ? ["a number"] : []),
    ...(config.requireLowercase ? ["a lowercase letter"] : []),
    ...(config.requireUppercase ? ["an uppercase letter"] : []),
    ...(config.requireSpecialChar ? ["a special character"] : []),
  ].join(", ") : "";
  return <main className="login-shell"><section className="panel login-card" aria-busy={auth.loading}>
    <p className="eyebrow">On-demand diagnostics</p><h1>AI Kubernetes Agent</h1>
    <h2>{signup ? "Create your account" : verifying ? "Verify your email" : "Sign in"}</h2>
    <p>{signup ? "Create an account to investigate your cluster and save diagnoses." : verifying
      ? method === "code" ? "Enter the six-digit code sent to your email." : "Open the verification link in your email, then return here to sign in."
      : "Sign in to investigate your cluster and review previous diagnoses."}</p>
    {notice && <p className="notice" role="status">{notice}</p>}
    <form onSubmit={event => void submit(event)}>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" autoComplete="username" required maxLength={254} value={email} disabled={auth.loading}
        onChange={e => {setEmail(e.target.value); setOtp("");}}/>
      {!verifying && <>
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete={signup ? "new-password" : "current-password"} required
          minLength={signup ? config?.passwordMinLength : undefined} maxLength={1024} value={password} disabled={auth.loading}
          aria-describedby={signup ? "password-rules" : undefined} onChange={e => setPassword(e.target.value)}/>
        {signup && <>
          <p id="password-rules" className="muted">{rules ? `Use ${rules}.` : "Loading password requirements…"}</p>
          <label htmlFor="confirm-password">Confirm password</label>
          <input id="confirm-password" type="password" autoComplete="new-password" required maxLength={1024}
            value={confirm} disabled={auth.loading} onChange={e => setConfirm(e.target.value)}/>
        </>}
      </>}
      {verifying && method === "code" && <>
        <label htmlFor="verification-code">Verification code</label>
        <input id="verification-code" type="text" inputMode="numeric" autoComplete="one-time-code" required
          pattern="[0-9]{6}" minLength={6} maxLength={6} value={otp} disabled={auth.loading}
          onChange={e => setOtp(e.target.value.replace(/[^0-9]/g, ""))}/>
      </>}
      {(auth.error || formError) && <p role="alert" className="notice">{formError || auth.error}</p>}
      {signup && configError && <p role="alert" className="notice">{configError} <button type="button" className="text-button" onClick={() => void loadConfig()}>Retry configuration</button></p>}
      {signup && config?.disableSignup && <p role="alert" className="notice">New account registration is disabled in this InsForge project. Contact the project administrator.</p>}
      {!(verifying && method === "link") && <button className="primary"
        disabled={auth.loading || (signup && (!config || config.disableSignup || !!configError))}>
        {auth.loading ? "Please wait…" : signup ? "Create account" : verifying ? "Verify email" : "Sign in"}
      </button>}
      {verifying && <button type="button" className="secondary" disabled={auth.loading || remaining > 0} onClick={() => void resend()}>
        {remaining > 0 ? `Resend available in ${remaining}s` : "Resend verification email"}
      </button>}
    </form>
    {mode === "login" ? <>
      <p className="muted">Don&apos;t have an account? <button type="button" className="text-button" disabled={auth.loading} onClick={() => switchMode("signup")}>Sign up</button></p>
      <button type="button" className="text-button" disabled={auth.loading} onClick={() => {switchMode("verify"); setMethod(config?.verifyEmailMethod || "code");}}>Verify an existing account</button>
    </> : <p className="muted">Already have an account? <button type="button" className="text-button" disabled={auth.loading} onClick={() => switchMode("login")}>Sign in</button></p>}
  </section></main>;
}
