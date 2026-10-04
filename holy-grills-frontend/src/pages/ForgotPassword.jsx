import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Mail, ArrowRight, Check, ArrowLeft } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import AuthShell from '@/components/auth/AuthShell';
import AuthField from '@/components/auth/AuthField';

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setSent(false);
    try {
      await liveApi.auth.resetPassword({ email });
    } catch (err) {
      // Backend always shows generic success (hides whether email exists) —
      // surface the same success state either way so we never leak account info.
    }
    setSent(true);
    setLoading(false);
  };

  return (
    <AuthShell>
      {sent ? (
        <div className="w-full bg-card rounded-2xl border border-border shadow-card p-7 text-center animate-slide-up">
          <div className="w-16 h-16 rounded-full bg-success/15 flex items-center justify-center mx-auto mb-4">
            <Check className="w-8 h-8 text-success" />
          </div>
          <h2 className="font-heading font-bold text-lg text-foreground mb-2">Reset link sent</h2>
          <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
            If an account exists for <span className="font-semibold text-foreground">{email}</span>, a password reset link is on its way. Check your inbox and follow the instructions.
          </p>
          <button onClick={() => navigate('/login')} className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-cta text-white font-bold shadow-glow active:scale-[0.98] transition-transform">
            Back to Login <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <div className="w-full bg-card rounded-2xl border border-border shadow-card p-6 animate-slide-up">
          <button onClick={() => navigate('/login')} className="flex items-center gap-1 text-xs text-muted-foreground mb-4 hover:text-foreground transition">
            <ArrowLeft className="w-4 h-4" /> Back to login
          </button>
          <h1 className="font-heading font-bold text-xl text-foreground mb-1">Forgot your password?</h1>
          <p className="text-xs text-muted-foreground mb-5 leading-relaxed">Enter your email and we'll send you a reset link.</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <AuthField
              icon={Mail}
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="student@futa.edu.ng"
              required
              autoComplete="email"
            />
            <button type="submit" disabled={loading || !email} className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-60 active:scale-[0.98] transition-transform">
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
              ) : (
                <>Send Reset Link <ArrowRight className="w-4 h-4" /></>
              )}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground mt-5">
            Remembered it? <Link to="/login" className="text-primary font-bold hover:underline">Log in</Link>
          </p>
        </div>
      )}
    </AuthShell>
  );
}