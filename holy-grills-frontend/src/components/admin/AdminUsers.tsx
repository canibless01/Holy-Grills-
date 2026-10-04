import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, Flame, Wallet, Ban, Check, X, Package, Plus, Users as UsersIcon, Send,
  Mail, Phone, RefreshCw, History, AlertTriangle, UserX, UserCheck, User as UserIcon,
} from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, timeAgo, ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/lib/hgUtils';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Pill, Pagination, body } from './ui/AdminKit';

const ROLES = [
  { value: 'student', label: 'Student' },
  { value: 'kitchen', label: 'Kitchen' },
  { value: 'rider', label: 'Rider' },
  { value: 'admin', label: 'Admin' },
  { value: 'super_admin', label: 'Super Admin' },
];
const PAGE_SIZE = 24;

// The backend occasionally returns a nested object where the UI expects text
// (a tier, a status, a transaction type). Rendering that object as a React
// child would take the whole drawer down, so every such value is coerced to
// display text first.
const txt = (v, fallback = '') => {
  if (v == null) return fallback;
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (typeof v === 'object') return v.name || v.label || v.title || v.full_name || v.code || v.value || fallback;
  return fallback;
};

// Tier label comes straight from the backend's user list ("HP balance and
// tier info") — no mock tier table lookup.
const tierLabel = (u) =>
  u.tier_name || (typeof u.tier === 'string' ? u.tier : (u.tier && typeof u.tier === 'object' ? (u.tier.name || u.tier.tier) : null)) || null;

// User Directory — GET /admin/users (q, role, limit, offset) · role changes
// (PATCH /admin/users/:id/role) · activate/deactivate · per-user HP ledger,
// wallet history and order history from their dedicated admin endpoints.
export default function AdminUsers() {
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
  const [bulkOpen, setBulkOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await liveApi.admin.getUsers({
        q: search || undefined,
        role: roleFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setUsers(res);
      setHasMore(res.length === PAGE_SIZE);
    } catch (e) {
      toast({ title: "Couldn't load users", description: e.message, variant: 'destructive' });
      setUsers([]);
      setHasMore(false);
    }
    setLoading(false);
  };

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [search, roleFilter, page]);

  const onSearchInput = (v) => { setSearch(v); if (page !== 0) setPage(0); };
  const onRoleFilter = (v) => { setRoleFilter(v); if (page !== 0) setPage(0); };

  // PATCH /admin/users/:id/role — backend rejects self-changes and
  // non-super-admin → super_admin; mirrored client-side for instant feedback.
  const handleRole = async (u, role) => {
    if (role === u.role) return;
    if (u.id === me?.id) {
      toast({ title: 'Not allowed', description: 'You cannot change your own role.', variant: 'destructive' });
      return;
    }
    if (role === 'super_admin' && me?.role !== 'super_admin') {
      toast({ title: 'Not allowed', description: 'Only a super admin can assign the super_admin role.', variant: 'destructive' });
      return;
    }
    setUpdating(u.id);
    try {
      await liveApi.admin.updateRole(u.id, { role });
      toast({ title: 'Role updated', description: `${u.full_name} is now ${role.replace('_', ' ')}.` });
      load();
    } catch (e) {
      toast({ title: 'Role change failed', description: e.message, variant: 'destructive' });
    }
    setUpdating(null);
  };

  // POST /admin/users/:id/deactivate | /activate — backend blocks self-
  // deactivation and non-super-admin deactivating a super_admin.
  const handleToggle = async (u) => {
    if (u.id === me?.id) {
      toast({ title: 'Not allowed', description: 'You cannot deactivate your own account.', variant: 'destructive' });
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
      toast({ title: 'Action failed', description: e.message, variant: 'destructive' });
      setConfirmToggle(null);
    }
    setUpdating(null);
  };

  const toggleSelect = (id) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelectedIds(next);
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card className="p-3 flex flex-col lg:flex-row gap-2.5 lg:items-center">
        <div className="relative flex-1 min-w-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => onSearchInput(e.target.value)}
            placeholder="Search by name, phone or email…"
            className="w-full pl-10 pr-9 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          {search && (
            <button onClick={() => onSearchInput('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-secondary active:scale-95 transition">
              <X className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
        <select
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
                          onClick={() => toggleSelect(u.id)}
                          aria-label="Select user"
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
                        disabled={updating === u.id || isSelf}
                        title={isSelf ? 'You cannot change your own role' : 'Change role'}
                        className="flex-1 min-w-0 text-xs px-2.5 py-2 rounded-xl border border-border bg-card text-foreground font-bold focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50"
                      >
                        {ROLES.filter((r) => r.value !== 'super_admin' || me?.role === 'super_admin').map((r) => (
                          <option key={r.value} value={r.value}>{r.label}</option>
                        ))}
                      </select>
                      <button
                        onClick={() => (u.is_active ? setConfirmToggle(u) : handleToggle(u))}
                        disabled={updating === u.id || (u.is_active && u.role === 'super_admin' && me?.role !== 'super_admin')}
                        title={u.is_active
                          ? (u.role === 'super_admin' && me?.role !== 'super_admin' ? 'Only a super admin can deactivate a super admin' : 'Deactivate account')
                          : 'Reactivate account'}
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
        {selected && <UserDrawer key={selected.id} user={selected} onClose={() => setSelected(null)} />}
      </AnimatePresence>

      {bulkOpen && (
        <BulkGrantModal
          userIds={[...selectedIds]}
          users={users.filter((u) => selectedIds.has(u.id))}
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
function UserDrawer({ user, onClose }) {
  const [tab, setTab] = useState('hp');
  const [profile, setProfile] = useState(null);
  const [hp, setHp] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [orders, setOrders] = useState(null);
  const [grantOpen, setGrantOpen] = useState(false);
  const [tabLoading, setTabLoading] = useState(true);

  const loadTab = async (t) => {
    setTab(t);
    setTabLoading(true);
    try {
      if (t === 'hp') setHp(await liveApi.admin.getUserHp(user.id));
      else if (t === 'wallet') setWallet(await liveApi.admin.getUserWallet(user.id));
      else setOrders(await liveApi.admin.getUserOrders(user.id, { limit: 50 }));
    } catch (e) {
      toast({ title: "Couldn't load this tab", description: e.message, variant: 'destructive' });
    }
    setTabLoading(false);
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
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-end sm:items-stretch sm:justify-end bg-foreground/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: 60, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 60, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 320, damping: 32 }}
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
          <button onClick={onClose} className="p-2 -mr-2 rounded-xl hover:bg-secondary active:scale-95 transition">
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
            <Plus className="w-4 h-4" /> Adjust HP
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
          ) : tab === 'hp' ? (
            <div className="space-y-2">
              {hp && (
                <div className="flex gap-1.5 flex-wrap items-center">
                  <Pill tone="flame">{Number(hp.active ?? 0).toLocaleString()} active</Pill>
                  <Pill tone="amber">{Number(hp.pending ?? 0).toLocaleString()} pending</Pill>
                  {hp.tier && <Pill tone="green">🔥 {tierLabel(hp)}</Pill>}
                  {hp.tier_multiplier != null && <Pill tone="outline">×{txt(hp.tier_multiplier)} earn rate</Pill>}
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

      {grantOpen && <GrantModal user={user} onClose={() => setGrantOpen(false)} onDone={() => loadTab('hp')} />}
    </motion.div>
  );
}

// POST /hp/admin/grant — manual grant/deduct with notes (negative to deduct).
function GrantModal({ user, onClose, onDone }) {
  const [amount, setAmount] = useState<string | number>(50);
  const [notes, setNotes] = useState('Manual grant');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await liveApi.admin.grantHpToUser(user.id, { amount: Number(amount), notes });
      toast({
        title: 'HP adjusted',
        description: `${res?.amount ?? amount} HP · new balance ${res?.new_balance != null ? Number(res.new_balance).toLocaleString() : 'updated'}`,
      });
      onDone();
      onClose();
    } catch (e) {
      toast({ title: 'HP adjustment failed', description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={`Adjust HP — ${user.full_name}`}>
      <div className="space-y-3">
        <p className="text-xs text-muted-foreground">Grant or deduct HP for this user. A negative amount deducts.</p>
        <Field label="Amount (HP)"><TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Notes"><TextInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason for this adjustment" /></Field>
        <button onClick={submit} disabled={submitting || amount === ''} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold active:scale-95 transition disabled:opacity-50">
          {submitting ? 'Adjusting…' : 'Apply adjustment'}
        </button>
      </div>
    </Modal>
  );
}

// POST /admin/hp/bulk-grant — one amount to every selected user.
function BulkGrantModal({ userIds, users, onClose, onDone }) {
  const [amount, setAmount] = useState<string | number>(50);
  const [reason, setReason] = useState('Bulk HP grant');
  const [submitting, setSubmitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);

  // dry_run: true — the backend reports who would be matched WITHOUT awarding
  // any HP. The backend contract expects a preview step before committing.
  const runPreview = async () => {
    setPreviewing(true);
    try {
      const res = await liveApi.admin.bulkGrantHp({ user_ids: userIds, amount: Number(amount), reason, dry_run: true });
      setPreview(res);
    } catch (e) {
      toast({ title: 'Preview failed', description: e.message, variant: 'destructive' });
    }
    setPreviewing(false);
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await liveApi.admin.bulkGrantHp({ user_ids: userIds, amount: Number(amount), reason });
      setResult(res);
      toast({ title: 'Bulk grant sent', description: `${res?.awarded_count ?? userIds.length} users granted ${amount} HP each.` });
      setTimeout(onDone, 1200);
    } catch (e) {
      toast({ title: 'Bulk grant failed', description: e.message, variant: 'destructive' });
      setSubmitting(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Bulk HP Grant">
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
        <Field label="Amount per user (HP)"><TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Reason"><TextInput value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex gap-2">
          <button onClick={runPreview} disabled={previewing || submitting || !amount} className="flex-1 py-3 rounded-full bg-secondary text-secondary-foreground font-bold text-sm active:scale-95 transition disabled:opacity-50">
            {previewing ? 'Checking…' : 'Preview (no HP awarded)'}
          </button>
          <button onClick={submit} disabled={submitting || !amount} className="flex-1 py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-95 transition disabled:opacity-50">
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
            ✓ {result.awarded_count ?? userIds.length} users granted {result.amount_per_user ?? amount} HP each. Total: {result.total_hp_awarded ?? (Number(amount) * userIds.length)} HP
          </div>
        )}
      </div>
    </Modal>
  );
}