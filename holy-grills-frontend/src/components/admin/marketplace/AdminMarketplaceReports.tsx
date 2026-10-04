import { useState } from 'react';
import { RefreshCw, RotateCcw, X, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, Pill } from '../AdminShared';

// Resolve a reported broken code: replace (issue a fresh code), refund
// (wallet+HP refund, no restock) or reject (no problem confirmed). The PATCH
// route returns { message, status } — message is toasted verbatim.
const ACTIONS = [
  { key: 'replace', label: 'Replace code', icon: RefreshCw, btn: 'bg-green-600' },
  { key: 'refund', label: 'Refund buyer', icon: RotateCcw, btn: 'bg-blue-600' },
  { key: 'reject', label: 'Reject report', icon: X, btn: 'bg-red-600' },
];

export default function AdminMarketplaceReports({ reports, reload }) {
  const [acting, setActing] = useState(null); // { report, action }
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const body: { action: string; admin_note?: string } = { action: acting.action };
      if (note.trim()) body.admin_note = note.trim();
      const res = await liveApi.admin.resolveMarketplaceReport(acting.report.id, body);
      toast({ title: 'Report resolved', description: res?.message });
      setActing(null);
      setNote('');
      await reload();
    } catch (e) {
      toast({ title: 'Resolve failed', description: e.message, variant: 'destructive' });
    }
    setBusy(false);
  };

  return (
    <div className="space-y-2">
      {reports.map((r) => {
        const purchase = r.marketplace_purchases;
        const title = purchase?.marketplace_listings?.title || 'Listing';
        const buyer = r.profiles?.full_name || r.user_name || 'Buyer';
        return (
          <div key={r.id} className="rounded-2xl bg-white border border-border p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-bold text-sm text-foreground truncate">{title}</div>
                <div className="text-xs text-muted-foreground truncate">{buyer} · {timeAgo(r.created_at)}</div>
              </div>
              <Pill tone="amber">{r.status}</Pill>
            </div>
            <p className="text-xs text-foreground bg-secondary rounded-xl p-2.5">{r.reason}</p>
            <div className="flex gap-1">
              {ACTIONS.map((a) => (
                <button key={a.key} onClick={() => { setActing({ report: r, action: a.key }); setNote(''); }} className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-full text-[11px] font-bold text-white ${a.btn}`}>
                  <a.icon className="w-3.5 h-3.5" /> {a.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
      {reports.length === 0 && <p className="text-xs text-muted-foreground text-center py-6">No open reports.</p>}

      <Modal open={!!acting} onClose={() => setActing(null)} title="Resolve Report">
        {acting && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground capitalize">{acting.action} this report.</p>
            <Field label="Admin note (optional)">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" />
            </Field>
            <button onClick={submit} disabled={busy} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Working…</> : 'Confirm'}
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}