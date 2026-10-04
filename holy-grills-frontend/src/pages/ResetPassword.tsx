import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Lock, Loader2, AlertTriangle, Eye, EyeOff, Check } from "lucide-react";
import { liveApi } from "@/lib/liveApi";
import AuthLayout from "@/components/AuthLayout";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  // Captured once, into state: the address bar is scrubbed below (S2), and
  // re-reading the parameter afterwards must not flip the form into its
  // "invalid link" state mid-session.
  const [resetToken] = useState(() => searchParams.get("token"));
  const [done, setDone] = useState(false);

  // S2 — drop the token from the URL as soon as it is in memory: it no longer
  // sits in browser history, in a copied/shared link, or in the Referer of any
  // request this page makes. The token itself is unaffected — it is sent to the
  // backend in the POST body when the form is submitted.
  useEffect(() => {
    if (!resetToken) return;
    window.history.replaceState(null, "", window.location.pathname);
  }, [resetToken]);

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const strength = (() => {
    let s = 0;
    if (newPassword.length >= 8) s++;
    if (/[A-Z]/.test(newPassword)) s++;
    if (/[a-z]/.test(newPassword)) s++;
    if (/\d/.test(newPassword)) s++;
    if (/[^A-Za-z0-9]/.test(newPassword)) s++;
    return s;
  })();
  const match = newPassword && confirmPassword && newPassword === confirmPassword;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      // Custom-backend confirm — POST /api/auth/reset-password/confirm with the
      // token from the reset email + the new password, straight to the Flask
      // backend that owns the users (POST /auth/reset-password/confirm).
      // could never validate the custom-backend token. If this endpoint 404s,
      // the error surfaces here so the backend route can be corrected.
      await liveApi.auth.confirmReset({ access_token: resetToken, new_password: newPassword });
      // Confirmation rather than a silent bounce to /login, so the user knows the
      // password actually changed (and that every other session was signed out).
      setDone(true);
    } catch (err) {
      setError(err.message || "Failed to reset password");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <AuthLayout
        icon={Check}
        title="Password changed"
        subtitle="Your new password is in place"
        footer={
          <Link to="/login" className="text-primary font-medium hover:underline">
            Continue to login
          </Link>
        }
      >
        <p className="text-sm text-foreground text-center leading-relaxed">
          You can now sign in with your new password. For safety, every other
          session on your account has been signed out.
        </p>
      </AuthLayout>
    );
  }

  if (!resetToken) {
    return (
      <AuthLayout
        icon={AlertTriangle}
        title="Invalid reset link"
        subtitle="This password reset link is missing or invalid"
        footer={
          <Link to="/forgot-password" className="text-primary font-medium hover:underline">
            Request a new link
          </Link>
        }
      >
        <p className="text-sm text-foreground text-center leading-relaxed">
          The link you used appears to be incomplete. Please request a new password reset email.
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      icon={Lock}
      title="Set a new password"
      subtitle="Choose a strong password to secure your account"
    >
      {error && (
        <div className="mb-4 p-3 rounded-xl bg-destructive/10 text-destructive text-xs font-semibold">
          {error}
        </div>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">New Password</label>
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <input
              type={showPw ? "text" : "password"}
              autoComplete="new-password"
              autoFocus
              placeholder="••••••••"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full pl-10 pr-11 py-3 rounded-xl bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
              required
            />
            <button type="button" onClick={() => setShowPw((v) => !v)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition p-1" aria-label={showPw ? "Hide password" : "Show password"} tabIndex={-1}>
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {/* Strength meter */}
          {newPassword.length > 0 && (
            <div className="flex gap-1 mt-2">
              {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i < strength ? (strength <= 2 ? 'bg-primary' : strength <= 3 ? 'bg-accent' : 'bg-success') : 'bg-border'}`} />
              ))}
            </div>
          )}
        </div>
        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">Confirm Password</label>
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
            <input
              type={showPw ? "text" : "password"}
              autoComplete="new-password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full pl-10 pr-11 py-3 rounded-xl bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
              required
            />
            {confirmPassword.length > 0 && (
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2">
                {match ? <Check className="w-4 h-4 text-success" /> : <span className="text-xs font-bold text-destructive">✕</span>}
              </div>
            )}
          </div>
        </div>
        <button type="submit" className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-60 active:scale-[0.98] transition-transform" disabled={loading}>
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Resetting...
            </>
          ) : (
            "Reset password"
          )}
        </button>
      </form>
    </AuthLayout>
  );
}