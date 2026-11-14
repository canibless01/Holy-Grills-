import { useState, useEffect, useRef } from 'react';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { useCampus } from '@/lib/campusContext';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { msg } from '@/lib/messages';
import AdminUserPicker from './AdminUserPicker';
import { Flame, TrendingUp, TrendingDown, Sparkles, Play } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { Field, TextInput, Card, Pill, Toggle, SectionHeader } from './AdminShared';

export default function AdminHp() {
  const { adminCampusId } = useCampus();
  const { user } = useHolyGrill();
  const campusId = user?.role === 'super_admin' ? adminCampusId : user?.campus_id || user?.profile?.campus_id;
  return <HpWorkspace key={campusId || 'global'} campusId={campusId} />;
}

function HpWorkspace({ campusId }) {
  const grantIntent = useCmsCreateIntent();
  const bulkIntent = useCmsCreateIntent();
  const grantWriting = useRef(false);
  const bulkWriting = useRef(false);
  const expiryIntent = useCmsCreateIntent();
  const expiryWriting = useRef(false);
  const [hp, setHp] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // bulk grant
  const [amount, setAmount] = useState<string | number>(50);
  const [reason, setReason] = useState('Engagement bonus');
  const [dryRun, setDryRun] = useState(true);
  const [segment, setSegment] = useState('all');
  const [tierSlug, setTierSlug] = useState('');
  const [lastOrderBefore, setLastOrderBefore] = useState('');
  const [lastOrderAfter, setLastOrderAfter] = useState('');
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [bulkPreviewKey, setBulkPreviewKey] = useState('');

  // manual grant
  const [grantUserId, setGrantUserId] = useState('');
  const [grantAmount, setGrantAmount] = useState<string | number>(100);
  const [grantReason, setGrantReason] = useState('Manual grant');
  const [grantMsg, setGrantMsg] = useState(null);
  const [grantBusy, setGrantBusy] = useState(false);

  // expire HP
  const [expireUserId, setExpireUserId] = useState('');
  const [expireAmount, setExpireAmount] = useState('');
  const [expireMsg, setExpireMsg] = useState(null);
  const [expireReason, setExpireReason] = useState('Manual HP expiry');
  const [expirePreview, setExpirePreview] = useState(null);
  const [expiryBusy, setExpiryBusy] = useState(false);

  // KPIs come from /analytics/hp (the canonical HP analytics endpoint).
  const load = async () => {
    setLoading(true); setLoadError(null);
    try {
      const [h, u] = await Promise.all([mockApi.admin.getAnalyticsHp(campusId ? { campus_id: campusId } : {}), mockApi.admin.getUsers(campusId ? { campus_id: campusId } : {})]);
      setHp(h || null);
      setUsers(Array.isArray(u) ? u : []);
    } catch (e) { setLoadError(e?.message || 'Failed to load HP analytics.'); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const runBulk = async () => {
    if (bulkWriting.current || !segment) return;
    bulkWriting.current = true;
    setSubmitting(true);
    const body: Record<string, unknown> = { amount: Number(amount), reason: reason.trim(), ...(campusId ? { campus_id: campusId } : {}) };
    if (segment !== 'all') {
      body.user_ids = [segment];
    } else {
      // Segment filters only apply to the "all active users" segment (not an explicit list).
      if (tierSlug.trim()) body.tier_slug = tierSlug.trim().toLowerCase();
      if (lastOrderBefore) body.last_order_before = lastOrderBefore;
      if (lastOrderAfter) body.last_order_after = lastOrderAfter;
    }
    try {
      if (!dryRun && bulkPreviewKey !== JSON.stringify(body)) throw new Error(msg('FE_USER_BULK_PREVIEW_REQUIRED', 'Preview the current recipients and amount before granting.'));
      const { request_id, ...payload } = bulkIntent.body(body);
      setResult(await mockApi.admin.bulkGrantHp({ ...payload, grant_id: request_id, dry_run: dryRun }));
      if (dryRun) setBulkPreviewKey(JSON.stringify(body)); else await load();
    } catch (e) { setResult({ error: e.message }); }
    finally { bulkWriting.current = false; setSubmitting(false); }
  };

  const runGrant = async () => {
    if (!grantUserId || grantWriting.current) return;
    grantWriting.current = true; setGrantBusy(true);
    try {
      const { request_id, ...payload } = grantIntent.body({ user_id: grantUserId, amount: Number(grantAmount), notes: grantReason.trim() });
      setGrantMsg(await mockApi.admin.grantHpToUser(grantUserId, { ...payload, grant_id: request_id })); await load();
    } catch (e) { setGrantMsg({ error: e.message }); }
    finally { grantWriting.current = false; setGrantBusy(false); }
  };

  const expiryKey = JSON.stringify([expireUserId, expireAmount, expireReason.trim()]);
  const previewExpiry = async () => {
    if (!expireUserId || expiryWriting.current) return;
    expiryWriting.current = true; setExpiryBusy(true); setExpireMsg(null); setExpirePreview(null);
    try {
      const balance = await mockApi.admin.getUserHp(expireUserId);
      if (balance.degraded) throw new Error(msg('FE_USER_TAB_FAILED', 'This history could not be loaded. Retry to see the current records.'));
      const active = Number(balance.active);
      const requested = expireAmount.trim() ? Number(expireAmount) : null;
      const remove = requested ?? active;
      if (!Number.isSafeInteger(active) || active < 0 || !Number.isSafeInteger(remove) || remove < 1 || remove > active || !expireReason.trim() || expireReason.trim().length > 200) throw new Error(msg('FE_HP_EXPIRY_INVALID', 'Choose a user, a positive whole amount within their active balance, and a reason of at most 200 characters.'));
      setExpirePreview({ key: expiryKey, active, requested, remove });
    } catch (e) { setExpireMsg({ error: e.message }); }
    finally { expiryWriting.current = false; setExpiryBusy(false); }
  };
  const runExpire = async () => {
    if (expiryWriting.current || !expirePreview || expirePreview.key !== expiryKey) return;
    expiryWriting.current = true; setExpiryBusy(true); setExpireMsg(null);
    try {
      const payload = expiryIntent.body({ user_id: expireUserId, amount: expirePreview.requested, expected_balance: expirePreview.active, notes: expireReason.trim() });
      const res = await mockApi.admin.expireHpFromUser(expireUserId, payload);
      setExpireMsg(res); setExpirePreview(null); expiryIntent.clear(); await load();
    } catch (e) { setExpireMsg({ error: e.message }); }
    finally { expiryWriting.current = false; setExpiryBusy(false); }
  };

  if (loading) return <StaffPanelSkeleton />;
  if (loadError || !hp) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <p className="text-sm text-muted-foreground mb-3">{loadError || 'No HP analytics available.'}</p>
        <button onClick={load} className="px-4 py-2 rounded-full bg-gradient-cta text-white text-sm font-bold">Retry</button>
      </div>
    );
  }

  const num = (v) => (typeof v === 'number' ? v : Number(v) || 0);
  const kpis = [
    { label: 'HP in Circulation', value: num(hp.hp_in_circulation).toLocaleString(), icon: Flame, color: 'text-primary' },
    { label: 'Pending HP', value: num(hp.hp_pending).toLocaleString(), icon: TrendingUp, color: 'text-warn' },
    { label: 'Earned (Active)', value: num(hp.hp_earned_active).toLocaleString(), icon: Sparkles, color: 'text-success' },
    { label: 'Spent', value: num(hp.hp_spent).toLocaleString(), icon: TrendingDown, color: 'text-info' },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k) => (
          <Card key={k.label}>
            <k.icon className={`w-5 h-5 ${k.color} mb-2`} />
            <div className="font-heading font-extrabold text-xl text-foreground">{k.value}</div>
            <div className="text-xs text-muted-foreground">{k.label}</div>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <Card>
          <SectionHeader title="Bulk HP Grant" action={<Pill tone="flame">admin</Pill>} />
          <p className="text-[11px] text-muted-foreground mb-3">Grant HP to all active users or one user. Dry-run first to preview (POST /admin/hp/bulk-grant).</p>
          <fieldset disabled={submitting} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Amount (HP)"><TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
              <Field label="Recipients">
                <AdminUserPicker users={users} value={segment} onChange={setSegment} campusId={campusId} disabled={submitting} label={msg('FE_USER_BULK_RECIPIENT', 'Bulk recipient')} searchLabel={msg('FE_USER_BULK_SEARCH', 'Find bulk recipient')} allLabel={msg('FE_USER_ALL_ACTIVE_SCOPE', 'All active users in this scope')} />
              </Field>
            </div>
            <Field label="Reason"><TextInput value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
            {segment === 'all' && (
              <div className="rounded-xl bg-muted/50 border border-border p-2.5 space-y-2.5">
                <div className="text-[10px] font-bold uppercase text-muted-foreground tracking-wide">Optional segment filters</div>
                <Field label="Tier slug (e.g. bronze, silver, gold)"><TextInput value={tierSlug} onChange={(e) => setTierSlug(e.target.value)} placeholder="Leave blank for all tiers" /></Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Last order before"><input type="date" value={lastOrderBefore} onChange={(e) => setLastOrderBefore(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
                  <Field label="Last order after"><input type="date" value={lastOrderAfter} onChange={(e) => setLastOrderAfter(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
                </div>
              </div>
            )}
            <div className="flex items-center gap-2">
              <Toggle checked={dryRun} onChange={setDryRun} />
              <span className="text-xs font-semibold text-foreground">Dry run (preview only — no HP credited)</span>
            </div>
            <button onClick={runBulk} disabled={submitting || !segment} className="flex items-center gap-1.5 w-full py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold disabled:opacity-50">
              <Play className="w-4 h-4" /> {dryRun ? 'Preview grant' : 'Grant HP'}
            </button>
            {result && !result.error && !result.dry_run && !result.failed_count && <button onClick={() => { if (!bulkWriting.current) { bulkIntent.clear(); setResult(null); setBulkPreviewKey(''); setDryRun(true); } }} className="text-xs font-bold text-primary">{msg('FE_USER_NEW_GRANT', 'Start new grant')}</button>}
            {result && (
              <div className="rounded-xl bg-muted border border-border p-3 text-xs space-y-1">
                {result.error ? <span className="text-destructive">✕ {result.error}</span> : (
                  <>
                    <div className="font-bold text-foreground">{result.dry_run ? 'Dry-run preview' : 'Grant complete'}</div>
                    {result.dry_run ? (
                      <div className="text-muted-foreground">{result.matched_count} users matched × {result.amount_per_user} HP = <span className="font-bold text-primary">{(result.total_hp_to_award ?? 0).toLocaleString()} HP</span></div>
                    ) : (
                      <div className="text-muted-foreground">{result.awarded_count} awarded × {result.amount_per_user} HP = <span className="font-bold text-primary">{(result.total_hp_awarded ?? 0).toLocaleString()} HP</span></div>
                    )}
                    {!!result.already_granted_count && result.already_granted_count > 0 && <div className="text-warn">{result.already_granted_count} already granted (skipped)</div>}
                    {!!result.failed_count && result.failed_count > 0 && <div className="text-destructive">{result.failed_count} failed</div>}
                    {Array.isArray(result.skipped_user_ids) && result.skipped_user_ids.length > 0 && <div className="text-muted-foreground">Skipped: {result.skipped_user_ids.length} user(s) not found</div>}
                    {result.grant_id && <div className="text-[10px] text-muted-foreground font-mono">grant_id: {result.grant_id}</div>}
                  </>
                )}
              </div>
            )}
          </fieldset>
        </Card>

        <Card>
          <SectionHeader title="Manual Grant to User" action={<Pill tone="blue">single</Pill>} />
          <p className="text-[11px] text-muted-foreground mb-3">Grant HP to one user (POST /hp/admin/grant — body: user_id, amount, notes).</p>
          <div className="space-y-3">
            <Field label="User">
              <AdminUserPicker users={users} value={grantUserId} onChange={setGrantUserId} campusId={campusId} disabled={grantBusy} label={msg('FE_USER_GRANT_RECIPIENT', 'Grant recipient')} searchLabel={msg('FE_USER_GRANT_SEARCH', 'Find grant recipient')} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Amount (HP)"><TextInput aria-label={msg('FE_USER_GRANT_LABEL', 'HP amount')} disabled={grantBusy} type="number" value={grantAmount} onChange={(e) => setGrantAmount(e.target.value)} /></Field>
              <Field label="Notes"><TextInput aria-label={msg('FE_USER_GRANT_REASON', 'Grant reason')} disabled={grantBusy} value={grantReason} onChange={(e) => setGrantReason(e.target.value)} /></Field>
            </div>
            <button onClick={runGrant} disabled={!grantUserId || grantBusy} className="w-full py-2.5 rounded-full bg-foreground text-white text-sm font-bold disabled:opacity-50">Grant to user</button>
            {grantMsg && !grantMsg.error && <button disabled={grantBusy} onClick={() => { if (!grantWriting.current) { grantIntent.clear(); setGrantMsg(null); } }} className="text-xs font-bold text-primary">{msg('FE_USER_NEW_GRANT', 'Start new grant')}</button>}
            {grantMsg && (
              <div className={`rounded-xl p-3 text-xs ${grantMsg.error ? 'tone-error border border-destructive/30 text-destructive' : 'tone-success border border-success/30 text-success'}`}>
                {grantMsg.error ? `✕ ${grantMsg.error}` : grantMsg.replayed ? msg('FE_USER_GRANT_REPLAY', 'This grant was already applied.') : <>✓ {grantMsg.amount} HP granted. New balance: <span className="font-bold">{grantMsg.new_balance?.toLocaleString()}</span> HP</>}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <SectionHeader title="Expire HP from User" action={<Pill tone="red">admin</Pill>} />
        <p className="text-[11px] text-muted-foreground mb-3">{msg('FE_HP_EXPIRY_HELP', 'Preview the deduction before confirming. Leave the amount blank to remove the active HP shown in the preview.')}</p>
        <div className="space-y-3">
          <Field label="User">
            <AdminUserPicker users={users} value={expireUserId} onChange={id => { setExpireUserId(id); setExpirePreview(null); }} campusId={campusId} disabled={expiryBusy} label={msg('FE_HP_EXPIRY_RECIPIENT', 'Deduction recipient')} searchLabel={msg('FE_USER_EXPIRY_SEARCH', 'Find deduction recipient')} />
          </Field>
          <Field label="Amount (HP) — leave blank to expire all"><TextInput aria-label={msg('FE_HP_EXPIRY_AMOUNT', 'HP to remove (blank for all active HP)')} disabled={expiryBusy} type="number" min="1" step="1" value={expireAmount} onChange={(e) => { setExpireAmount(e.target.value); setExpirePreview(null); }} /></Field>
          <Field label={msg('FE_HP_EXPIRY_REASON', 'Deduction reason')}><TextInput aria-label={msg('FE_HP_EXPIRY_REASON', 'Deduction reason')} disabled={expiryBusy} maxLength={200} value={expireReason} onChange={e => { setExpireReason(e.target.value); setExpirePreview(null); }} /></Field>
          <button onClick={previewExpiry} disabled={!expireUserId || expiryBusy} className="w-full py-2.5 rounded-full bg-secondary text-foreground text-sm font-bold disabled:opacity-50">{msg('FE_HP_EXPIRY_PREVIEW', 'Preview deduction')}</button>
          {expirePreview && expirePreview.key === expiryKey && <div className="space-y-3"><p className="text-xs text-muted-foreground">{msg('FE_HP_EXPIRY_PREVIEW_TEXT', 'Active balance: {balance} HP · amount to remove: {amount} HP. This records a permanent HP ledger entry.', { balance: expirePreview.active, amount: expirePreview.remove })}</p><button onClick={runExpire} disabled={expiryBusy} className="w-full py-2.5 rounded-full bg-destructive text-white text-sm font-bold disabled:opacity-50">{msg('FE_HP_EXPIRY_CONFIRM', 'Confirm removal of {amount} HP', { amount: expirePreview.remove })}</button></div>}
          {expireMsg && (
            <div className={`rounded-xl p-3 text-xs ${expireMsg.error ? 'tone-error border border-destructive/30 text-destructive' : 'tone-success border border-success/30 text-success'}`}>
              {expireMsg.error ? `✕ ${expireMsg.error}` : expireMsg.replayed ? msg('FE_HP_EXPIRY_REPLAY', 'This deduction was already applied. Current balance: {balance} HP.', { balance: expireMsg.new_balance }) : msg('FE_HP_EXPIRY_DONE', '{amount} HP removed. Current balance: {balance} HP.', { amount: expireMsg.expired, balance: expireMsg.new_balance })}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}