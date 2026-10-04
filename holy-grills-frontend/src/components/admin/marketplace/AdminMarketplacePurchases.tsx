import React, { useState } from 'react';
import { Package, RotateCcw, Ban, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, timeAgo } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, Pill } from '../AdminShared';

// Purchase status transitions: pending → completed | refunded | cancelled.
// refunded/cancelled trigger a real wallet+HP refund server-side; the route
// returns { message, purchase_id, old_status, status } — we toast message verbatim.
// A purchase already refunded/cancelled is final and cannot be changed again.
const STATUS_TONE = { pending: 'amber', completed: 'green', refunded: 'blue', cancelled: 'red' };

export default function AdminMarketplacePurchases({ purchases, reload }) {
  const [acting, setActing] = useState(null); // { purchase, status }
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const body: { status: string; admin_note?: string } = { status: acting.status };
      if (note.trim()) body.admin_note = note.trim();
      const res = await liveApi.admin.updateMarketplacePurchase(acting.purchase.id, body);
      toast({ title: 'Purchase updated', description: res?.message });
      setActing(null);
      setNote('');
      await reload();
    } catch (e) {
      toast({ title: 'Update failed', description: e.message, variant: 'destructive' });
    }
    setBusy(false);
  };

  return (
    <div className="space-y-2">
      {purchases.map((p) => {
        const title = p.marketplace_listings?.title || p.listing_title || 'Listing';
        const buyer = p.profiles?.full_name || p.user_name || 'Buyer';
        const paid = (p.wallet_amount || 0) + (p.card_amount || 0);
        const final = p.status === 'refunded' || p.status === 'cancelled';
        return (
          <div key={p.id} className="rounded-2xl bg-white border border-border p-3 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center shrink-0"><Package className="w-5 h-5 text-muted-foreground" /></div>
            <div className="flex-1 min-w-0">
              <div className="font-bold text-sm text-foreground truncate">{title}</div>
              <div className="text-xs text-muted-foreground truncate">{buyer} · {formatNaira(paid)} · {timeAgo(p.created_at)}</div>
            </div>
            <Pill tone={STATUS_TONE[p.status] || 'cocoa'}>{p.status}</Pill>
            {p.status === 'pending' && (
              <div className="flex gap-1 shrink-0">
                <button onClick={() => { setActing({ purchase: p, status: 'completed' }); setNote(''); }} title="Mark completed" className="p-2 rounded-lg bg-green-600 text-white"><Package className="w-4 h-4" /></button>
                <button onClick={() => { setActing({ purchase: p, status: 'refunded' }); setNote(''); }} title="Refund" className="p-2 rounded-lg bg-blue-600 text-white"><RotateCcw className="w-4 h-4" /></button>
                <button onClick={() => { setActing({ purchase: p, status: 'cancelled' }); setNote(''); }} title="Cancel" className="p-2 rounded-lg bg-red-600 text-white"><Ban className="w-4 h-4" /></button>
              </div>
            )}
          </div>
        );
      })}
      {purchases.length === 0 && <p className="text-xs text-muted-foreground text-center py-6">No purchases.</p>}

      <Modal open={!!acting} onClose={() => setActing(null)} title={`${acting?.status ? acting.status[0].toUpperCase() + acting.status.slice(1) : ''} Purchase`}>
        {acting && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {acting.status === 'completed' ? 'Fulfil this purchase — the buyer receives their access code.' : 'This refunds the buyer\'s wallet and HP, and restocks the code. This cannot be undone.'}
            </p>
            <Field label="Admin note (optional)">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" />
            </Field>
            <button onClick={submit} disabled={busy} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50">
              {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Working…</> : `Confirm ${acting.status}`}
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
}