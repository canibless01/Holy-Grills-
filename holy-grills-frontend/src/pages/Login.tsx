import { useState, useRef, useEffect } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { Mail, Lock, ArrowRight, Check, Eye, EyeOff } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';
import { localStore } from '@/lib/storage';
import AuthShell from '@/components/auth/AuthShell';
import AuthField from '@/components/auth/AuthField';

// Role-based login — after POST /api/auth/login the user's role routes them:
// admin/super_admin → /admin, kitchen → /kitchen, rider → /rider, student → /.
const ROLE_HOME = { admin: '/admin', super_admin: '/admin', kitchen: '/kitchen', rider: '/rider', student: '/' };

// "Remember me" has two halves:
//   1. This app keeps the email address, so the sign-in screen opens pre-filled.
//   2. The password stays with the BROWSER's password manager — that is the
//      "save password?" prompt, and it is what pre-fills the password on the
//      next visit. Storing a password in localStorage would put it inside
//      reach of any script on the page, so we deliberately do not.
// For (2) to fire, Chrome/Safari/Edge need a real form submission: the fields
// must carry a `name` and the classic autocomplete tokens, and the form must be
// submitted (not have its handler called directly). Both are set up below.
const REMEMBER_FLAG = 'hg_remember';
const REMEMBER_EMAIL = 'hg_remember_email';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useHolyGrill();
  const [email, setEmail] = useState(() => localStore.getItem(REMEMBER_EMAIL) || '');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(() => localStore.getItem(REMEMBER_FLAG) === '1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showPw, setShowPw] = useState(false);
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const formRef = useRef(null);
  const autoKickedRef = useRef(false);

  const doLogin = async (emailVal, passwordVal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await login(emailVal, passwordVal);
      const role = data?.role || data?.user?.role || 'student';
      toast({ title: msg('FE_LOGIN_WELCOME_TITLE', '🔥 Welcome back!'), description: msg('FE_LOGIN_WELCOME_BODY', 'Good to see you again, {name}.', { name: data?.user?.full_name?.split(' ')[0] || 'griller' }) });
      // Role-based routing: staff (admin/kitchen/rider) ALWAYS land on their own
      // role page — never on a student route, regardless of any `from` deep-link.
      // Students return to the page they were trying to reach IF it's a student
      // route; otherwise they land on the student home.
      const isStaff = ['admin', 'super_admin', 'kitchen', 'rider'].includes(role);
      const from = location.state?.from;
      const studentRoutes = ['/', '/menu', '/cart', '/checkout', '/orders', '/track-orders', '/dashboard', '/hp-education', '/rewards', '/wallet', '/profile', '/addresses', '/notifications', '/notification-preferences', '/referrals', '/order-locks', '/streak', '/leaderboard', '/events', '/marketplace', '/faq', '/terms', '/our-story', '/hall-of-fame'];
      const isStudentRoute = (p) => studentRoutes.includes(p) || /^\/(menu|orders|marketplace|events)\//.test(p);
      let dest;
      if (isStaff) {
        dest = ROLE_HOME[role] || '/admin';
      } else if (from && isStudentRoute(from)) {
        dest = from;
      } else {
        dest = ROLE_HOME[role] || '/';
      }
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message || msg('FE_LOGIN_FAILED', 'Login failed'));
    }
    setLoading(false);
  };

  // Persist (or forget) the remembered identity. Called from the real submit
  // path only — an autofilled-but-never-submitted form must not save anything.
  const applyRemember = (shouldRemember, emailVal) => {
    if (shouldRemember) {
      localStore.setItem(REMEMBER_FLAG, '1');
      if (emailVal) localStore.setItem(REMEMBER_EMAIL, emailVal.trim());
    } else {
      localStore.removeItem(REMEMBER_FLAG);
      localStore.removeItem(REMEMBER_EMAIL);
    }
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    // Read the DOM as well as state: a browser-autofilled field fills the
    // input without ever firing React's onChange, so `email`/`password` can
    // still be empty at the moment the user (or the browser) submits.
    const emailVal = (email || emailRef.current?.value || '').trim();
    const passwordVal = password || passwordRef.current?.value || '';
    setEmail(emailVal);
    setPassword(passwordVal);
    applyRemember(remember, emailVal);
    await doLogin(emailVal, passwordVal);
  };

  const onRememberChange = (next) => {
    setRemember(next);
    // Switching it off must forget the stored identity immediately — otherwise
    // the address is still pre-filled on the next visit.
    if (!next) {
      localStore.removeItem(REMEMBER_FLAG);
      localStore.removeItem(REMEMBER_EMAIL);
    } else {
      localStore.setItem(REMEMBER_FLAG, '1');
      if (emailRef.current?.value) localStore.setItem(REMEMBER_EMAIL, emailRef.current.value.trim());
    }
  };

  // Auto-kickstart: if the browser autofilled both fields (without the user
  // typing), submit immediately instead of waiting for the Sign In press.
  // Autofill doesn't fire React onChange, so we poll the DOM values via refs.
  useEffect(() => {
    const poll = setInterval(() => {
      const eVal = emailRef.current?.value || '';
      const pVal = passwordRef.current?.value || '';
      if (eVal && pVal && !autoKickedRef.current) {
        autoKickedRef.current = true;
        setEmail(eVal);
        setPassword(pVal);
        clearInterval(poll);
        // requestSubmit() (not doLogin directly) so this counts as a real form
        // submission: it is what lets the browser's password manager see the
        // sign-in and offer to remember the password for next time.
        if (formRef.current?.requestSubmit) formRef.current.requestSubmit();
        else handleSubmit(null);
      }
    }, 250);
    const stop = setTimeout(() => clearInterval(poll), 3000);
    return () => { clearInterval(poll); clearTimeout(stop); };
  }, [remember]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <AuthShell>
      <form ref={formRef} onSubmit={handleSubmit} className="w-full bg-card rounded-2xl border border-border shadow-card p-6 space-y-4 animate-slide-up">
        <div className="text-center mb-1">
          <h1 className="font-heading font-bold text-xl text-foreground">Welcome to the fire ❤️‍🔥</h1>
          <p className="text-xs text-muted-foreground mt-1">Order. Earn. Show up.</p>
        </div>

        <AuthField
          icon={Mail}
          label="Email"
          type="email"
          name="email"
          inputRef={emailRef}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="student@futa.edu.ng"
          required
          autoComplete="username"
        />

        <AuthField
          icon={Lock}
          label="Password"
          type={showPw ? 'text' : 'password'}
          name="password"
          inputRef={passwordRef}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          required
          autoComplete="current-password"
          trailing={
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="text-muted-foreground hover:text-foreground transition p-1"
              aria-label={showPw ? 'Hide password' : 'Show password'}
              tabIndex={-1}
            >
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          }
        />

        {/* Remember me + forgot password */}
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2 cursor-pointer select-none min-w-0">
            <span className={`w-4 h-4 shrink-0 rounded-[6px] border flex items-center justify-center transition-all ${remember ? 'bg-primary border-primary' : 'border-border bg-card'}`}>
              {remember && <Check className="w-3 h-3 text-white" />}
            </span>
            <input type="checkbox" name="remember" checked={remember} onChange={(e) => onRememberChange(e.target.checked)} className="sr-only" />
            <span className="text-xs font-semibold text-muted-foreground truncate">Remember me</span>
          </label>
          <Link to="/forgot-password" className="text-xs text-muted-foreground font-semibold hover:text-primary transition shrink-0">Forgot password?</Link>
        </div>
        <p className="-mt-2 text-[11px] text-muted-foreground leading-snug">
          Keeps you signed in on this device and pre-fills your email. Your browser will offer to remember the password when you sign in.
        </p>

        {error && (
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-destructive/10 border border-destructive/20">
            <span className="text-xs text-destructive font-semibold">{error}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-60 active:scale-[0.98] transition-transform"
        >
          {loading ? (
            <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          ) : (
            <>Sign In <ArrowRight className="w-4 h-4" /></>
          )}
        </button>

        <div className="text-center pt-0.5">
          <Link to="/register" className="text-xs text-primary font-bold hover:underline">Create account →</Link>
        </div>
      </form>
    </AuthShell>
  );
}