import { useState, useEffect } from 'react';
import { X, Send, CalendarHeart } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useCampus } from '@/lib/campusContext';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';

const EMPTY = {
  organizer_name: '', email: '', phone: '', organization: '',
  event_name: '', event_date: '', expected_guests: '', budget: '', notes: '',
  hp_promo_optin: false,
};

export default function CateringRequestModal({ open, onClose }) {
  const { campusId } = useCampus();
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => { if (open) { setForm(EMPTY); setDone(false); } }, [open]);
  if (!open) return null;

  const set = (k) => (e) => setForm({ ...form, [k]: typeof e === 'boolean' ? e : e.target.value });

  const valid = form.organizer_name.trim() && form.email.includes('@') &&
    form.phone.match(/^(0|\+234)\d{10}$/) && form.event_name.trim() && form.event_date &&
    parseInt(form.expected_guests, 10) >= 1;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await liveApi.events.cateringRequest({
        ...form,
        campus_id: campusId,
        expected_guests: parseInt(form.expected_guests, 10),
        budget: form.budget ? Number(form.budget) : undefined,
      });
      setDone(true);
      toast({ title: '✅ Request submitted!', description: "Our team will contact you shortly." });
    } catch (e) {
      toast({ title: 'Submission failed', description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <ModalPortal>
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={onClose}>
        <div className="bg-card rounded-t-3xl sm:rounded-3xl p-6 w-full max-w-md max-h-[90vh] overflow-y-auto animate-slide-up" onClick={(e) => e.stopPropagation()}>
          {done ? (
            <div className="text-center py-8">
              <div className="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-3">
                <CalendarHeart className="w-8 h-8 text-success" />
              </div>
              <h3 className="font-heading font-bold text-lg text-foreground">Request Received!</h3>
              <p className="text-sm text-muted-foreground mt-1">We'll be in touch within 24 hours to discuss your event.</p>
              <button onClick={onClose} className="mt-5 px-6 py-3 rounded-2xl bg-gradient-cta text-white font-bold text-sm">Done</button>
            </div>
          ) : (
            <>
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-heading font-bold text-lg text-foreground flex items-center gap-2"><CalendarHeart className="w-5 h-5 text-primary" /> Request Catering</h3>
                <button onClick={onClose} className="p-1 rounded-full hover:bg-secondary"><X className="w-5 h-5 text-muted-foreground" /></button>
              </div>
              <p className="text-xs text-muted-foreground mb-4 leading-relaxed">Planning an event on campus? Tell us about it and our team will get back to you within 24 hours.</p>
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Organizer name *" value={form.organizer_name} onChange={set('organizer_name')} />
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Organization" value={form.organization} onChange={set('organization')} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Email *" type="email" value={form.email} onChange={set('email')} />
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Phone (080…)" value={form.phone} onChange={set('phone')} />
                </div>
                <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" placeholder="Event name *" value={form.event_name} onChange={set('event_name')} />
                <div className="grid grid-cols-2 gap-3">
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" type="date" value={form.event_date} onChange={set('event_date')} />
                  <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" type="number" placeholder="Expected guests *" value={form.expected_guests} onChange={set('expected_guests')} />
                </div>
                <input className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40" type="number" placeholder="Budget (₦) — optional" value={form.budget} onChange={set('budget')} />
                <textarea className="w-full p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary/40 resize-none" rows={3} placeholder="Notes — dietary needs, setup, anything else" value={form.notes} onChange={set('notes')} />
                <label className="flex items-center gap-2.5 p-3 rounded-xl bg-primary/5 border border-primary/20 cursor-pointer">
                  <input type="checkbox" checked={form.hp_promo_optin} onChange={(e) => set('hp_promo_optin')(e.target.checked)} className="w-4 h-4 rounded accent-primary" />
                  <span className="text-xs text-foreground leading-relaxed">Offer Holy Points rewards to my attendees</span>
                </label>
                <button onClick={handleSubmit} disabled={submitting || !valid} className="w-full py-3.5 rounded-2xl bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98] disabled:opacity-50">
                  <Send className="w-4 h-4" /> {submitting ? 'Submitting…' : 'Submit Request'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </ModalPortal>
  );
}