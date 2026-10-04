import React, { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, Mail, Lock, User, Phone, Calendar, Gift, ChevronDown, AlertCircle, Info, Eye, EyeOff, BookOpen, GraduationCap, MapPin } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { liveApi } from '@/lib/liveApi';
import { getStoredCampusId } from '@/lib/campusContext';
import { toast } from '@/components/ui/use-toast';
import AuthShell from '@/components/auth/AuthShell';
import AuthField from '@/components/auth/AuthField';

const ROLE_HOME = { admin: '/admin', super_admin: '/admin', kitchen: '/kitchen', rider: '/rider', student: '/' };
const STUDENT_HOME = '/';

export default function Register() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { register } = useHolyGrill();
  const [form, setForm] = useState({
    full_name: '', nickname: '', email: searchParams.get('email') || '', password: '', confirm: '',
    phone: '', date_of_birth: '', campus_id: getStoredCampusId() || '', department_id: '', academic_level_id: '', referred_by: searchParams.get('ref') || searchParams.get('referral') || '',
  });
  const [terms, setTerms] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [departments, setDepartments] = useState([]);
  const [academicLevels, setAcademicLevels] = useState([]);
  const [campuses, setCampuses] = useState([]);

  useEffect(() => {
    (async () => {
      try { setDepartments(await liveApi.departments.list()); } catch { /* ignore */ }
      try { setAcademicLevels(await liveApi.academicLevels.list()); } catch { /* ignore */ }
      try { setCampuses(await liveApi.campuses.list()); } catch { /* ignore */ }
    })();
  }, []);

  const set = (k, v) => setForm({ ...form, [k]: v });

  const strength = (() => {
    let s = 0;
    if (form.password.length >= 8) s++;
    if (/[A-Z]/.test(form.password)) s++;
    if (/[a-z]/.test(form.password)) s++;
    if (/\d/.test(form.password)) s++;
    if (/[^A-Za-z0-9]/.test(form.password)) s++;
    return s;
  })();

  // Only guard the form's own integrity here — never the business rules.
  // Age, password policy, phone format and every other rule belong to the
  // backend: it decides what is valid and its message is what the user sees.
  const validate = () => {
    if (!form.full_name.trim()) return 'Please enter your full name';
    if (!form.email.trim()) return 'Please enter your email';
    if (!form.password) return 'Please enter a password';
    if (form.password !== form.confirm) return 'Passwords do not match';
    if (!terms) return 'Please accept the Terms & Conditions';
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    const v = validate();
    if (v) { setError(v); return; }
    setLoading(true);
    try {
      const phone = form.phone.startsWith('0') ? '+234' + form.phone.slice(1) : form.phone;
      const data = await register({
        full_name: form.full_name,
        nickname: form.nickname.trim() || undefined,
        email: form.email.toLowerCase(),
        password: form.password,
        phone,
        date_of_birth: form.date_of_birth,
        campus_id: form.campus_id || undefined,
        department: departments.find((d) => d.id === form.department_id)?.name || undefined,
        academic_level: (() => { const l = academicLevels.find((x) => x.id === form.academic_level_id); return l ? (l.value || l.name || l.label || l.level) : undefined; })(),
        referred_by_code: form.referred_by || undefined,
      });
      // check_email — account created, email verification required. Show as
      // info (not an error) with login + reset-password links beneath it.
      if (data?.status === 'check_email') {
        setInfo(data.message || 'Check your email to verify your account, then log in.');
        setLoading(false);
        return;
      }
      toast({ title: "You're in ❤️‍🔥", description: 'Welcome to Holy Grills.' });
      const role = data?.role || data?.user?.role || 'student';
      const isStaff = ['admin', 'super_admin', 'kitchen', 'rider'].includes(role);
      window.location.href = isStaff ? (ROLE_HOME[role] || '/admin') : STUDENT_HOME;
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  return (
    <AuthShell>
      <form onSubmit={handleSubmit} className="w-full bg-card rounded-2xl border border-border shadow-card p-6 space-y-3.5 animate-slide-up">
        <div className="text-center mb-1">
          <h1 className="font-heading font-bold text-xl text-foreground">Join Holy Grills</h1>
          <p className="text-xs text-muted-foreground mt-1">Start showing up.</p>
        </div>

        <AuthField icon={User} label="Full Name" value={form.full_name} onChange={(e) => set('full_name', e.target.value)} placeholder="Jane Doe" autoComplete="name" />
        <AuthField icon={User} label="Nickname (optional)" value={form.nickname} onChange={(e) => set('nickname', e.target.value)} placeholder="e.g. Speedy" />

        <AuthField icon={Mail} label="Email" type="email" value={form.email} onChange={(e) => set('email', e.target.value)} placeholder="student@futa.edu.ng" autoComplete="email" />

        <AuthField icon={Phone} label="Phone Number" type="tel" value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="08012345678 or +2348012345678" autoComplete="tel" />

        {/* Campus — Domain 0 multi-tenancy. Prefilled from the guest gate
            selection; user can confirm/switch. Sent as campus_id on register. */}
        {campuses.length > 0 && (
          <SelectField icon={MapPin} label="Campus" value={form.campus_id} onChange={(e) => set('campus_id', e.target.value)} placeholder="Pick your campus">
            {campuses.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </SelectField>
        )}

        <AuthField icon={Calendar} label="When's your birthday?" type="date" value={form.date_of_birth} onChange={(e) => set('date_of_birth', e.target.value)} />

        <SelectField icon={BookOpen} label="What are you studying?" value={form.department_id || ''} onChange={(e) => set('department_id', e.target.value)} placeholder="Pick your department">
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </SelectField>

        <SelectField icon={GraduationCap} label="Your level" value={form.academic_level_id || ''} onChange={(e) => set('academic_level_id', e.target.value)} placeholder="Pick your level">
          {academicLevels.map((l) => (
            <option key={l.id} value={l.id}>{l.name || l.label || l.level}</option>
          ))}
        </SelectField>

        <AuthField
          icon={Lock}
          label="Password (min 8, uppercase + number + special)"
          type={showPw ? 'text' : 'password'}
          value={form.password}
          onChange={(e) => set('password', e.target.value)}
          placeholder="••••••••"
          autoComplete="new-password"
          trailing={
            <button type="button" onClick={() => setShowPw((v) => !v)} className="text-muted-foreground hover:text-foreground transition p-1" aria-label={showPw ? 'Hide password' : 'Show password'} tabIndex={-1}>
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          }
        />
        {form.password.length > 0 && (
          <div className="flex gap-1 -mt-1">
            {[0, 1, 2, 3, 4].map((i) => (
              <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i < strength ? (strength <= 2 ? 'bg-primary' : strength <= 3 ? 'bg-accent' : 'bg-success') : 'bg-border'}`} />
            ))}
          </div>
        )}

        <AuthField
          icon={Lock}
          label="Confirm Password"
          type={showConfirm ? 'text' : 'password'}
          value={form.confirm}
          onChange={(e) => set('confirm', e.target.value)}
          placeholder="••••••••"
          autoComplete="new-password"
          trailing={
            <button type="button" onClick={() => setShowConfirm((v) => !v)} className="text-muted-foreground hover:text-foreground transition p-1" aria-label={showConfirm ? 'Hide password' : 'Show password'} tabIndex={-1}>
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          }
        />

        <AuthField icon={Gift} label="Referral Code (optional)" value={form.referred_by} onChange={(e) => set('referred_by', e.target.value.toUpperCase())} placeholder="JANE123" />

        <label className="flex items-start gap-2.5 p-3 rounded-xl bg-beige-soft/60 border border-border cursor-pointer">
          <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} className="mt-0.5 w-4 h-4 accent-primary shrink-0" />
          <span className="text-[11px] text-foreground leading-relaxed">
            I agree to the <Link to="/terms" className="text-primary font-bold">Terms & Conditions</Link> and confirm I'm at least 16 years old. I consent to receive order notifications and marketing offers.
          </span>
        </label>

        {error && (
          <div className="flex items-center gap-2 p-2.5 rounded-xl bg-destructive/10 border border-destructive/20">
            <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
            <span className="text-xs text-destructive font-semibold">{error}</span>
          </div>
        )}

        {info && (
          <div className="space-y-2">
            <div className="flex items-start gap-2 p-2.5 rounded-xl bg-accent/10 border border-accent/20">
              <Info className="w-4 h-4 text-accent shrink-0 mt-0.5" />
              <span className="text-xs text-foreground font-medium leading-relaxed">{info}</span>
            </div>
            <div className="flex items-center gap-3 text-xs px-1">
              <Link to="/login" className="text-primary font-bold hover:underline">Log in</Link>
              <span className="text-muted-foreground">·</span>
              <Link to="/forgot-password" className="text-primary font-bold hover:underline">Reset password</Link>
            </div>
          </div>
        )}

        <button type="submit" disabled={loading} className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-60 active:scale-[0.98] transition-transform">
          {loading ? (
            <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          ) : (
            <>Create Account <ArrowRight className="w-4 h-4" /></>
          )}
        </button>
      </form>

      <p className="text-center text-sm text-muted-foreground mt-5">
        Already have an account?{' '}
        <Link to="/login" className="text-primary font-bold hover:underline">Log in</Link>
      </p>
    </AuthShell>
  );
}

function SelectField({ icon: Icon, label, value, onChange, placeholder, children }) {
  return (
    <div>
      <label className="block text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">{label}</label>
      <div className="relative">
        <Icon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        <select
          value={value}
          onChange={onChange}
          className="w-full pl-10 pr-9 py-3 rounded-xl bg-card border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition appearance-none"
        >
          <option value="">{placeholder}</option>
          {children}
        </select>
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
      </div>
    </div>
  );
}