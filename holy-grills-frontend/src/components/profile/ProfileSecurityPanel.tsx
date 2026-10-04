import { useState } from 'react';
import { KeyRound, MailCheck, LogOut, ChevronDown, ChevronUp, Eye, EyeOff, Loader2, ShieldCheck } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';

// Security & Account actions backed by dedicated auth routes that previously
// had no UI entry point:
//   • POST /auth/change-password      { current_password, new_password }
//   • POST /auth/verify-email          (resends the verification link)
//   • POST /auth/logout-all-devices    (revokes every session, signs this device out)
// Each action surfaces the backend's own response message verbatim.
export default function ProfileSecurityPanel() {
  const [openPw, setOpenPw] = useState(false);
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' });
  const [showCur, setShowCur] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const [pwError, setPwError] = useState(null);

  const [verifying, setVerifying] = useState(false);
  const [loggingOutAll, setLoggingOutAll] = useState(false);

  const handleChangePassword = async () => {
    setPwError(null);
    if (!pw.current) { setPwError('Enter your current password.'); return; }
    if (pw.next.length < 8) { setPwError('New password must be at least 8 characters.'); return; }
    if (pw.next !== pw.confirm) { setPwError('New passwords do not match.'); return; }
    setChangingPw(true);
    try {
      const res = await liveApi.auth.changePassword({ current_password: pw.current, new_password: pw.next });
      toast({ title: '✅ Password updated', description: res?.message || 'Your password has been changed.' });
      setPw({ current: '', next: '', confirm: '' });
      setOpenPw(false);
    } catch (e) {
      setPwError(e.message || 'Could not change password.');
    } finally {
      setChangingPw(false);
    }
  };

  const handleVerifyEmail = async () => {
    setVerifying(true);
    try {
      const res = await liveApi.auth.verifyEmail({});
      toast({ title: '📬 Verification email sent', description: res?.message || 'Check your inbox for the verification link.' });
    } catch (e) {
      toast({ title: 'Could not resend', description: e.message, variant: 'destructive' });
    } finally {
      setVerifying(false);
    }
  };

  const handleLogoutAll = async () => {
    if (!confirm("Sign out of every device? You will be logged out here too.")) return;
    setLoggingOutAll(true);
    try {
      await liveApi.auth.logoutAll();
      window.location.href = '/login';
    } catch (e) {
      toast({ title: 'Could not sign out everywhere', description: e.message, variant: 'destructive' });
      setLoggingOutAll(false);
    }
  };

  return (
    <div className="rounded-2xl bg-card border border-border overflow-hidden">
      <div className="flex items-center gap-2 px-4 pt-4 pb-2">
        <ShieldCheck className="w-4 h-4 text-primary" />
        <span className="text-[11px] font-bold uppercase tracking-wide text-primary">Security & Account</span>
      </div>

      {/* Change password — expandable inline form */}
      <div className="border-t border-border">
        <button
          onClick={() => setOpenPw((v) => !v)}
          className="w-full flex items-center gap-3 p-3.5 hover:bg-muted/50 transition"
        >
          <KeyRound className="w-5 h-5 text-muted-foreground" />
          <span className="flex-1 text-left text-sm font-medium text-foreground">Change password</span>
          {openPw ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </button>
        {openPw && (
          <div className="px-4 pb-4 space-y-2.5 bg-muted/30">
            <div className="relative">
              <input
                type={showCur ? 'text' : 'password'}
                value={pw.current}
                onChange={(e) => setPw({ ...pw, current: e.target.value })}
                placeholder="Current password"
                autoComplete="current-password"
                className="w-full pl-3 pr-10 py-2.5 rounded-xl bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
              />
              <button type="button" onClick={() => setShowCur((v) => !v)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground p-1">
                {showCur ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <div className="relative">
              <input
                type={showNew ? 'text' : 'password'}
                value={pw.next}
                onChange={(e) => setPw({ ...pw, next: e.target.value })}
                placeholder="New password (min 8)"
                autoComplete="new-password"
                className="w-full pl-3 pr-10 py-2.5 rounded-xl bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
              />
              <button type="button" onClick={() => setShowNew((v) => !v)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground p-1">
                {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <input
              type={showNew ? 'text' : 'password'}
              value={pw.confirm}
              onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
              placeholder="Confirm new password"
              autoComplete="new-password"
              className="w-full pl-3 pr-3 py-2.5 rounded-xl bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
            />
            {pwError && (
              <div className="flex items-center gap-2 p-2.5 rounded-xl bg-destructive/10 border border-destructive/20">
                <span className="text-xs text-destructive font-semibold">{pwError}</span>
              </div>
            )}
            <button
              onClick={handleChangePassword}
              disabled={changingPw}
              className="w-full py-2.5 rounded-xl bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 active:scale-[0.98] transition flex items-center justify-center gap-2"
            >
              {changingPw ? <><Loader2 className="w-4 h-4 animate-spin" /> Updating…</> : 'Update password'}
            </button>
          </div>
        )}
      </div>

      {/* Resend email verification */}
      <div className="border-t border-border">
        <button
          onClick={handleVerifyEmail}
          disabled={verifying}
          className="w-full flex items-center gap-3 p-3.5 hover:bg-muted/50 transition disabled:opacity-50"
        >
          <MailCheck className="w-5 h-5 text-muted-foreground" />
          <span className="flex-1 text-left text-sm font-medium text-foreground">Resend email verification</span>
          {verifying ? <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" /> : null}
        </button>
      </div>

      {/* Sign out all devices */}
      <div className="border-t border-border">
        <button
          onClick={handleLogoutAll}
          disabled={loggingOutAll}
          className="w-full flex items-center gap-3 p-3.5 hover:bg-destructive/5 transition disabled:opacity-50"
        >
          <LogOut className="w-5 h-5 text-destructive" />
          <span className="flex-1 text-left text-sm font-medium text-destructive">Sign out all devices</span>
          {loggingOutAll ? <Loader2 className="w-4 h-4 animate-spin text-destructive" /> : null}
        </button>
      </div>
    </div>
  );
}