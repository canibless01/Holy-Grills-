import React, { useState, useEffect } from 'react';
import { Flame, TrendingUp, TrendingDown, Sparkles, Play } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Field, TextInput, Card, Pill, Toggle, SectionHeader } from './AdminShared';

export default function AdminHp() {
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

  // manual grant
  const [grantUserId, setGrantUserId] = useState('');
  const [grantAmount, setGrantAmount] = useState<string | number>(100);
  const [grantReason, setGrantReason] = useState('Manual grant');
  const [grantMsg, setGrantMsg] = useState(null);

  // expire HP
  const [expireUserId, setExpireUserId] = useState('');
  const [expireAmount, setExpireAmount] = useState('');
  const [expireMsg, setExpireMsg] = useState(null);

  // KPIs come from /analytics/hp (the canonical HP analytics endpoint).
  const load = async () => {
    setLoading(true); setLoadError(null);
    try {
      const [h, u] = await Promise.all([mockApi.admin.getAnalyticsHp(), mockApi.admin.getUsers()]);
      setHp(h || null);
      setUsers(Array.isArray(u) ? u : []);
    } catch (e) { setLoadError(e?.message || 'Failed to load HP analytics.'); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const runBulk = async () => {
    setSubmitting(true);
    const body: Record<string, unknown> = { amount: Number(amount), reason, dry_run: dryRun };
    if (segment !== 'all') {
      body.user_ids = [segment];
    } else {
      // Segment filters only apply to the "all active users" segment (not an explicit list).
      if (tierSlug.trim()) body.tier_slug = tierSlug.trim().toLowerCase();
      if (lastOrderBefore) body.last_order_before = lastOrderBefore;
      if (lastOrderAfter) body.last_order_after = lastOrderAfter;
    }
    try { setResult(await mockApi.admin.bulkGrantHp(body)); if (!dryRun) await load(); }
    catch (e) { setResult({ error: e.message }); }
    setSubmitting(false);
  };

  const runGrant = async () => {
    if (!grantUserId) return;
    try { setGrantMsg(await mockApi.admin.grantHpToUser(grantUserId, { amount: Number(grantAmount), reason: grantReason })); await load(); }
    catch (e) { setGrantMsg({ error: e.message }); }
  };

  const runExpire = async () => {
    if (!expireUserId) return;
    try { setExpireMsg(await mockApi.admin.expireHpFromUser(expireUserId, { amount: expireAmount ? Number(expireAmount) : undefined }) || { expired: true }); await load(); }
    catch (e) { setExpireMsg({ error: e.message }); }
  };

  if (loading) return <LoadingSpinner label="Loading HP analytics..." />;
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
    { label: 'Pending HP', value: num(hp.hp_pending).toLocaleString(), icon: TrendingUp, color: 'text-amber-600' },
    { label: 'Earned (Active)', value: num(hp.hp_earned_active).toLocaleString(), icon: Sparkles, color: 'text-green-600' },
    { label: 'Spent', value: num(hp.hp_spent).toLocaleString(), icon: TrendingDown, color: 'text-blue-600' },
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
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Amount (HP)"><TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
              <Field label="Recipients">
                <select value={segment} onChange={(e) => setSegment(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                  <option value="all">All active users</option>
                  {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                </select>
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
            <button onClick={runBulk} disabled={submitting} className="flex items-center gap-1.5 w-full py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold disabled:opacity-50">
              <Play className="w-4 h-4" /> {dryRun ? 'Preview grant' : 'Grant HP'}
            </button>
            {result && (
              <div className="rounded-xl bg-muted border border-border p-3 text-xs space-y-1">
                {result.error ? <span className="text-red-600">✕ {result.error}</span> : (
                  <>
                    <div className="font-bold text-foreground">{result.dry_run ? 'Dry-run preview' : 'Grant complete'}</div>
                    {result.dry_run ? (
                      <div className="text-muted-foreground">{result.matched_count} users matched × {result.amount_per_user} HP = <span className="font-bold text-primary">{(result.total_hp_to_award ?? 0).toLocaleString()} HP</span></div>
                    ) : (
                      <div className="text-muted-foreground">{result.awarded_count} awarded × {result.amount_per_user} HP = <span className="font-bold text-primary">{(result.total_hp_awarded ?? 0).toLocaleString()} HP</span></div>
                    )}
                    {!!result.already_granted_count && result.already_granted_count > 0 && <div className="text-amber-600">{result.already_granted_count} already granted (skipped)</div>}
                    {!!result.failed_count && result.failed_count > 0 && <div className="text-red-600">{result.failed_count} failed</div>}
                    {Array.isArray(result.skipped_user_ids) && result.skipped_user_ids.length > 0 && <div className="text-muted-foreground">Skipped: {result.skipped_user_ids.length} user(s) not found</div>}
                    {result.grant_id && <div className="text-[10px] text-muted-foreground font-mono">grant_id: {result.grant_id}</div>}
                  </>
                )}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <SectionHeader title="Manual Grant to User" action={<Pill tone="blue">single</Pill>} />
          <p className="text-[11px] text-muted-foreground mb-3">Grant HP to one user (POST /hp/admin/grant — body: user_id, amount, notes).</p>
          <div className="space-y-3">
            <Field label="User">
              <select value={grantUserId} onChange={(e) => setGrantUserId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                <option value="">Select user…</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.full_name} · {u.hp_balance} HP</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Amount (HP)"><TextInput type="number" value={grantAmount} onChange={(e) => setGrantAmount(e.target.value)} /></Field>
              <Field label="Notes"><TextInput value={grantReason} onChange={(e) => setGrantReason(e.target.value)} /></Field>
            </div>
            <button onClick={runGrant} disabled={!grantUserId} className="w-full py-2.5 rounded-full bg-foreground text-white text-sm font-bold disabled:opacity-50">Grant to user</button>
            {grantMsg && (
              <div className={`rounded-xl p-3 text-xs ${grantMsg.error ? 'bg-red-50 border border-red-200 text-red-700' : 'bg-green-50 border border-green-200 text-green-700'}`}>
                {grantMsg.error ? `✕ ${grantMsg.error}` : <>✓ {grantMsg.amount} HP granted. New balance: <span className="font-bold">{grantMsg.new_balance?.toLocaleString()}</span> HP</>}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <SectionHeader title="Expire HP from User" action={<Pill tone="red">admin</Pill>} />
        <p className="text-[11px] text-muted-foreground mb-3">Remove active HP from a user. Leave amount blank to expire all (POST /hp/admin/expire).</p>
        <div className="space-y-3">
          <Field label="User">
            <select value={expireUserId} onChange={(e) => setExpireUserId(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
              <option value="">Select user…</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.full_name} · {u.hp_balance} HP</option>)}
            </select>
          </Field>
          <Field label="Amount (HP) — leave blank to expire all"><TextInput type="number" value={expireAmount} onChange={(e) => setExpireAmount(e.target.value)} /></Field>
          <button onClick={runExpire} disabled={!expireUserId} className="w-full py-2.5 rounded-full bg-red-600 text-white text-sm font-bold disabled:opacity-50">Expire HP</button>
          {expireMsg && (
            <div className={`rounded-xl p-3 text-xs ${expireMsg.error ? 'bg-red-50 border border-red-200 text-red-700' : 'bg-green-50 border border-green-200 text-green-700'}`}>
              {expireMsg.error ? `✕ ${expireMsg.error}` : `✓ HP expired. ${expireMsg.expired_amount ?? expireMsg.amount ?? 0} HP removed.`}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}