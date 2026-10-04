import React, { useState } from 'react';
import { Check, X, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, Pill } from '../AdminShared';

// Approve/reject a vendor listing request. The PATCH route accepts an optional
// admin_notes string, surfaced here so the vendor sees the reason in their
// notification. No backend success message is returned (just the updated row),
// so the toast is a plain action label, not a duplicated backend string.
export default function AdminMarketplaceRequests({ requests, reload }) {
  const [reviewing, setReviewing] = useState(null); // { row, status }
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const body = notes.trim() ? { admin_notes: notes.trim() } : {};
      if (reviewing.status === 'approved') await liveApi.admin.approveListingRequest(reviewing.row.id, body);
      else await liveApi.admin.rejectListingRequest(reviewing.row.id, body);
      toast({ title: reviewing.status === 'approved' ? 'Request approved' : 'Request rejected' });
      setReviewing(null);
      setNotes('');
      await reload();
    } catch (e) {
      toast({ title: 'Action failed', description: e.message, variant: 'destructive' });
    }
    setBusy(false);
  };

  return (
    <div className="space-y-2">
      {requests.map((r) => (
        <div key={r.id} className="rounded-2xl bg-white border border-border p-3 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="font-bold text-sm text-foreground truncate">{r.service_title || r.title}</div>
            <div className="text-xs text-muted-foreground truncate">{r.vendor_name || r.user_name} · {r.category || r.listing_type} · {formatNaira(r.proposed_price || r.price)}</div>
            {r.description && <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">{r.description}</p>}
          </div>
          {r.status === 'pending' ? (
            <div className="flex gap-1 shrink-0">
              <button onClick={() => { setReviewing({ row: r, status: 'approved' }); setNotes(''); }} title="Approve" className="p-2 rounded-lg bg-green-600 text-white"><Check className="w-4 h-4" /></button>
              <button onClick={() => { setReviewing({ row: r, status: 'rejected' }); setNotes(''); }} title="Reject" className="p-2 rounded-lg bg-red-600 text-white"><X className="w-4 h-4" /></button>
            </div>
          ) : <Pill tone={r.status === 'approved' ? 'green' : 'red'}>{r.status}</Pill>}
        </div>
      ))}
      {requests.length === 0 && <p className="text-xs text-muted-foreground text-center py-6">No vendor requests.</p>}

      <Modal open={!!reviewing} onClose={() => setReviewing(null)} title={reviewing?.status === 'approved' ? 'Approve Request' : 'Reject Request'}>
        {reviewing && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">{reviewing.row.vendor_name} — {reviewing.row.service_title}</p>
            <Field label="Admin note (optional)" hint="Sent to the vendor with the decision.">
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" />
            </Field>
            <button onClick={submit} disabled={busy} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Working…</> : `Confirm ${reviewing.status}`}
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}