import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';

type Config = { recipients: string[]; paid_order_alerts: boolean; abandoned_cart_alerts: boolean; daily_report: boolean; weekly_report: boolean; abandoned_minutes: number };
type Receipt = { id: string; kind: string; recipient: string; state: string; created_at: string };
const switches = { paid_order_alerts: 'Paid order alerts', abandoned_cart_alerts: 'Abandoned cart alerts', daily_report: 'Daily summary', weekly_report: 'Weekly summary' };
export default function OperationsEmailControls({ value, campusId, editable, busy, onSave }: { value: Config; campusId: string; editable: boolean; busy: boolean; onSave: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [addresses, setAddresses] = useState(value.recipients.join(', '));
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => { setDraft(value); setAddresses(value.recipients.join(', ')); }, [value]);
  useEffect(() => {
    let active = true; setLoading(true); setError('');
    liveApi.admin.getOperationsEmails(campusId).then((result) => {
      if (active) setReceipts(result.recent || []);
    }).catch((e) => { if (active) setError(e.message || 'Could not load delivery status.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [campusId, refresh]);
  const save = (event: React.FormEvent) => {
    event.preventDefault();
    const recipients = [...new Set(addresses.split(/[;,\n]/).map((s) => s.trim().toLowerCase()).filter(Boolean))];
    if (recipients.length > 5 || recipients.some((s) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s))) {
      setError('Enter up to five complete email addresses.'); return;
    }
    onSave(JSON.stringify({ ...draft, recipients }));
  };
  return <div className="mt-3 space-y-4">
    <form onSubmit={save} className="space-y-3">
      <label className="block text-sm font-semibold">Report and alert recipients
        <textarea value={addresses} disabled={!editable || busy} onChange={(e) => setAddresses(e.target.value)} rows={2} className="mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm" placeholder="campus@example.com" />
      </label>
      <p className="text-xs text-muted-foreground">Separate addresses with commas. Only these inboxes receive this campus’s operational mail.</p>
      <div className="grid gap-2 sm:grid-cols-2">{Object.entries(switches).map(([key, label]) => <label key={key} className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={Boolean(draft[key])} disabled={!editable || busy} onChange={(e) => setDraft({ ...draft, [key]: e.target.checked })} />{label}
      </label>)}</div>
      <label className="block text-sm">Alert staff after cart inactivity (minutes)
        <input type="number" min={10} max={1440} required value={draft.abandoned_minutes} disabled={!editable || busy} onChange={(e) => setDraft({ ...draft, abandoned_minutes: Number(e.target.value) })} className="ml-2 w-24 rounded-lg border border-border bg-background p-2" />
      </label>
      <p className="text-xs text-muted-foreground">Daily summaries cover the previous day. Weekly summaries cover Monday–Sunday. Nigeria time; super-admin customer tests excluded. Alerts are checked every ten minutes.</p>
      {editable && <button type="submit" disabled={busy} className="rounded-full bg-primary px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-50">{busy ? 'Saving…' : 'Save operations email'}</button>}
    </form>
    <div className="border-t border-border pt-3">
      <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">Recent operational emails</h3><button type="button" disabled={loading} onClick={() => setRefresh((n) => n + 1)} className="text-xs text-primary">Refresh status</button></div>
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
      {loading ? <p role="status" className="text-xs text-muted-foreground">Loading status…</p> : !error && receipts.length === 0 ? <p className="text-xs text-muted-foreground">No operational emails queued yet.</p> : <ul className="mt-2 space-y-2">{receipts.map((row) => <li key={row.id} className="flex flex-wrap justify-between gap-2 rounded-lg bg-secondary p-2 text-xs"><span className="min-w-0 break-all">{row.kind.replace(/_/g, ' ')} · {row.recipient}</span><span>{row.state === 'accepted' ? 'Provider accepted' : row.state === 'uncertain' ? 'Needs delivery review' : row.state}</span></li>)}</ul>}
      <p className="mt-2 text-xs text-muted-foreground">Provider acceptance is not an inbox-delivery receipt. Uncertain sends are held for review to avoid duplicates.</p>
    </div>
  </div>;
}
