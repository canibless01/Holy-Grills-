import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  Flame,
  Wallet,
  Check,
  X,
  Package,
  Plus,
  Users as UsersIcon,
  Send,
  Mail,
  Phone,
  RefreshCw,
  History,
  AlertTriangle,
  UserX,
  UserCheck,
  User as UserIcon,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { hpTierName, safeText } from '@/lib/valueText';
import { formatNaira, timeAgo, ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/lib/hgUtils';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Pill, Pagination, body } from './ui/AdminKit';
import { msg } from '@/lib/messages';
import { useCampus } from '@/lib/campusContext';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';

const ROLES = [
  { value: 'student', label: 'Student' },
  { value: 'kitchen', label: 'Kitchen' },
  { value: 'rider', label: 'Rider' },
  { value: 'admin', label: 'Admin' },
  { value: 'community_manager', label: msg('FE_ROLE_COMMUNITY_MANAGER', 'Community Manager') },
  { value: 'super_admin', label: 'Super Admin' },
];
const PAGE_SIZE = 24;

// The backend occasionally returns a nested object where the UI expects text
// (a tier, a status, a transaction type). Rendering that object as a React
// child would take the whole drawer down, so every such value is coerced to
// display text first. safeText() walks up to four levels deep, which covers
// the HP balance's twice-nested tier row.
const txt = (v, fallback = '') => safeText(v, fallback) || fallback;

// Tier label — always a string or null, never the backend's tier container.
// (get_hp_balance nests the hp_tiers row two levels deep; returning it as-is
// crashed the drawer with "Objects are not valid as a React child".)
const tierLabel = (u) => hpTierName(u?.tier_name ?? u?.tier ?? u?.tier_info);

// User Directory — GET /admin/users (q, role, limit, offset) · role changes
// (PATCH /admin/users/:id/role) · activate/deactivate · per-user HP ledger,
// wallet history and order history from their dedicated admin endpoints.
export default function AdminUsers() {
  const { user: me } = useHolyGrill();
  const { adminCampusId } = useCampus();
  const campusId = me?.role === 'super_admin' ? adminCampusId : me?.campus_id || me?.profile?.campus_id;
  return <UserWorkspace key={campusId || 'global'} campusId={campusId} />;
}

function UserWorkspace({ campusId }) {
  const { user: me } = useHolyGrill();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [updating, setUpdating] = useState(null);
  const [selected, setSelected] = useState(null);
  const [confirmToggle, setConfirmToggle] = useState(null);
  const [bulkMode, setBulkMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const selectedRows = useRef(new Map());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const latestLoad = useRef(0);
  const [roleChange, setRoleChange] = useState(null);
  const [roleCampuses, setRoleCampuses] = useState([]);
  const [roleCampusId, setRoleCampusId] = useState('');

  const load = async () => {
    const intent = ++latestLoad.current;
    setLoading(true);
    setLoadError(false);
    try {
      const res = await liveApi.admin.getUsers({
        campus_id: campusId || undefined,
        q: search || undefined,
        role: roleFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      if (intent !== latestLoad.current) return;
      setUsers(res);
      setHasMore(res.length === PAGE_SIZE);
    } catch (e) {
      if (intent !== latestLoad.current) return;
      toast({ title: msg('FE_ADMIN_USERS_COULDN_T_LOAD_USERS', "Couldn't load users"), description: e.message, variant: 'destructive' });
      setLoadError(true);
    }
    setLoading(false);
  };

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => { clearTimeout(t); latestLoad.current++; };
  }, [search, roleFilter, page, campusId]);

  const onSearchInput = (v) => { setSearch(v); if (page !== 0) setPage(0); };
  const onRoleFilter = (v) => { setRoleFilter(v); if (page !== 0) setPage(0); };

  // PATCH /admin/users/:id/role — backend rejects self-changes and
  // non-super-admin → super_admin; mirrored client-side for instant feedback.
  const handleRole = async (u, role, campusId = null) => {
    if (role === u.role) return;
    if (u.id === me?.id) {
      toast({ title: msg('FE_ADMIN_USERS_NOT_ALLOWED', 'Not allowed'), description: msg('FE_ADMIN_USERS_YOU_CANNOT_CHANGE_YOUR_OWN_ROLE', 'You cannot change your own role.'), variant: 'destructive' });
      return;
    }
    if (role === 'super_admin' && me?.role !== 'super_admin') {
      toast({ title: msg('FE_ADMIN_USERS_NOT_ALLOWED', 'Not allowed'), description: msg('FE_ADMIN_USERS_ONLY_A_SUPER_ADMIN_CAN_ASSIGN_THE_SUPER', 'Only a super admin can assign the super_admin role.'), variant: 'destructive' });
      return;
    }
    if (role !== 'super_admin' && !u.campus_id && !campusId) {
      try {
        setRoleCampuses((await liveApi.admin.getCampuses()).filter(c => c.is_active !== false));
        setRoleCampusId('');
        setRoleChange({ user: u, role });
      } catch (e) {
        toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: e.message, variant: 'destructive' });
      }
      return;
    }
    setUpdating(u.id);
    try {
      await liveApi.admin.updateRole(u.id, { role, ...(campusId ? { campus_id: campusId } : {}) });
      setRoleChange(null);
      toast({ title: msg('FE_ADMIN_USERS_ROLE_UPDATED', 'Role updated'), description: msg('FE_ADMIN_USERS_NAME_IS_NOW_VALUE', '{name} is now {value}.', { name: u.full_name, value: role.replace('_', ' ') }) });
      load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_USERS_ROLE_CHANGE_FAILED', 'Role change failed'), description: e.message, variant: 'destructive' });
    }
    setUpdating(null);
  };

  // POST /admin/users/:id/deactivate | /activate — backend blocks self-
  // deactivation and non-super-admin deactivating a super_admin.
  const handleToggle = async (u) => {
    if (u.id === me?.id) {
      toast({ title: msg('FE_ADMIN_USERS_NOT_ALLOWED', 'Not allowed'), description: msg('FE_ADMIN_USERS_YOU_CANNOT_DEACTIVATE_YOUR_OWN_ACCOUNT', 'You cannot deactivate your own account.'), variant: 'destructive' });
      setConfirmToggle(null);
      return;
    }
    setUpdating(u.id);
    try {
      await (u.is_active ? liveApi.admin.deactivateUser(u.id) : liveApi.admin.activateUser(u.id));
      toast({ title: u.is_active ? 'Account deactivated' : 'Account reactivated', description: u.full_name });
      setConfirmToggle(null);
      load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_USERS_ACTION_FAILED', 'Action failed'), description: e.message, variant: 'destructive' });
      setConfirmToggle(null);
    }
    setUpdating(null);
  };

  const toggleSelect = (id) => {
    const next = new Set(selectedIds);
    if (next.has(id)) { next.delete(id); selectedRows.current.delete(id); }
    else { next.add(id); selectedRows.current.set(id, users.find(user => user.id === id)); }
    setSelectedIds(next);
  };

  if (loadError) return <div className="py-10 text-center space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card className="p-3 flex flex-col lg:flex-row gap-2.5 lg:items-center">
        <div className="relative flex-1 min-w-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => onSearchInput(e.target.value)}
            aria-label={msg('FE_USER_SEARCH', 'Search by name, phone or email…')} placeholder={msg('FE_USER_SEARCH', 'Search by name, phone or email…')}
            className="w-full pl-10 pr-9 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          {search && (
            <button onClick={() => onSearchInput('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-secondary active:scale-95 transition">
              <X className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
        <select
          aria-label={msg('FE_USER_ROLE_FILTER', 'Role filter')}
          value={roleFilter}
          onChange={(e) => onRoleFilter(e.target.value)}
          className="px-4 py-2.5 rounded-xl border border-border bg-card text-sm font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">All roles</option>
          {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <button
          onClick={() => { setBulkMode(!bulkMode); setSelectedIds(new Set()); }}
          className={`flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-bold active:scale-95 transition ${bulkMode ? 'bg-primary text-white shadow-glow' : 'bg-secondary text-secondary-foreground hover:bg-primary/10 hover:text-primary'}`}
        >
          <UsersIcon className="w-4 h-4" /> {bulkMode ? 'Exit bulk' : 'Bulk'}
        </button>
        {bulkMode && selectedIds.size > 0 && (
          <button
            onClick={() => setBulkOpen(true)}
            className="flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition"
          >
            <Send className="w-4 h-4" /> Grant HP ({selectedIds.size})
          </button>
        )}
      </Card>

      {/* List */}
      {loading && users.length === 0 ? (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="p-4 space-y-3">
              <div className="flex items-center gap-3">
                <Skeleton className="w-10 h-10 rounded-full" />
                <div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-2/3" /><Skeleton className="h-3 w-1/2" /></div>
              </div>
              <Skeleton className="h-3 w-1/3" />
              <Skeleton className="h-9 w-full" />
            </Card>
          ))}
        </div>
      ) : users.length === 0 ? (
        <Card>
          <EmptyState
            icon={UsersIcon}
            title="No users found"
            body={search || roleFilter ? 'Try a different search term or clear the filters.' : 'Users appear here as they sign up.'}
            action={
              (search || roleFilter) ? (
                <button onClick={() => { setSearch(''); onRoleFilter(''); }} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
                  <RefreshCw className="w-3.5 h-3.5" /> Clear filters
                </button>
              ) : null
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {users.map((u, i) => {
              const tier = tierLabel(u);
              const isSelf = u.id === me?.id;
              return (
                <motion.div key={u.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.2), duration: 0.25 }}>
                  <Card className={`p-4 space-y-3 h-full transition-all ${selectedIds.has(u.id) ? 'ring-2 ring-primary/50 border-primary/40' : 'hover:border-primary/30'}`}>
                    <div className="flex items-center gap-3">
                      {bulkMode && (
                        <button
                          aria-label={msg('FE_USER_SELECT', 'Select {name}', { name: u.full_name })}
                          aria-pressed={selectedIds.has(u.id)}
                          onClick={() => toggleSelect(u.id)}
                          className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 active:scale-95 transition ${selectedIds.has(u.id) ? 'bg-primary border-primary' : 'border-input bg-card'}`}
                        >
                          {selectedIds.has(u.id) && <Check className="w-3 h-3 text-white" />}
                        </button>
                      )}
                      <button onClick={() => !bulkMode && setSelected(u)} className="flex items-center gap-3 text-left min-w-0 flex-1 group">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-extrabold shrink-0 ${u.is_active ? 'bg-gradient-cta text-white' : 'bg-secondary text-muted-foreground'}`}>
                          {(u.full_name || '?').charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-bold text-sm text-foreground truncate group-hover:text-primary transition-colors">{u.full_name || 'Unnamed'}</div>
                          <div className="text-[11px] text-muted-foreground truncate">{u.phone || u.email || '—'}</div>
                        </div>
                      </button>
                    </div>

                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Pill tone={u.role === 'admin' || u.role === 'super_admin' ? 'flame' : u.role === 'kitchen' ? 'amber' : u.role === 'rider' ? 'outline' : 'cocoa'}>
                        {(u.role || 'student').replace('_', ' ')}
                      </Pill>
                      {tier && <Pill tone="green">🔥 {tier}</Pill>}
                      {!u.is_active && <Pill tone="red">INACTIVE</Pill>}
                      {isSelf && <Pill tone="outline">YOU</Pill>}
                    </div>

                    <div className="flex items-center gap-4 text-xs font-bold">
                      <span className="flex items-center gap-1 text-primary"><Flame className="w-3.5 h-3.5" />{Number(u.hp_balance ?? 0).toLocaleString()} HP</span>
                      <span className="flex items-center gap-1 text-success"><Wallet className="w-3.5 h-3.5" />{formatNaira(u.wallet_balance ?? 0)}</span>
                    </div>

                    <div className="flex gap-1.5">
                      <select
                        value={u.role || 'student'}
                        onChange={(e) => handleRole(u, e.target.value)}
                        disabled={updating === u.id || isSelf || (me?.role !== 'super_admin' && ['admin', 'super_admin', 'community_manager'].includes(u.role))}
                        title={isSelf ? 'You cannot change your own role' : 'Change role'}
                        className="flex-1 min-w-0 text-xs px-2.5 py-2 rounded-xl border border-border bg-card text-foreground font-bold focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50"
                      >
                        {ROLES.filter((r) => r.value === u.role || me?.role === 'super_admin' || !['admin', 'super_admin', 'community_manager'].includes(r.value)).map((r) => (
                          <option key={r.value} value={r.value}>{r.label}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => (u.is_active ? setConfirmToggle(u) : handleToggle(u))}
                        disabled={updating === u.id || isSelf || (['admin', 'super_admin'].includes(u.role) && me?.role !== 'super_admin')}
                        title={isSelf ? msg('FE_ADMIN_USERS_YOU_CANNOT_DEACTIVATE_YOUR_OWN_ACCOUNT', 'You cannot deactivate your own account.')
                          : ['admin', 'super_admin'].includes(u.role) && me?.role !== 'super_admin'
                          ? msg('FE_USER_ADMIN_ACCOUNT_SUPER_ONLY', 'Only a super admin can change this admin account.')
                          : u.is_active ? 'Deactivate account' : 'Reactivate account'}
                        className={`px-3 py-2 rounded-xl text-xs font-bold flex items-center justify-center active:scale-95 transition disabled:opacity-50 ${u.is_active ? 'text-destructive bg-destructive/10 hover:bg-destructive/20' : 'text-success bg-success/10 hover:bg-success/20'}`}
                      >
                        {updating === u.id
                          ? <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                          : u.is_active ? <UserX className="w-3.5 h-3.5" /> : <UserCheck className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </div>

          {(page > 0 || hasMore) && (
            <Card className="p-3">
              <Pagination page={page} canPrev={page > 0} canNext={hasMore} onPrev={() => setPage((p) => Math.max(0, p - 1))} onNext={() => setPage((p) => p + 1)} busy={loading} />
            </Card>
          )}
        </>
      )}

      <AnimatePresence>
        {roleChange && <Modal open onClose={() => setRoleChange(null)} title={msg('FE_ROLE_CAMPUS_REQUIRED', "Choose the user's campus")}><div className="space-y-3"><Field label={msg('FE_ROLE_CAMPUS', 'Campus')}><select value={roleCampusId} onChange={e => setRoleCampusId(e.target.value)} className="w-full p-3 border border-border rounded-xl"><option value="">{msg('FE_ROLE_SELECT_CAMPUS', 'Select a campus')}</option>{roleCampuses.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field><button disabled={!roleCampusId || updating === roleChange.user.id} onClick={() => handleRole(roleChange.user, roleChange.role, roleCampusId)} className="w-full p-3 rounded-full bg-primary text-white font-bold disabled:opacity-50">{msg('FE_ROLE_SAVE', 'Save role')}</button></div></Modal>}
        {selected && <UserDrawer key={selected.id} user={selected} onClose={() => setSelected(null)} onUserUpdated={load} />}
      </AnimatePresence>

      {bulkOpen && (
        <BulkGrantModal
          userIds={[...selectedIds]}
          users={[...selectedIds].map(id => selectedRows.current.get(id)).filter(Boolean)}
          campusId={campusId}
          onClose={() => setBulkOpen(false)}
          onDone={() => { setBulkOpen(false); setSelectedIds(new Set()); load(); }}
        />
      )}

      {/* Destructive confirmation — deactivate */}
      <Modal open={!!confirmToggle} onClose={() => setConfirmToggle(null)} title="Deactivate account?">
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl bg-destructive/10 border border-destructive/20 p-3.5">
            <AlertTriangle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
            <div className="text-xs text-foreground leading-relaxed">
              <b>{confirmToggle?.full_name}</b> will lose access to the app until reactivated. Their HP, wallet and order history are preserved.
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setConfirmToggle(null)} className="flex-1 py-2.5 rounded-full bg-secondary text-secondary-foreground text-sm font-bold active:scale-95 transition">Cancel</button>
            <button onClick={() => handleToggle(confirmToggle)} className="flex-1 py-2.5 rounded-full bg-destructive text-white text-sm font-bold active:scale-95 transition">Deactivate</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// Full user profile + lazy HP / wallet / orders tabs.
// GET /admin/users/:id (profile) · /hp · /wallet · /orders — each fetched on
// demand, rendered against the documented response fields with guards.
function UserDrawer({ user, onClose, onUserUpdated }) {
  const [tab, setTab] = useState('hp');
  const [profile, setProfile] = useState(null);
  const [hp, setHp] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [orders, setOrders] = useState(null);
  const [grantOpen, setGrantOpen] = useState(false);
  const [tabLoading, setTabLoading] = useState(true);
  const [tabError, setTabError] = useState(false);
  const tabGeneration = useRef(0);

  const loadTab = async (t) => {
    const current = ++tabGeneration.current;
    setTab(t); setTabLoading(true); setTabError(false);
    try {
      const value = t === 'hp' ? await liveApi.admin.getUserHp(user.id) : t === 'wallet' ? await liveApi.admin.getUserWallet(user.id) : await liveApi.admin.getUserOrders(user.id, { limit: 50 });
      if (current !== tabGeneration.current) return;
      if (t === 'hp') setHp(value); else if (t === 'wallet') setWallet(value); else setOrders(value);
    } catch (e) {
      if (current !== tabGeneration.current) return;
      setTabError(true);
      toast({ title: msg('FE_ADMIN_USERS_COULDN_T_LOAD_THIS_TAB', "Couldn't load this tab"), description: e.message, variant: 'destructive' });
    }
    if (current === tabGeneration.current) setTabLoading(false);
  };

  useEffect(() => {
    // Full profile — endpoint previously wired in the client but never used.
    (async () => {
      try {
        const raw = await liveApi.admin.getUser(user.id);
        setProfile(raw?.user || raw?.profile || body(raw));
      } catch { /* profile context is optional — the drawer still works */ }
    })();
    loadTab('hp');
    return () => { tabGeneration.current++; };
  }, [user.id]);

  const walletBalance = wallet ? (wallet.wallet_balance ?? wallet.balance ?? 0) : null;
  const walletCurrency = (wallet && wallet.currency) || 'NGN';
  const walletTxs = wallet ? (wallet.transactions || wallet.wallet_transactions || wallet.history || []) : [];
  const hpTxs = Array.isArray(hp?.transactions) ? hp.transactions : [];
  const contact = profile || user;
  // Orders can stay null if that tab's fetch fails — guard the render so a
  // failed request shows the empty state instead of crashing the drawer.
  const orderList = Array.isArray(orders) ? orders : [];

  return (
    <ModalPortal>
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-end sm:items-stretch sm:justify-end hg-scrim"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 320, damping: 32 }}
        role="dialog" aria-modal="true" aria-label={user.full_name || msg('FE_USER_PROFILE', 'User profile')}
        className="w-full sm:max-w-md bg-card h-[88vh] sm:h-full rounded-t-3xl sm:rounded-none overflow-y-auto shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-card border-b border-border px-5 py-4 flex items-center gap-3 z-10">
          <div className="w-10 h-10 rounded-full bg-gradient-cta text-white flex items-center justify-center font-extrabold shrink-0">
            {(user.full_name || '?').charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="font-extrabold text-sm text-foreground truncate">{user.full_name || 'Unnamed'}</div>
            <div className="text-[11px] text-muted-foreground truncate">{contact.email || contact.phone || '—'}</div>
          </div>
          <button aria-label={msg('FE_USER_CLOSE_PROFILE', 'Close profile')} onClick={onClose} className="p-2 -mr-2 rounded-xl hover:bg-secondary active:scale-95 transition">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Profile meta — only fields the backend actually returns */}
          <div className="grid grid-cols-2 gap-2 text-[11px] font-semibold">
            {contact.email && <div className="flex items-center gap-1.5 text-muted-foreground min-w-0"><Mail className="w-3.5 h-3.5 text-primary shrink-0" /><span className="truncate">{contact.email}</span></div>}
            {contact.phone && <div className="flex items-center gap-1.5 text-muted-foreground min-w-0"><Phone className="w-3.5 h-3.5 text-primary shrink-0" /><span className="truncate">{contact.phone}</span></div>}
            {contact.campus && <div className="flex items-center gap-1.5 text-muted-foreground min-w-0"><UserIcon className="w-3.5 h-3.5 text-primary shrink-0" /><span className="truncate">{typeof contact.campus === 'string' ? contact.campus : (contact.campus?.name || '')}</span></div>}
            {contact.created_at && <div className="flex items-center gap-1.5 text-muted-foreground min-w-0"><History className="w-3.5 h-3.5 text-primary shrink-0" /><span>Joined {timeAgo(contact.created_at)}</span></div>}
          </div>

          {/* Snapshot stats */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-xl bg-primary/10 border border-primary/20 p-2.5 text-center">
              <Flame className="w-4 h-4 text-primary mx-auto mb-1" />
              <div className="font-extrabold text-sm text-foreground">{hp ? Number(hp.total ?? 0).toLocaleString() : '—'}</div>
              <div className="text-[10px] font-bold text-muted-foreground">HP</div>
            </div>
            <div className="rounded-xl bg-success/15 border border-success/25 p-2.5 text-center">
              <Wallet className="w-4 h-4 text-success mx-auto mb-1" />
              <div className="font-extrabold text-sm text-foreground">{walletBalance != null ? formatNaira(walletBalance) : '—'}</div>
              <div className="text-[10px] font-bold text-muted-foreground">{walletCurrency}</div>
            </div>
            <div className="rounded-xl bg-accent/25 border border-accent/40 p-2.5 text-center">
              <Package className="w-4 h-4 text-accent-foreground mx-auto mb-1" />
              <div className="font-extrabold text-sm text-foreground">{orders ? orders.length : '—'}</div>
              <div className="text-[10px] font-bold text-muted-foreground">Orders</div>
            </div>
          </div>

          <button onClick={() => setGrantOpen(true)} className="flex items-center justify-center gap-1.5 w-full py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold active:scale-95 transition shadow-glow">
            <Plus className="w-4 h-4" /> {msg('FE_USER_GRANT_BUTTON', 'Grant HP')}
          </button>

          {/* Tabs */}
          <div className="flex gap-1 p-1 rounded-full bg-secondary border border-border">
            {[
              { id: 'hp', label: 'HP History' },
              { id: 'wallet', label: 'Wallet' },
              { id: 'orders', label: 'Orders' },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => loadTab(t.id)}
                className={`flex-1 py-2 rounded-full text-xs font-bold transition-all active:scale-95 ${tab === t.id ? 'bg-card text-primary shadow-card' : 'text-muted-foreground hover:text-foreground'}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {tabLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}
            </div>
          ) : tabError ? <div role="alert" className="space-y-3 text-sm"><p>{msg('FE_USER_TAB_FAILED', 'This history could not be loaded. Retry to see the current records.')}</p><button onClick={() => loadTab(tab)} className="font-bold text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div> : tab === 'hp' ? (
            <div className="space-y-2">
              {hp && (
                <div className="flex gap-1.5 flex-wrap items-center">
                  <Pill tone="flame">{Number(hp.active ?? 0).toLocaleString()} active</Pill>
                  <Pill tone="amber">{Number(hp.pending ?? 0).toLocaleString()} pending</Pill>
                  {tierLabel(hp) && <Pill tone="green">🔥 {tierLabel(hp)}</Pill>}
                  {hp.tier_multiplier != null && <Pill tone="outline">×{txt(hp.tier_multiplier)} earn rate</Pill>}
                  {hp.hp_earned_120day != null && <Pill tone="cocoa">{Number(hp.hp_earned_120day).toLocaleString()} HP / 120d</Pill>}
                </div>
              )}
              {hp?.degraded && (
                <div className="flex items-start gap-2 rounded-xl bg-accent/20 border border-accent/40 p-2.5 text-[11px] text-foreground">
                  <AlertTriangle className="w-3.5 h-3.5 text-accent-foreground shrink-0 mt-0.5" />
                  <span>Some HP figures could not be read just now and are shown as 0. Retry in a moment.</span>
                </div>
              )}
              {hpTxs.length === 0 ? (
                <EmptyState icon={Flame} title="No HP transactions yet" body="This user's HP ledger appears here." />
              ) : hpTxs.map((t, i) => {
                const positive = ['earn', 'earned', 'credit', 'grant', 'transferred_in'].includes(t.type);
                return (
                  <div key={t.id || i} className="rounded-xl bg-secondary/50 border border-border p-3 flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-foreground capitalize truncate">{txt(t.source || t.type || t.reason, 'HP').replace(/_/g, ' ')}</div>
                      <div className="text-[11px] text-muted-foreground">{t.created_at ? timeAgo(t.created_at) : ''}</div>
                    </div>
                    <span className={`text-sm font-extrabold shrink-0 ${positive ? 'text-success' : 'text-destructive'}`}>
                      {positive ? '+' : '−'}{Number(t.amount ?? t.hp_amount ?? 0).toLocaleString()}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : tab === 'wallet' ? (
            <div className="space-y-2">
              {wallet && (
                <div className="rounded-xl bg-gradient-dark text-white p-3.5 flex items-center justify-between">
                  <span className="text-[10px] font-extrabold uppercase tracking-wider text-white/60">Wallet balance</span>
                  <span className="font-heading font-extrabold text-lg">{formatNaira(walletBalance ?? 0)}</span>
                </div>
              )}
              {walletTxs.length === 0 ? (
                <EmptyState icon={Wallet} title="No wallet transactions yet" body="Funding and spending history appears here." />
              ) : walletTxs.map((t, i) => (
                <div key={t.id || i} className="rounded-xl bg-secondary/50 border border-border p-3 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-bold text-foreground truncate">{txt(t.reason || t.description || t.type, 'Transaction')}</div>
                    <div className="text-[11px] text-muted-foreground">{t.created_at ? timeAgo(t.created_at) : ''}</div>
                  </div>
                  <span className={`text-sm font-extrabold shrink-0 ${t.type === 'credit' ? 'text-success' : 'text-destructive'}`}>
                    {t.type === 'credit' ? '+' : '−'}{formatNaira(t.amount ?? 0)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {orderList.length === 0 ? (
                <EmptyState icon={Package} title="No orders yet" body="This user's order history appears here." />
              ) : orderList.map((o) => (
                <div key={o.id} className="rounded-xl bg-secondary/50 border border-border p-3">
                  <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${ORDER_STATUS_COLORS[o.status] || ''}`}>
                        {ORDER_STATUS_LABELS[o.status] ?? txt(o.status, '—')}
                      </span>
                      {o.payment_status && <Pill tone={o.payment_status === 'paid' ? 'green' : 'outline'}>{txt(o.payment_status)}</Pill>}
                    </div>
                    <span className="text-[11px] text-muted-foreground font-semibold shrink-0">{o.created_at ? timeAgo(o.created_at) : ''}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-bold text-muted-foreground font-mono truncate">{o.order_number || `#${String(o.id || '').slice(-6).toUpperCase()}`}</span>
                    <span className="text-sm font-extrabold text-foreground shrink-0">{formatNaira(o.total_amount ?? o.total ?? 0)}</span>
                  </div>
                  {Array.isArray(o.order_items) && o.order_items.length > 0 && (
                    <div className="text-[11px] text-muted-foreground mt-1 truncate">
                      {o.order_items.map((it) => `${it.quantity || 1}× ${it.name_snapshot || it.name || ''}`).join(', ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </motion.div>

      {grantOpen && <GrantModal user={user} onClose={() => setGrantOpen(false)} onDone={() => { loadTab('hp'); onUserUpdated?.(); }} />}
    </motion.div>
    </ModalPortal>
  );
}

// POST /hp/admin/grant — positive, explicitly identified grants with notes.
function GrantModal({ user, onClose, onDone }) {
  const intent = useCmsCreateIntent();
  const writing = useRef(false);
  const [error, setError] = useState('');
  const [amount, setAmount] = useState<string | number>(50);
  const [notes, setNotes] = useState('Manual grant');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (writing.current) return;
    const value = Number(amount);
    if (!Number.isSafeInteger(value) || value < 1 || value > 100000 || !notes.trim() || notes.trim().length > 200) { setError(msg('FE_USER_GRANT_INVALID', 'Enter a whole HP amount between 1 and 100000 and a reason of at most 200 characters.')); return; }
    writing.current = true; setSubmitting(true); setError('');
    try {
      const { request_id, ...payload } = intent.body({ amount: value, notes: notes.trim(), user_id: user.id });
      const res = await liveApi.admin.grantHpToUser(user.id, { ...payload, grant_id: request_id });
      intent.clear();
      toast({ title: res?.replayed ? msg('FE_USER_GRANT_REPLAY', 'This grant was already applied.') : msg('FE_ADMIN_USERS_HP_ADJUSTED', 'HP adjusted') });
      onDone(); onClose();
    } catch (e) { setError(e.message || msg('FE_ADMIN_USERS_HP_ADJUSTMENT_FAILED', 'HP adjustment failed')); }
    finally { writing.current = false; setSubmitting(false); }
  };

  return (
    <Modal open onClose={() => { if (!writing.current) onClose(); }} title={msg('FE_USER_GRANT_TITLE', 'Grant HP — {name}', { name: user.full_name })}>
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">{msg('FE_USER_GRANT_HELP', 'Grant active HP to this user. Enter a positive whole amount and a reason.')}</p>
        <Field label="Amount (HP)"><TextInput aria-label={msg('FE_USER_GRANT_LABEL', 'HP amount')} disabled={submitting} min="1" max="100000" step="1" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Notes"><TextInput aria-label={msg('FE_USER_GRANT_REASON', 'Grant reason')} disabled={submitting} maxLength={200} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <button onClick={submit} disabled={submitting || amount === ''} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold active:scale-95 transition disabled:opacity-50">
          {submitting ? msg('FE_STOCK_SAVING', 'Saving…') : msg('FE_USER_GRANT_BUTTON', 'Grant HP')}
        </button>
      </div>
    </Modal>
  );
}

// POST /admin/hp/bulk-grant — one amount to every selected user.
function BulkGrantModal({ userIds, users, campusId, onClose, onDone }) {
  const intent = useCmsCreateIntent();
  const writing = useRef(false);
  const [error, setError] = useState('');
  const [previewKey, setPreviewKey] = useState('');
  const [amount, setAmount] = useState<string | number>(50);
  const [reason, setReason] = useState('Bulk HP grant');
  const [submitting, setSubmitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);

  const fingerprint = JSON.stringify([userIds, Number(amount), reason.trim(), campusId]);
  const grantBody = () => {
    const value = Number(amount);
    if (!userIds.length || !Number.isSafeInteger(value) || value < 1 || value > 100000 || !reason.trim() || reason.trim().length > 200) throw new Error(msg('FE_USER_GRANT_INVALID', 'Enter a whole HP amount between 1 and 100000 and a reason of at most 200 characters.'));
    const { request_id, ...payload } = intent.body({ user_ids: userIds, amount: value, reason: reason.trim(), ...(campusId ? { campus_id: campusId } : {}) });
    return { ...payload, grant_id: request_id };
  };
  const runPreview = async () => {
    if (writing.current) return;
    writing.current = true; setPreviewing(true); setError('');
    try { const res = await liveApi.admin.bulkGrantHp({ ...grantBody(), dry_run: true }); setPreview(res); setPreviewKey(fingerprint); }
    catch (e) { setError(e.message); }
    finally { writing.current = false; setPreviewing(false); }
  };
  const submit = async () => {
    if (writing.current) return;
    if (!preview || previewKey !== fingerprint) { setError(msg('FE_USER_BULK_PREVIEW_REQUIRED', 'Preview the current recipients and amount before granting.')); return; }
    writing.current = true; setSubmitting(true); setError('');
    try {
      const res = await liveApi.admin.bulkGrantHp({ ...grantBody(), dry_run: false }); setResult(res);
      toast({ title: msg('FE_USER_BULK_RESULT', 'Granted: {awarded} · already applied: {replayed} · failed: {failed} · skipped: {skipped}', { awarded: res.awarded_count ?? 0, replayed: res.already_granted_count ?? 0, failed: res.failed_count ?? 0, skipped: res.skipped_user_ids?.length ?? 0 }) });
      if (!res.failed_count) { intent.clear(); onDone(); }
    } catch (e) { setError(e.message); }
    finally { writing.current = false; setSubmitting(false); }
  };

  return (
    <Modal open onClose={() => { if (!writing.current) onClose(); }} title="Bulk HP Grant">
      <div className="space-y-3">
        <div className="rounded-xl bg-primary/10 border border-primary/20 p-3 text-xs font-bold text-primary flex items-center gap-1.5">
          <UsersIcon className="w-4 h-4 shrink-0" /> Granting HP to {userIds.length} selected user{userIds.length === 1 ? '' : 's'}
        </div>
        <div className="max-h-32 overflow-y-auto rounded-xl bg-secondary/60 p-2.5 space-y-1">
          {users.map((u) => (
            <div key={u.id} className="text-xs font-bold text-foreground flex justify-between gap-2">
              <span className="truncate">{u.full_name}</span>
              <span className="text-muted-foreground shrink-0">{Number(u.hp_balance ?? 0).toLocaleString()} HP</span>
            </div>
          ))}
        </div>
        <Field label="Amount per user (HP)"><TextInput aria-label={msg('FE_USER_GRANT_LABEL', 'HP amount')} disabled={submitting || previewing} type="number" value={amount} onChange={(e) => { setAmount(e.target.value); setPreview(null); setResult(null); }} /></Field>
        <Field label="Reason"><TextInput aria-label={msg('FE_USER_GRANT_REASON', 'Grant reason')} disabled={submitting || previewing} maxLength={200} value={reason} onChange={(e) => { setReason(e.target.value); setPreview(null); setResult(null); }} /></Field>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {!preview && <p className="text-xs text-muted-foreground">{msg('FE_USER_BULK_PREVIEW_REQUIRED', 'Preview the current recipients and amount before granting.')}</p>}
        <div className="flex gap-2">
          <button onClick={runPreview} disabled={previewing || submitting || !amount} className="flex-1 py-3 rounded-full bg-secondary text-secondary-foreground font-bold text-sm active:scale-95 transition disabled:opacity-50">
            {previewing ? 'Checking…' : 'Preview (no HP awarded)'}
          </button>
          <button onClick={submit} disabled={submitting || previewing || !preview || previewKey !== fingerprint || !preview.matched_count} className="flex-1 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-95 transition disabled:opacity-50">
            {submitting ? 'Granting…' : `Grant ${amount} HP`}
          </button>
        </div>
        {preview && (
          <div className="rounded-xl bg-primary/10 border border-primary/20 p-3 text-xs font-bold text-primary">
            Dry run: {preview.matched_count ?? preview.count ?? userIds.length} user{(Number(preview.matched_count ?? preview.count ?? userIds.length) || 2) === 1 ? '' : 's'} matched — preview only, no HP awarded yet.
          </div>
        )}
        {result && (
          <div className="rounded-xl bg-success/10 border border-success/25 p-3 text-xs text-success font-bold">
            {msg('FE_USER_BULK_RESULT', 'Granted: {awarded} · already applied: {replayed} · failed: {failed} · skipped: {skipped}', { awarded: result.awarded_count ?? 0, replayed: result.already_granted_count ?? 0, failed: result.failed_count ?? 0, skipped: result.skipped_user_ids?.length ?? 0 })}
          </div>
        )}
      </div>
    </Modal>
  );
}
