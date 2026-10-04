import { useState, useEffect } from 'react';
import { Bike, Phone, MapPin, Wallet, ChevronDown, ChevronRight, Check, Eye } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { formatNaira, formatDateTime, timeAgo } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Modal, Field, TextInput, Pill } from './AdminShared';
import { toast } from '@/components/ui/use-toast';

// Riders tab for AdminDelivery — backed by riders.py /api/riders/admin/*.
// Roster (who is online), payments summary, per-rider batches with set-pay +
// mark paid/unpaid, and a per-order pay breakdown modal.
export default function AdminRiders() {
  const [tab, setTab] = useState('roster');
  const [roster, setRoster] = useState([]);
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null); // rider_id whose batches are open
  const [riderBatches, setRiderBatches] = useState({}); // rider_id -> { batches, loading }
  const [payModal, setPayModal] = useState(null); // { batch }
  const [breakdownModal, setBreakdownModal] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setLoading(true);
    const [r, p] = await Promise.all([
      mockApi.admin.getRiderRoster(),
      mockApi.admin.getRiderPayments({ period: 'all' }),
    ]);
    setRoster(r || []);
    setPayments(p || []);
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const toggleRider = async (riderId) => {
    if (expanded === riderId) { setExpanded(null); return; }
    setExpanded(riderId);
    if (!riderBatches[riderId]) {
      setRiderBatches((s) => ({ ...s, [riderId]: { loading: true } }));
      try {
        const res = await mockApi.admin.getRiderPaymentBatches(riderId, { period: 'all' });
        setRiderBatches((s) => ({ ...s, [riderId]: { batches: res?.batches || [], loading: false } }));
      } catch (e) {
        setRiderBatches((s) => ({ ...s, [riderId]: { batches: [], loading: false, error: e.message } }));
      }
    }
  };

  const reloadRider = async (riderId) => {
    try {
      const res = await mockApi.admin.getRiderPaymentBatches(riderId, { period: 'all' });
      setRiderBatches((s) => ({ ...s, [riderId]: { batches: res?.batches || [], loading: false } }));
    } catch { /* keep stale */ }
    await load();
  };

  const markPaid = async (batchId, riderId) => {
    setBusy(batchId);
    try {
      const res = await mockApi.admin.markBatchesPaid([batchId]);
      const skipped = res?.skipped?.length || 0;
      const notFound = res?.not_found?.length || 0;
      if (skipped || notFound) toast({ title: 'Marked paid', description: `${(res?.updated || []).length} paid · ${skipped} skipped · ${notFound} not found`, variant: 'default' });
      else toast({ title: '✅ Marked paid' });
      await reloadRider(riderId);
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  const markUnpaid = async (batchId, riderId) => {
    setBusy(batchId);
    try {
      await mockApi.admin.markBatchesUnpaid([batchId]);
      toast({ title: 'Marked unpaid' });
      await reloadRider(riderId);
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (loading) return <LoadingSpinner label="Loading riders..." />;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-full bg-secondary">
        {[{ id: 'roster', label: 'Roster' }, { id: 'payments', label: 'Payments' }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`flex-1 py-2 rounded-full text-xs font-bold ${tab === t.id ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}>{t.label}</button>
        ))}
      </div>

      {tab === 'roster' && (
        <div className="space-y-2">
          {roster.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground text-sm"><Bike className="w-8 h-8 mx-auto mb-2 text-muted-foreground" /> No riders on this campus yet.</div>
          ) : roster.map((r) => (
            <div key={r.rider_id} className="rounded-2xl bg-white border border-border p-3 flex items-center gap-3">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${r.is_available ? 'bg-green-100' : 'bg-secondary'}`}><Bike className={`w-4 h-4 ${r.is_available ? 'text-green-600' : 'text-muted-foreground'}`} /></div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="font-bold text-sm text-foreground">{r.full_name || 'Rider'}</div>
                  {r.is_available ? <Pill tone="green">Online</Pill> : <Pill tone="cocoa">Offline</Pill>}
                  {r.active_batches > 0 && <Pill tone="amber">{r.active_batches} active</Pill>}
                </div>
                <div className="text-xs text-muted-foreground flex items-center gap-2 flex-wrap">
                  {r.phone && <span className="flex items-center gap-0.5"><Phone className="w-3 h-3" />{r.phone}</span>}
                  {r.location_lat != null && r.location_lng != null && <span className="flex items-center gap-0.5"><MapPin className="w-3 h-3" />{Number(r.location_lat).toFixed(4)}, {Number(r.location_lng).toFixed(4)}</span>}
                  {r.availability_updated_at && <span>· updated {timeAgo(r.availability_updated_at)}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'payments' && (
        <div className="space-y-2">
          {payments.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground text-sm"><Wallet className="w-8 h-8 mx-auto mb-2 text-muted-foreground" /> No rider payments yet.</div>
          ) : payments.map((r) => {
            const rid = r.rider_id || r.id;
            const isOpen = expanded === rid;
            const rb = riderBatches[rid] || {};
            return (
              <div key={rid} className="rounded-2xl bg-white border border-border overflow-hidden">
                <button onClick={() => toggleRider(rid)} className="w-full flex items-center gap-3 p-3 text-left">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center shrink-0 bg-primary/10"><Bike className="w-4 h-4 text-primary" /></div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-sm text-foreground">{r.full_name || 'Rider'}</div>
                    <div className="text-xs text-muted-foreground">Earned {formatNaira(r.total_earnings ?? r.earnings ?? 0)} · Paid {formatNaira(r.total_paid ?? r.paid ?? 0)} · Outstanding {formatNaira(r.outstanding ?? 0)}{r.batch_count != null ? ` · ${r.batch_count} batches` : ''}</div>
                  </div>
                  {isOpen ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
                </button>
                {isOpen && (
                  <div className="border-t border-border p-3 space-y-2 bg-muted/30">
                    {rb.loading && <div className="text-xs text-muted-foreground text-center py-3">Loading batches…</div>}
                    {rb.error && <div className="text-xs text-destructive text-center py-3">{rb.error}</div>}
                    {!rb.loading && (rb.batches || []).length === 0 && <div className="text-xs text-muted-foreground text-center py-3">No completed batches.</div>}
                    {(rb.batches || []).map((b) => {
                      const batchId = b.batch_id || b.id;
                      const amount = b.rider_pay_total ?? b.amount;
                      const paid = !!b.rider_paid_at;
                      return (
                        <div key={batchId} className="rounded-xl bg-white border border-border p-2.5 flex items-center gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-bold text-foreground">{b.zone || 'Batch'} · {b.order_count ?? 0} orders</div>
                            <div className="text-[11px] text-muted-foreground">{b.completed_at ? formatDateTime(b.completed_at) : ''}</div>
                          </div>
                          {amount != null ? <span className="text-xs font-bold text-foreground">{formatNaira(amount)}</span> : <Pill tone="amber">Unpriced</Pill>}
                          {paid ? <Pill tone="green">Paid</Pill> : amount != null ? <Pill tone="amber">Unpaid</Pill> : null}
                          <button onClick={() => setPayModal({ ...b, rider_id: rid })} title="Set pay" className="p-1.5 rounded-lg hover:bg-muted"><Wallet className="w-3.5 h-3.5 text-muted-foreground" /></button>
                          <button onClick={() => setBreakdownModal(batchId)} title="Pay breakdown" className="p-1.5 rounded-lg hover:bg-muted"><Eye className="w-3.5 h-3.5 text-muted-foreground" /></button>
                          {paid
                            ? <button onClick={() => markUnpaid(batchId, rid)} disabled={busy === batchId} className="px-2 py-1 rounded-full bg-secondary text-[11px] font-bold disabled:opacity-50">{busy === batchId ? '…' : 'Unpay'}</button>
                            : amount != null && <button onClick={() => markPaid(batchId, rid)} disabled={busy === batchId} className="flex items-center gap-0.5 px-2 py-1 rounded-full bg-green-600 text-white text-[11px] font-bold disabled:opacity-50"><Check className="w-3 h-3" />{busy === batchId ? '…' : 'Pay'}</button>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {payModal && <SetPayModal batch={payModal} onClose={() => setPayModal(null)} onSaved={() => reloadRider(payModal.rider_id)} />}
      {breakdownModal && <BreakdownModal batchId={breakdownModal} onClose={() => setBreakdownModal(null)} />}
    </div>
  );
}

// Set a batch's rider pay — PATCH /riders/admin/batches/<id>/pay { rider_pay_total }.
function SetPayModal({ batch, onClose, onSaved }) {
  const [amount, setAmount] = useState(batch.rider_pay_total ?? batch.amount ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    setError(null);
    const value = Number(amount);
    if (!Number.isFinite(value) || value < 0) { setError('Enter a valid amount.'); return; }
    setSubmitting(true);
    try {
      await mockApi.admin.setBatchPay(batch.batch_id || batch.id, { rider_pay_total: value });
      toast({ title: '✅ Pay saved', description: formatNaira(value) });
      onSaved(); onClose();
    } catch (e) { setError(e.message); }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title="Set Rider Pay">
      <div className="space-y-3">
        <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">{batch.zone || 'Batch'} · {batch.order_count ?? 0} orders</div>
        <Field label="Rider pay total (₦)"><TextInput type="number" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        {error && <p className="text-[11px] font-bold text-destructive text-center">⚠ {error}</p>}
        <button onClick={submit} disabled={submitting} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{submitting ? 'Saving...' : 'Save Pay'}</button>
      </div>
    </Modal>
  );
}

// Per-order pay breakdown — GET /riders/admin/batches/<id>/pay-breakdown.
function BreakdownModal({ batchId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await mockApi.admin.getBatchPayBreakdown(batchId);
        setData(res);
      } catch (e) { setError(e.message); }
      setLoading(false);
    })();
  }, [batchId]);

  return (
    <Modal open onClose={onClose} title="Pay Breakdown">
      {loading ? <div className="text-xs text-muted-foreground text-center py-6">Loading…</div>
        : error ? <p className="text-[11px] font-bold text-destructive text-center">⚠ {error}</p>
        : (
          <div className="space-y-2">
            {(data?.orders || []).length === 0 && <div className="text-xs text-muted-foreground text-center py-4">No breakdown rows.</div>}
            {(data?.orders || []).map((o, i) => (
              <div key={o.order_id || i} className="rounded-xl bg-muted border border-border p-2.5 flex items-center justify-between">
                <div className="text-xs text-foreground font-mono">#{(o.order_id || '').slice(0, 8).toUpperCase()}</div>
                <div className="text-xs font-bold text-foreground">{formatNaira(o.pay_component ?? o.amount ?? 0)}</div>
              </div>
            ))}
            {data?.orders?.length > 0 && <div className="text-[11px] text-muted-foreground text-center pt-1">For records only — never shown to riders.</div>}
          </div>
        )}
    </Modal>
  );
}