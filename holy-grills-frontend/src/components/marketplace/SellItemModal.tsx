import { useState, useEffect } from 'react';
import { X, Send, Store } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';
import { msg } from '@/lib/messages';

const CATEGORIES = [
  { value: 'voucher', label: 'Voucher' },
  { value: 'event_ticket', label: 'Event Ticket' },
  { value: 'goodie', label: 'Goodie' },
  { value: 'service', label: 'Service' },
  { value: 'product', label: 'Product' },
];

const EMPTY = { vendor_name: '', vendor_email: '', vendor_phone: '', service_title: '', category: 'voucher', description: '', proposed_price: '' };

export default function SellItemModal({ open, onClose }) {
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { if (open) setForm(EMPTY); }, [open]);
  if (!open) return null;

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const valid = form.vendor_name.trim() && form.vendor_email.trim() && form.service_title.trim() && form.description.trim() && form.proposed_price;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const res = await liveApi.marketplace.request({
        vendor_name: form.vendor_name.trim(),
        vendor_email: form.vendor_email.trim(),
        vendor_phone: form.vendor_phone.trim() || undefined,
        service_title: form.service_title.trim(),
        category: form.category,
        description: form.description.trim(),
        proposed_price: Number(form.proposed_price),
      });
      toast({ title: msg('FE_SELL_ITEM_MODAL_REQUEST_SUBMITTED', 'Request submitted'), description: res?.message || "We'll review your listing and get back to you." });
      onClose();
    } catch (e) {
      toast({ title: msg('FE_SELL_ITEM_MODAL_SUBMISSION_FAILED', 'Submission failed'), description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={onClose}>
        <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-md animate-slide-up max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><Store className="w-5 h-5 text-primary" /> Selling opens soon.</h3>
            <button onClick={onClose} className="p-1 rounded-full hover:bg-secondary"><X className="w-5 h-5 text-muted-foreground" /></button>
          </div>
          <p className="text-xs text-muted-foreground mb-4 leading-relaxed">Fill in your vendor details and what you'd like to sell. An admin will review your listing before it goes live.</p>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Vendor Name *</label>
                <input value={form.vendor_name} onChange={set('vendor_name')} placeholder="Your name" className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Vendor Email *</label>
                <input type="email" value={form.vendor_email} onChange={set('vendor_email')} placeholder="you@email.com" className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
              </div>
            </div>
            <div>
              <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Phone (optional)</label>
              <input type="tel" value={form.vendor_phone} onChange={set('vendor_phone')} placeholder="0801 234 5678" className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Item Title *</label>
              <input value={form.service_title} onChange={set('service_title')} placeholder="e.g., Netflix Premium 1-Month Voucher" className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Category *</label>
                <select value={form.category} onChange={set('category')} className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40 bg-card">
                  {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Price (₦) *</label>
                <input type="number" value={form.proposed_price} onChange={set('proposed_price')} placeholder="5000" className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" />
              </div>
            </div>
            <div>
              <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Description *</label>
              <textarea value={form.description} onChange={set('description')} placeholder="Describe what you're selling — condition, specs, delivery method." rows={3} className="w-full mt-1 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40 resize-none" />
            </div>
            <button onClick={handleSubmit} disabled={submitting || !valid} className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-50">
              <Send className="w-4 h-4" /> {submitting ? 'Submitting…' : 'Submit for Review'}
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}