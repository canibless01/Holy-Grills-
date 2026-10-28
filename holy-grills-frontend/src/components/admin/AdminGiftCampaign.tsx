import { useEffect, useRef, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { Card, Field, TextInput, Toggle } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

const draft = () => ({ id: crypto.randomUUID(), name: '', enabled: false, eligibility: 'first_order',
  starts_at: new Date().toISOString(), ends_at: new Date(Date.now() + 7 * 86400000).toISOString(),
  validity_days: 60, benefits: [{ kind: 'free_side', credits: 1 }] });
const asInstant = value => { const instant = new Date(`${value}+01:00`); return Number.isNaN(instant.getTime()) ? null : instant.toISOString(); };
const localTime = value => value ? new Date(value).toLocaleString('sv-SE', { timeZone: 'Africa/Lagos' }).replace(' ', 'T').slice(0, 16) : '';
const fields = { hp: { amount: 50 }, free_side: { credits: 1 }, delivery_discount: { percent: 100, cap: 500 }, hp_multiplier: { multiplier: 2 } };
const kindLabels = () => ({ hp: msg('FE_GIFT_HP', 'HP'), free_side: msg('FE_GIFT_SIDE', 'Free-side credits'), delivery_discount: msg('FE_GIFT_DELIVERY', 'Delivery discount'), hp_multiplier: msg('FE_GIFT_MULTIPLIER', 'Food HP multiplier') });
const fieldLabels = () => ({ amount: msg('FE_GIFT_AMOUNT', 'HP amount'), credits: msg('FE_ONBOARDING_CREDITS', 'Credits per account'), percent: msg('FE_GIFT_PERCENT', 'Delivery discount (%)'), cap: msg('FE_GIFT_CAP', 'Maximum delivery discount (₦)'), multiplier: msg('FE_GIFT_MULTIPLIER_VALUE', 'Food HP multiplier (×)') });

export default function AdminGiftCampaign({ scope }) {
  const [form, setForm] = useState(null), [stamp, setStamp] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(false), [conflict, setConflict] = useState(false);
  const [inherited, setInherited] = useState(false);
  const alive = useRef(true);
  const load = async () => {
    setError(false);
    try {
      const response = await liveApi.admin.getGiftCampaign(scope);
      if (!alive.current) return;
      setForm(response.config?.id ? response.config : draft()); setStamp(response.updated_at);
      setInherited(response.inherited === true); setConflict(false);
    } catch { if (alive.current) setError(true); }
  };
  useEffect(() => { alive.current = true; load(); return () => { alive.current = false; }; }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await liveApi.admin.updateGiftCampaign({ ...scope, config: form, expected_updated_at: stamp });
      if (!alive.current) return;
      setForm(result.config); setStamp(result.updated_at); setInherited(false); setConflict(false);
      toast({ title: msg('FE_GIFT_SAVED', 'Gift campaign saved') });
    } catch (exception) {
      if (!alive.current) return;
      if (exception.status === 409) setConflict(true);
      toast({ title: msg('FE_ADMIN_ONBOARDING_FAILED', 'Failed'), description: exception.message, variant: 'destructive' });
    } finally { if (alive.current) setBusy(false); }
  };
  const toggle = kind => setForm(current => ({ ...current, benefits: current.benefits.some(item => item.kind === kind)
    ? current.benefits.filter(item => item.kind !== kind) : [...current.benefits, { kind, ...fields[kind] }] }));
  const editBenefit = (kind, key, value) => setForm(current => ({ ...current, benefits: current.benefits.map(item => item.kind === kind ? { ...item, [key]: Number(value) } : item) }));
  return <Card>
    <div className="flex items-center justify-between gap-3"><h3 className="text-sm font-bold">{msg('FE_GIFT_TITLE', 'Gift campaigns')}</h3><button disabled={busy} onClick={() => { setForm(draft()); setConflict(false); }} className="text-xs font-bold text-primary">{msg('FE_GIFT_NEW', 'New campaign')}</button></div>
    <p className="my-2 text-xs text-muted-foreground">{msg('FE_GIFT_ADMIN_HELP', 'Choose one or several gifts. Each eligible account receives this campaign once, without approval. Editing preserves earned bundles; New campaign creates a new entitlement. Campaign gifts are additional to signup welcome credits.')}</p>
    {inherited && <p className="mb-2 text-xs text-muted-foreground">{msg('FE_ONBOARDING_INHERITED', 'Using global defaults')}</p>}
    {(error || conflict) && <button onClick={load} className="mb-3 text-sm font-bold text-primary">{msg('FE_GIFT_RELOAD', 'Reload campaign')}</button>}
    {!form && !error && <p role="status">{msg('FE_LOOKUP_SEARCHING', 'Searching…')}</p>}
    {form && <div className="space-y-3">
      <Field label={msg('FE_GIFT_NAME', 'Campaign name')}><TextInput value={form.name} disabled={busy} onChange={event => setForm({ ...form, name: event.target.value })} /></Field>
      <div className="flex items-center gap-2"><Toggle checked={form.enabled} disabled={busy} label={msg('FE_GIFT_ENABLE', 'Enable campaign')} onChange={enabled => setForm({ ...form, enabled })} /><span className="text-sm">{msg('FE_GIFT_ENABLE', 'Enable campaign')}</span></div>
      <Field label={msg('FE_GIFT_ELIGIBILITY', 'Who receives these gifts?')}><select aria-label={msg('FE_GIFT_ELIGIBILITY', 'Who receives these gifts?')} value={form.eligibility} disabled={busy} onChange={event => setForm({ ...form, eligibility: event.target.value })} className="w-full rounded-xl border border-border bg-card p-3 text-sm">
        <option value="signup">{msg('FE_GIFT_NEW_ACCOUNTS', 'Accounts created during the campaign')}</option>
        <option value="first_order">{msg('FE_GIFT_FIRST_ORDER', 'Customers starting their first paid order')}</option>
        <option value="everyone">{msg('FE_GIFT_EVERYONE', 'All eligible students')}</option>
      </select></Field>
      <p className="text-xs text-muted-foreground">{msg('FE_GIFT_FIRST_ORDER_HELP', 'First-order eligibility allows recovery after the first payment during this campaign. Existing customers with earlier paid orders do not qualify. Customers can claim before checkout; order gifts remain available for an eligible order.')}</p>
      <div className="grid gap-3 sm:grid-cols-2">{['starts_at', 'ends_at'].map(key => <Field key={key} label={key === 'starts_at' ? msg('FE_GIFT_START', 'Campaign starts') : msg('FE_GIFT_END', 'Campaign ends')}><TextInput type="datetime-local" value={localTime(form[key])} disabled={busy} onChange={event => setForm({ ...form, [key]: event.target.value ? asInstant(event.target.value) : null })} /></Field>)}</div>
      <p className="text-xs text-muted-foreground">{msg('FE_PROMO_TIMEZONE', 'Dates and times use Africa/Lagos (WAT).')}</p>
      <Field label={msg('FE_GIFT_VALIDITY', 'Order gift validity after claim (days)')}><TextInput type="number" min={1} max={365} step={1} value={form.validity_days} disabled={busy} onChange={event => setForm({ ...form, validity_days: Number(event.target.value) })} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">{Object.keys(fields).map(kind => {
        const benefit = form.benefits.find(item => item.kind === kind);
        return <section key={kind} className="rounded-xl border border-border p-3 space-y-2"><label className="flex items-center gap-2 text-sm font-semibold"><input type="checkbox" checked={!!benefit} disabled={busy} onChange={() => toggle(kind)} />{kindLabels()[kind]}</label>
          {benefit && Object.keys(fields[kind]).map(key => <Field key={key} label={fieldLabels()[key]}><TextInput type="number" min={key === 'multiplier' ? 1.01 : 1} max={key === 'credits' || key === 'multiplier' ? 10 : key === 'percent' ? 100 : 100000} step={['amount', 'credits'].includes(key) ? 1 : .01} value={benefit[key]} disabled={busy} onChange={event => editBenefit(kind, key, event.target.value)} /></Field>)}
        </section>;
      })}</div>
      <p className="text-xs text-muted-foreground">{msg('FE_GIFT_DELIVERY_HELP', 'Use 100% with a cap for a fixed delivery allowance, or a lower percentage for a percentage discount. Exclusive spins are not included. Gift choices never override paused feature releases.')}</p>
      <button disabled={busy || conflict || !form.name.trim() || !form.benefits.length || !form.starts_at || !form.ends_at} onClick={save} className="w-full rounded-full bg-gradient-cta py-3 text-sm font-bold text-white disabled:opacity-40">{busy ? msg('FE_ONBOARDING_SAVING', 'Saving…') : msg('FE_GIFT_SAVE', 'Save campaign')}</button>
    </div>}
  </Card>;
}
