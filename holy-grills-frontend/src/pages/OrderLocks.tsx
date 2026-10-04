import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Lock, Clock, Flame, X, Calendar, RefreshCw, Gift } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { orderLockMaxReschedules } from '@/lib/appConfig';
import { toast } from '@/components/ui/use-toast';
import { fadeUp, staggerContainer } from '@/lib/animationPresets';
import MascotStandee from '@/components/mascot/MascotStandee';

const LOCK_STATUS_LABELS = {
  active: 'Active',
  used: 'Used',
  consumed: 'Used',
  expired: 'Expired',
  cancelled: 'Cancelled',
};
const LOCK_STATUS_COLORS = {
  active: 'bg-success/15 text-success',
  used: 'bg-primary/10 text-primary',
  consumed: 'bg-primary/10 text-primary',
  expired: 'bg-muted text-muted-foreground',
  cancelled: 'bg-destructive/10 text-destructive',
};

export default function OrderLocks() {
  const navigate = useNavigate();
  const [locks, setLocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [rescheduleLock, setRescheduleLock] = useState(null);
  const [rescheduleDate, setRescheduleDate] = useState('');
  const [rescheduling, setRescheduling] = useState(false);

  const [form, setForm] = useState({ locked_date: '', reward_kind: 'discount' });

  useEffect(() => { load(); }, []);

  const load = async () => {
    setLoading(true);
    setError(null);
    try { setLocks(((await liveApi.orderLocks.list()) || {}).locks || []); } catch (e) { console.error(e); setError('Something slipped. Try again.'); }
    setLoading(false);
  };

  const handleCreate = async () => {
    if (!form.locked_date) { toast({ title: 'Pick a date', description: 'Choose a future date to lock.' }); return; }
    if (new Date(form.locked_date) <= new Date(new Date().toDateString())) {
      toast({ title: 'Must be a future date', description: 'The lock date has to be after today.' }); return;
    }
    const maxCreate = new Date(); maxCreate.setDate(maxCreate.getDate() + 7);
    if (new Date(form.locked_date) > maxCreate) {
      toast({ title: 'Too far ahead', description: 'You can only lock a date within the next 7 days.' }); return;
    }
    setCreating(true);
    try {
      const body = { locked_date: form.locked_date, reward_type: form.reward_kind === 'hp' ? 'hp' : 'discount' };
      await liveApi.orderLocks.create(body);
      toast({ title: '🔒 Lock created', description: `Locked for ${new Date(form.locked_date).toLocaleDateString()}.` });
      setShowCreate(false);
      setForm({ ...form, locked_date: '' });
      load();
    } catch (e) {
      toast({ title: 'Lock failed', description: e.message, variant: 'destructive' });
    }
    setCreating(false);
  };

  const handleCancel = async (id) => {
    if (!confirm('Cancel this order lock? You will lose the locked reward.')) return;
    try { await liveApi.orderLocks.cancel(id); load(); } catch (e) { toast({ title: 'Cancel failed', description: e.message, variant: 'destructive' }); }
  };

  const handleReschedule = async () => {
    if (!rescheduleLock || !rescheduleDate) return;
    if (new Date(rescheduleDate) <= new Date(new Date().toDateString())) { toast({ title: 'Must be a future date' }); return; }
    const maxReschedule = new Date(); maxReschedule.setDate(maxReschedule.getDate() + 3);
    if (new Date(rescheduleDate) > maxReschedule) {
      toast({ title: 'Too far ahead', description: 'Reschedule must be within the next 3 days.' }); return;
    }
    setRescheduling(true);
    try {
      await liveApi.orderLocks.reschedule(rescheduleLock.id, { locked_date: rescheduleDate });
      toast({ title: '🔒 Rescheduled', description: `Lock moved to ${new Date(rescheduleDate).toLocaleDateString()}.` });
      setRescheduleLock(null);
      load();
    } catch (e) { toast({ title: 'Reschedule failed', description: e.message, variant: 'destructive' }); }
    setRescheduling(false);
  };

  if (loading) {
    return (
      <div className="space-y-3 animate-fade-in">
        <div className="h-8 w-40 bg-muted rounded animate-pulse" />
        <div className="h-24 bg-muted rounded-2xl animate-pulse" />
        <div className="h-32 bg-muted rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4 animate-fade-in">
        <div>
          <span className="hg-eyebrow">Lock in a reward</span>
          <h1 className="font-heading font-bold text-xl text-foreground mt-0.5">Order Locks</h1>
          <p className="text-sm text-muted-foreground mt-1">Plan it. Claim it.</p>
        </div>
        <div className="text-center py-12 space-y-3">
          <MascotStandee mascot="worried" className="w-28 h-28 mx-auto" alt="Could not load order locks" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <button onClick={() => load()} className="px-4 py-2 rounded-xl bg-primary text-white text-xs font-bold hover:bg-primary-hover active:scale-95 transition">Retry</button>
        </div>
      </div>
    );
  }

  const dateOptions = (days) => Array.from({ length: days }).map((_, i) => {
    const d = new Date(); d.setDate(d.getDate() + i + 1); return d.toISOString().split('T')[0];
  });
  // Same-day locks are not allowed. A lock can be scheduled for the next 7 days,
  // and rescheduled once within another 3 days — a 10-day max lifespan.
  const tomorrow = dateOptions(1)[0];
  const maxCreate = dateOptions(7)[6];
  const maxReschedule = dateOptions(3)[2];

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <span className="hg-eyebrow">Lock in a reward</span>
          <h1 className="font-heading font-bold text-xl text-foreground mt-0.5">Order Locks 🔒</h1>
          <p className="text-sm text-muted-foreground mt-1">Pick a date. We bring the reward.</p>
          <p className="text-xs text-muted-foreground/80 mt-1">Order that day and it applies automatically. Plans change, so you can reschedule.</p>
        </div>
        <motion.button whileTap={{ scale: 0.95 }} onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow">
          <Lock className="w-3.5 h-3.5" /> New Lock
        </motion.button>
      </div>

      {/* Education */}
      <div className="rounded-2xl bg-primary/5 border border-primary/20 p-4">
        <div className="flex items-center gap-2 mb-1">
          <Lock className="w-4 h-4 text-primary" />
          <span className="font-bold text-sm text-foreground">How Order Locks work</span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Pick a day and a reward. Order that day and it applies. After lock, you can reschedule once.
        </p>
      </div>

      {/* Locks */}
      {locks.length === 0 ? (
        <div className="text-center py-12 space-y-3">
          <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto" alt="No order locks scheduled" />
          <div>
            <p className="text-sm text-foreground font-semibold">No locks yet.</p>
          </div>
          <button onClick={() => setShowCreate(true)} className="px-5 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow">Create your first lock</button>
        </div>
      ) : (
        <motion.div variants={staggerContainer(0.05)} initial="hidden" animate="show" className="space-y-3">
          {locks.map((lock) => {
            const lockedDate = lock.locked_date ? new Date(lock.locked_date) : null;
            const daysToLock = lockedDate ? Math.ceil((lockedDate.getTime() - Date.now()) / (24 * 60 * 60 * 1000)) : null;
            const isHp = (lock.reward_type || lock.reward) === 'hp';
            const status = lock.status || (lock.consumed_at ? 'used' : 'active');
            const isActive = status === 'active';
            const rescheduleCount = lock.reschedule_count || 0;
            const maxReschedules = orderLockMaxReschedules();
            const canReschedule = isActive && rescheduleCount < maxReschedules;
            return (
              <motion.div key={lock.id} variants={fadeUp} className={`rounded-2xl bg-card border-2 p-4 ${isActive ? 'border-primary/20' : 'border-border opacity-70'}`}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${LOCK_STATUS_COLORS[status] || 'bg-muted text-muted-foreground'}`}>{LOCK_STATUS_LABELS[status] || status}</span>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      {lockedDate ? `Locked for ${lockedDate.toLocaleDateString()}` : ''}
                      {lock.consumed_at && ` · claimed ${new Date(lock.consumed_at).toLocaleDateString()}`}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-xs font-bold text-primary">
                      {isHp ? <><Gift className="w-3.5 h-3.5" />{lock.reward_hp_amount || 0} HP</> : <><Flame className="w-3 h-3" />{lock.discount_pct || 0}% off</>}
                    </div>
                  </div>
                </div>

                {isActive && (
                  <>
                    <div className="flex items-center gap-2 text-xs mb-3">
                      <Clock className={`w-3.5 h-3.5 ${daysToLock <= 1 ? 'text-primary' : 'text-muted-foreground'}`} />
                      <span className={daysToLock <= 1 ? 'text-primary font-bold' : 'text-muted-foreground'}>
                        {daysToLock > 0 ? `${daysToLock} day${daysToLock !== 1 ? 's' : ''} until your lock date` : 'Lock date is today. Order to claim!'}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => navigate('/menu')} className="flex-1 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow">Order to claim</button>
                      <button
                        onClick={() => { setRescheduleLock(lock); setRescheduleDate(dateOptions(3)[0]); }}
                        disabled={!canReschedule}
                        className={`px-3 py-2.5 rounded-xl text-xs font-bold flex items-center gap-1 transition-colors ${canReschedule ? 'bg-accent/10 border border-accent/30 text-accent-foreground hover:bg-accent/20' : 'bg-muted border border-border text-muted-foreground cursor-not-allowed'}`}
                      >
                        <RefreshCw className="w-3 h-3" /> {rescheduleCount >= maxReschedules ? 'Rescheduled' : 'Reschedule'}
                      </button>
                      <button onClick={() => handleCancel(lock.id)} className="px-4 py-2.5 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs font-bold hover:bg-destructive/20 transition-colors">Cancel</button>
                    </div>
                  </>
                )}
              </motion.div>
            );
          })}
        </motion.div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !creating && setShowCreate(false)}>
          <div className="bg-card rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-heading font-bold text-base text-foreground flex items-center gap-2"><Lock className="w-5 h-5 text-primary" /> New Order Lock</h3>
              <button onClick={() => setShowCreate(false)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wide">Lock date (future)</label>
                <input type="date" min={tomorrow} max={maxCreate} value={form.locked_date} onChange={(e) => setForm({ ...form, locked_date: e.target.value })} className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => setForm({ ...form, reward_kind: 'discount' })} className={`p-3 rounded-xl border-2 text-center transition-all ${form.reward_kind === 'discount' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30'}`}>
                  <Flame className="w-5 h-5 mx-auto mb-1 text-primary" />
                  <span className="text-xs font-bold">Discount %</span>
                </button>
                <button onClick={() => setForm({ ...form, reward_kind: 'hp' })} className={`p-3 rounded-xl border-2 text-center transition-all ${form.reward_kind === 'hp' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30'}`}>
                  <Gift className="w-5 h-5 mx-auto mb-1 text-accent-foreground" />
                  <span className="text-xs font-bold">HP Reward</span>
                </button>
              </div>
              <div className="rounded-xl bg-muted/60 border border-border p-3 text-[11px] text-muted-foreground leading-relaxed">
                {form.reward_kind === 'discount'
                  ? 'Lock in a discount. It applies on your lock date.'
                  : "Lock in an HP reward. It lands on your lock date."}
              </div>
              <button onClick={handleCreate} disabled={creating} className="w-full py-3.5 rounded-xl bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2 shadow-glow">
                {creating ? <><div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Creating...</> : 'Create lock'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reschedule modal */}
      {rescheduleLock && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4" onClick={() => !rescheduling && setRescheduleLock(null)}>
          <div className="bg-card rounded-2xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-heading font-bold text-base text-foreground flex items-center gap-2"><Calendar className="w-5 h-5 text-primary" /> Reschedule Lock</h3>
              <button onClick={() => setRescheduleLock(null)}><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>
            <p className="text-xs text-muted-foreground mb-3">Move this lock to a new future date within the next 3 days. You can only reschedule once.</p>
            <input type="date" min={tomorrow} max={maxReschedule} value={rescheduleDate} onChange={(e) => setRescheduleDate(e.target.value)} className="w-full p-3 rounded-xl border border-border text-sm mb-3 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all" />
            <button onClick={handleReschedule} disabled={rescheduling} className="w-full py-3.5 rounded-xl bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2 shadow-glow">
              {rescheduling ? <><div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> Rescheduling...</> : `Move to ${rescheduleDate ? new Date(rescheduleDate).toLocaleDateString() : '—'}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}