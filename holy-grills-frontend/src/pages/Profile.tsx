import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Phone, Mail, Calendar, Lock, Bell, LogOut, ChevronRight, Shield, Trash2, Flame, MapPin as MapPinIcon, Wallet as WalletIcon, Volume2, VolumeX, Store, CalendarDays, Sparkles, Crown, GraduationCap, BookOpen, Users, X } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { liveApi } from '@/lib/liveApi';
import { useSound } from '@/lib/SoundProvider';
import { getTierProgress, formatDate } from '@/lib/hgUtils';
import ImageUploader from '@/components/admin/ImageUploader';
import TierAvatar from '@/components/TierAvatar';
import TierIcon from '@/components/TierIcon';
import ProfileSecurityPanel from '@/components/profile/ProfileSecurityPanel';

export default function Profile() {
  const navigate = useNavigate();
  const { user, hpBalance, logout, refreshUser } = useHolyGrill();
  const { soundOn, toggleSound } = useSound();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    full_name: user?.full_name || '',
    nickname: user?.profile?.nickname || user?.nickname || '',
    leaderboard_show_full_name: user?.profile?.leaderboard_show_full_name ?? user?.leaderboard_show_full_name ?? false,
    phone: user?.profile?.phone || '',
    department_id: user?.profile?.department_id || '',
    academic_level_id: user?.profile?.academic_level_id || '',
    avatar_url: user?.avatar_url || user?.profile?.avatar_url || '',
  });
  const [saving, setSaving] = useState(false);
  const [freeSideCredits, setFreeSideCredits] = useState({ count: 0, expires_at: null });
  const [exclusiveStatus, setExclusiveStatus] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [academicLevels, setAcademicLevels] = useState([]);
  const [showDelete, setShowDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteReason, setDeleteReason] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  useEffect(() => {
    (async () => {
      try { setFreeSideCredits(await liveApi.rewards.getFreeSideCredits()); } catch { /* ignore */ }
      try { setExclusiveStatus(await liveApi.hp.getExclusiveSpinStatus()); } catch { /* ignore */ }
      try { setDepartments(await liveApi.departments.list()); } catch { /* ignore */ }
      try { setAcademicLevels(await liveApi.academicLevels.list()); } catch { /* ignore */ }
    })();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const dept = departments.find((d) => d.id === form.department_id);
      const level = academicLevels.find((l) => l.id === form.academic_level_id);
      const body = {
        full_name: form.full_name,
        nickname: form.nickname.trim() || undefined,
        phone: form.phone || undefined,
        leaderboard_show_full_name: form.leaderboard_show_full_name,
        department: dept ? dept.name : undefined,
        academic_level: level ? (level.name || level.label || level.level) : undefined,
      };
      // Avatar goes through the dedicated photo route — update_profile does not
      // accept photo_url, so bundling it there silently drops the upload.
      const origAvatar = user?.avatar_url || user?.profile?.avatar_url || '';
      if (form.avatar_url && form.avatar_url !== origAvatar) {
        await liveApi.auth.updateProfilePhoto({ photo_url: form.avatar_url });
      }
      await liveApi.auth.updateProfile(body);
      await refreshUser();
      setEditing(false);
    } catch (e) { alert(e.message); }
    setSaving(false);
  };

  const handleLogout = async () => {
    if (confirm('Log out of Holy Grill?')) {
      await logout();
      navigate('/');
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteError(null);
    if (!deletePassword.trim()) { setDeleteError('Enter your password to confirm.'); return; }
    setDeleting(true);
    try {
      await liveApi.auth.deleteAccount({ password: deletePassword, reason: deleteReason.trim() || undefined });
      await logout();
      navigate('/');
    } catch (e) {
      setDeleteError(e.message || 'Could not delete account.');
    }
    setDeleting(false);
  };

  const tierInfo = hpBalance ? getTierProgress(hpBalance.hp_earned_120day) : null;

  const links = [
    { to: '/streak', icon: Flame, label: 'Check-in Streak' },
    { to: '/leaderboard', icon: Sparkles, label: 'Exclusive Spin' },
    { to: '/hall-of-fame', icon: Crown, label: 'Hall of Fame' },
    { to: '/addresses', icon: MapPinIcon, label: 'Saved Addresses' },
    { to: '/notification-preferences', icon: Bell, label: 'Notification Preferences' },
    { to: '/referrals', icon: Flame, label: 'Referrals' },
    { to: '/wallet', icon: WalletIcon, label: 'Wallet' },
    { to: '/order-locks', icon: Lock, label: 'Order Locks' },
    { to: '/squads', icon: Users, label: 'My Squads' },
  ];

  const staffLinks = [
    { to: '/marketplace', icon: Store, label: 'Marketplace' },
    { to: '/events', icon: CalendarDays, label: 'Events' },
  ];

  return (
    <div className="space-y-4 animate-fade-in">
      <h1 className="font-heading font-extrabold text-2xl text-foreground">Profile</h1>

      {/* Profile Card */}
      <div className="rounded-2xl bg-gradient-dark p-5 text-white relative overflow-hidden">
        <div className="absolute -right-6 -top-6 text-6xl opacity-10 select-none">🔥</div>
        <div className="relative flex items-center gap-3">
          <TierAvatar user={user} hpEarned120Day={hpBalance?.hp_earned_120day} size="lg" />
          <div className="flex-1 min-w-0">
            {editing ? (
              <input
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="bg-white/15 rounded-lg px-2 py-1 text-white text-lg font-bold focus:outline-none focus:ring-2 focus:ring-white/30 w-full"
              />
            ) : (
              <h2 className="font-heading font-bold text-lg truncate">{user?.full_name}</h2>
            )}
            <p className="text-xs text-white/70 truncate">{user?.email}</p>
          </div>
          {tierInfo && (
            <div className="text-right shrink-0">
              <div className="flex justify-end"><TierIcon slug={tierInfo.current.slug} tier={tierInfo.current} className="w-7 h-7" /></div>
              <div className="text-[10px] font-bold mt-0.5">{tierInfo.current.name}</div>
            </div>
          )}
        </div>
        {editing && (
          <div className="mt-3 space-y-2">
            <div className="bg-white/10 rounded-lg p-2">
              <ImageUploader value={form.avatar_url} onChange={(url) => setForm({ ...form, avatar_url: url })} folder="avatars" label="Avatar" />
            </div>
            <input
              value={form.nickname}
              onChange={(e) => setForm({ ...form, nickname: e.target.value })}
              className="w-full bg-white/15 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-white/30 placeholder-white/50"
              placeholder="Nickname (what friends call you)"
            />
            <input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              className="w-full bg-white/15 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-white/30 placeholder-white/50"
              placeholder="Phone"
            />
            <label className="flex items-start gap-2 px-1">
              <input type="checkbox" checked={form.leaderboard_show_full_name} onChange={(e) => setForm({ ...form, leaderboard_show_full_name: e.target.checked })} className="mt-0.5 w-4 h-4 accent-primary" />
              <span className="text-[11px] text-white/80 leading-relaxed">Show my full name on the leaderboard & Hall of Fame. Everything else always uses your nickname.</span>
            </label>
            <div className="grid grid-cols-2 gap-2">
              <select
                value={form.department_id}
                onChange={(e) => setForm({ ...form, department_id: e.target.value })}
                className="w-full bg-white/15 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-white/30"
              >
                <option value="" className="text-foreground">Department</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id} className="text-foreground">{d.name}</option>
                ))}
              </select>
              <select
                value={form.academic_level_id}
                onChange={(e) => setForm({ ...form, academic_level_id: e.target.value })}
                className="w-full bg-white/15 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-white/30"
              >
                <option value="" className="text-foreground">Level</option>
                {academicLevels.map((l) => (
                  <option key={l.id} value={l.id} className="text-foreground">{l.name || l.label || l.level}</option>
                ))}
              </select>
            </div>
          </div>
        )}
        <div className="mt-4 flex gap-2">
          {editing ? (
            <>
              <button onClick={handleSave} disabled={saving} className="flex-1 py-2 rounded-xl bg-white text-foreground font-bold text-xs active:scale-[0.98] transition disabled:opacity-50">
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button onClick={() => setEditing(false)} className="flex-1 py-2 rounded-xl bg-white/20 text-white font-bold text-xs active:scale-[0.98] transition">
                Cancel
              </button>
            </>
          ) : (
            <button onClick={() => setEditing(true)} className="flex-1 py-2 rounded-xl bg-white/20 text-white font-bold text-xs active:scale-[0.98] transition">
              Edit Profile
            </button>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="rounded-2xl bg-card border border-border p-4 space-y-3">
        <div className="flex items-center gap-3 text-sm">
          <Mail className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-foreground truncate">{user?.email}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Phone className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-foreground">{user?.profile?.phone || '—'}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Calendar className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-foreground">DOB: {formatDate(user?.profile?.date_of_birth)}</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Shield className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-foreground capitalize">Role: {user?.role}</span>
        </div>
        {(departments.find((d) => d.id === user?.profile?.department_id)?.name || user?.profile?.department) && (
          <div className="flex items-center gap-3 text-sm">
            <BookOpen className="w-4 h-4 text-muted-foreground shrink-0" />
            <span className="text-foreground">{departments.find((d) => d.id === user?.profile?.department_id)?.name || user?.profile?.department}</span>
          </div>
        )}
        {(academicLevels.find((l) => l.id === user?.profile?.academic_level_id)?.name || user?.profile?.academic_level) && (
          <div className="flex items-center gap-3 text-sm">
            <GraduationCap className="w-4 h-4 text-muted-foreground shrink-0" />
            <span className="text-foreground">{academicLevels.find((l) => l.id === user?.profile?.academic_level_id)?.name || academicLevels.find((l) => l.id === user?.profile?.academic_level_id)?.label || user?.profile?.academic_level}</span>
          </div>
        )}
      </div>

      {/* Rewards summary */}
      <div className="rounded-2xl bg-card border border-border p-4">
        <div className="flex items-center gap-2 mb-3">
          <Flame className="w-4 h-4 text-primary" />
          <span className="text-[11px] font-bold uppercase tracking-wide text-primary">My Rewards</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => navigate('/rewards')} className="rounded-xl bg-primary/5 p-3 text-center hover:bg-primary/10 transition">
            <div className="text-2xl">🏆</div>
            <div className="font-heading font-extrabold text-lg text-foreground">{freeSideCredits?.count ?? 0}</div>
            <div className="text-[10px] text-muted-foreground">Free side credits</div>
          </button>
          <button onClick={() => navigate('/leaderboard')} className="rounded-xl bg-muted p-3 text-center hover:bg-muted/80 transition">
            <div className="text-2xl">🎡</div>
            <div className="font-heading font-extrabold text-lg text-foreground">{exclusiveStatus?.total_spins ?? 0}</div>
            <div className="text-[10px] text-muted-foreground">Exclusive spins</div>
          </button>
        </div>
      </div>

      {/* Sound Toggle */}
      <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-border">
        <div className="w-9 h-9 rounded-full bg-primary/5 flex items-center justify-center">
          {soundOn ? <Volume2 className="w-5 h-5 text-primary" /> : <VolumeX className="w-5 h-5 text-muted-foreground" />}
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-foreground">Sound Effects</div>
          <div className="text-xs text-muted-foreground">{soundOn ? 'On, amplifying moments that matter' : 'Off'}</div>
        </div>
        <button onClick={toggleSound} className={`w-11 h-6 rounded-full p-1 transition-colors ${soundOn ? 'bg-gradient-cta' : 'bg-border'}`}>
          <div className={`w-4 h-4 rounded-full bg-card transition-transform ${soundOn ? 'translate-x-5' : ''}`} />
        </button>
      </div>

      {/* Security & Account — change password, verify email, sign out everywhere */}
      <ProfileSecurityPanel />

      {/* Quick Links */}
      <div className="space-y-1.5">
        {links.map(link => (
          <button
            key={link.to}
            onClick={() => navigate(link.to)}
            className="w-full flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-border hover:shadow-md transition-all active:scale-[0.99]"
          >
            <link.icon className="w-5 h-5 text-muted-foreground" />
            <span className="flex-1 text-left text-sm font-medium text-foreground">{link.label}</span>
            <ChevronRight className="w-4 h-4 text-foreground/30" />
          </button>
        ))}
      </div>

      {/* Explore */}
      <div className="space-y-2">
        <div className="px-1 flex items-center gap-1.5">
          <Shield className="w-3.5 h-3.5 text-primary" />
          <span className="text-[11px] font-bold uppercase tracking-wide text-primary">Explore</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {staffLinks.map((s) => (
            <button
              key={s.to}
              onClick={() => navigate(s.to)}
              className="flex items-center gap-2 p-3 rounded-2xl bg-primary/5 border border-primary/20 hover:bg-primary/10 transition-colors"
            >
              <s.icon className="w-4 h-4 text-primary" />
              <span className="text-xs font-bold text-foreground">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Danger Zone */}
      <div className="space-y-1.5">
        <button onClick={handleLogout} className="w-full flex items-center gap-3 p-3.5 rounded-2xl bg-destructive/10 border border-destructive/20 active:scale-[0.99] transition">
          <LogOut className="w-5 h-5 text-destructive" />
          <span className="flex-1 text-left text-sm font-bold text-destructive">Logout</span>
        </button>
        <button
          onClick={() => setShowDelete(true)}
          className="w-full flex items-center gap-3 p-3.5 rounded-2xl bg-card border border-border hover:shadow-sm transition"
        >
          <Trash2 className="w-5 h-5 text-muted-foreground" />
          <span className="flex-1 text-left text-sm font-medium text-muted-foreground">Delete Account</span>
        </button>
      </div>

      {/* Delete Account Modal */}
      {showDelete && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !deleting && setShowDelete(false)}>
          <div className="bg-card rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-heading font-bold text-lg text-foreground">Delete Account</h3>
              <button onClick={() => setShowDelete(false)} disabled={deleting}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <p className="text-xs text-muted-foreground mb-4 leading-relaxed">This permanently deactivates your account and removes your personal data. This action is irreversible.</p>
            <div className="space-y-3">
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                placeholder="Your password"
                className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
              />
              <input
                value={deleteReason}
                onChange={(e) => setDeleteReason(e.target.value)}
                placeholder="Reason (optional)"
                className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition"
              />
              {deleteError && (
                <div className="flex items-center gap-2 p-2.5 rounded-xl bg-destructive/10 border border-destructive/20">
                  <span className="text-xs text-destructive font-semibold">{deleteError}</span>
                </div>
              )}
              <button
                onClick={handleDeleteAccount}
                disabled={deleting}
                className="w-full py-3 rounded-xl bg-destructive text-white font-bold text-sm disabled:opacity-50 active:scale-[0.98] transition"
              >
                {deleting ? 'Deleting...' : 'Delete my account'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}