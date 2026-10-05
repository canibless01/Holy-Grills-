import { useState, useEffect } from 'react';
import { Trophy, Gift, Check, Clock } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Card, Pill, SectionHeader, Modal, Field, TextInput } from './AdminShared';
import { msg } from '@/lib/messages';

export default function AdminLeaderboard() {
  const [tab, setTab] = useState('rewards');
  const [rewards, setRewards] = useState([]);
  const [rewardHistory, setRewardHistory] = useState([]);
  const [hof, setHof] = useState([]);
  const [hofHistory, setHofHistory] = useState([]);
  const [busy, setBusy] = useState(null);
  const [loaded, setLoaded] = useState(false);
  const [advance, setAdvance] = useState(null); // { id, name, nextStatus, notes }
  const [lbNotes, setLbNotes] = useState({}); // per-prize notes for leaderboard fulfilment

  const load = async () => {
    try {
      const [pending, fulfilled, hofAll] = await Promise.all([
        mockApi.admin.getLeaderboardRewards({ status: 'pending' }).catch(() => []),
        mockApi.admin.getLeaderboardRewards({ status: 'fulfilled' }).catch(() => []),
        mockApi.admin.getHallOfFameRewards().catch(() => []),
      ]);
      setRewards(pending || []);
      setRewardHistory(fulfilled || []);
      const all = hofAll || [];
      setHof(all.filter((h) => h.status !== 'fulfilled'));
      setHofHistory(all.filter((h) => h.status === 'fulfilled'));
    } catch { /* empty */ }
    setLoaded(true);
  };

  useEffect(() => { load(); }, []);

  const fulfillReward = async (id, userName) => {
    setBusy(id);
    try {
      const res = await mockApi.admin.fulfillLeaderboardReward(id, { status: 'fulfilled', notes: lbNotes[id] || '' });
      toast({ title: res?.message || 'Reward fulfilled' });
      setLbNotes((prev) => { const n = { ...prev }; delete n[id]; return n; });
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_LEADERBOARD_FULFILLMENT_FAILED', 'Fulfillment failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  const submitAdvance = async () => {
    if (!advance) return;
    setBusy(advance.id);
    try {
      const res = await mockApi.admin.updateHallOfFameReward(advance.id, { status: advance.nextStatus, notes: advance.notes || '' });
      toast({ title: res?.message || 'Reward updated' });
      setAdvance(null);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_LEADERBOARD_UPDATE_FAILED', 'Update failed'), description: e.message, variant: 'destructive' });
    }
    setBusy(null);
  };

  if (!loaded) return <LoadingSpinner label="Loading..." />;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-full bg-secondary">
        {[{ id: 'rewards', label: 'Leaderboard Rewards' }, { id: 'hof', label: 'Hall of Fame' }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`flex-1 py-2 rounded-full text-xs font-bold ${tab === t.id ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}>{t.label}</button>
        ))}
      </div>

      {tab === 'rewards' ? (
        <div className="space-y-4">
          <div>
            <SectionHeader title="Pending Fulfillment" action={<Pill tone="amber">{rewards.length} pending</Pill>} />
            {rewards.length === 0 ? (
              <Card><p className="text-xs text-muted-foreground text-center py-4">No pending rewards. All caught up! 🎉</p></Card>
            ) : (
              <div className="space-y-2">
                {rewards.map((r) => (
                  <Card key={r.id}>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-cta text-white flex items-center justify-center font-bold text-sm shrink-0">#{r.rank}</div>
                      <div className="flex-1 min-w-0">
                        <div className="font-bold text-sm text-foreground">{r.user_name || r.full_name || 'User'}</div>
                        <div className="text-xs text-muted-foreground flex items-center gap-1.5"><Gift className="w-3 h-3" /> {r.reward_description || r.prize || '—'}</div>
                        {r.phone && <div className="text-[11px] text-muted-foreground mt-0.5">{r.phone}</div>}
                      </div>
                      <Pill tone="amber"><Clock className="w-3 h-3 inline mr-0.5" />Pending</Pill>
                      <button onClick={() => fulfillReward(r.id, r.user_name || r.full_name)} disabled={busy === r.id} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-green-600 text-white text-xs font-bold disabled:opacity-50">
                        <Check className="w-3.5 h-3.5" /> {busy === r.id ? '...' : 'Fulfill'}
                      </button>
                    </div>
                    <input
                      value={lbNotes[r.id] || ''}
                      onChange={(e) => setLbNotes((prev) => ({ ...prev, [r.id]: e.target.value }))}
                      placeholder="Fulfilment notes (optional)…"
                      className="w-full mt-2 px-3 py-1.5 rounded-lg border border-border text-xs"
                    />
                  </Card>
                ))}
              </div>
            )}
          </div>

          {rewardHistory.length > 0 && (
            <div>
              <SectionHeader title="Fulfillment History" action={<Pill tone="green">{rewardHistory.length} fulfilled</Pill>} />
              <div className="space-y-2">
                {rewardHistory.map((r) => (
                  <div key={r.id} className="rounded-xl bg-muted border border-border p-3 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-green-100 text-green-600 flex items-center justify-center text-xs font-bold">#{r.rank}</div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm text-foreground">{r.user_name || r.full_name}</div>
                      <div className="text-xs text-muted-foreground">{r.reward_description || r.prize}</div>
                    </div>
                    <Pill tone="green"><Check className="w-3 h-3 inline mr-0.5" />Fulfilled</Pill>
                    {r.fulfilled_at && <span className="text-[10px] text-muted-foreground">{new Date(r.fulfilled_at).toLocaleDateString()}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <SectionHeader title="Pending Inductees" action={<Pill tone="amber">{hof.length} pending</Pill>} />
            {hof.length === 0 ? (
              <Card><p className="text-xs text-muted-foreground text-center py-4">No pending Hall of Fame inductees. Induction is automatic at 4 top-4 finishes.</p></Card>
            ) : (
              <div className="space-y-2">
                {hof.map((h) => {
                  const status = h.status || 'pending';
                  const isCancelled = status === 'cancelled';
                  const isBoxPrepared = status === 'box_prepared';
                  return (
                    <Card key={h.id}>
                      <div className="flex items-center gap-3 flex-wrap">
                        <Trophy className="w-5 h-5 text-amber-500 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="font-bold text-sm text-foreground">{h.user_name || h.full_name || 'Inductee'}</div>
                          <div className="text-xs text-muted-foreground">Inducted {(h.inducted_at || h.induction_date) ? new Date(h.inducted_at || h.induction_date).toLocaleDateString() : '—'}{h.phone ? ` · ${h.phone}` : ''}</div>
                        </div>
                        {isCancelled ? (
                          <Pill tone="red">Cancelled</Pill>
                        ) : isBoxPrepared ? (
                          <Pill tone="blue">Box prepared</Pill>
                        ) : (
                          <Pill tone="amber"><Clock className="w-3 h-3 inline mr-0.5" />Pending</Pill>
                        )}
                        {!isCancelled && (
                          <div className="flex items-center gap-1.5">
                            {!isBoxPrepared && (
                              <button onClick={() => setAdvance({ id: h.id, name: h.user_name || h.full_name, nextStatus: 'box_prepared', notes: h.notes || '' })} disabled={busy === h.id} className="px-3 py-1.5 rounded-full bg-blue-600 text-white text-xs font-bold disabled:opacity-50">
                                {busy === h.id ? '...' : 'Box prepared'}
                              </button>
                            )}
                            <button onClick={() => setAdvance({ id: h.id, name: h.user_name || h.full_name, nextStatus: 'fulfilled', notes: h.notes || '' })} disabled={busy === h.id} className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-green-600 text-white text-xs font-bold disabled:opacity-50">
                              <Check className="w-3.5 h-3.5" /> {busy === h.id ? '...' : 'Fulfill'}
                            </button>
                            <button onClick={() => setAdvance({ id: h.id, name: h.user_name || h.full_name, nextStatus: 'cancelled', notes: h.notes || '' })} disabled={busy === h.id} className="px-3 py-1.5 rounded-full bg-red-100 text-red-700 text-xs font-bold disabled:opacity-50">
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>

          {hofHistory.length > 0 && (
            <div>
              <SectionHeader title="Fulfillment History" />
              <div className="space-y-2">
                {hofHistory.map((h) => (
                  <div key={h.id} className="rounded-xl bg-muted border border-border p-3 flex items-center gap-3">
                    <Trophy className="w-4 h-4 text-amber-500" />
                    <div className="flex-1">
                      <div className="font-semibold text-sm text-foreground">{h.user_name || h.full_name}</div>
                      <div className="text-xs text-muted-foreground">Inducted {(h.inducted_at || h.induction_date) ? new Date(h.inducted_at || h.induction_date).toLocaleDateString() : '—'}</div>
                    </div>
                    <Pill tone="green"><Check className="w-3 h-3 inline mr-0.5" />Fulfilled</Pill>
                  </div>
                ))}
              </div>
            </div>
          )}

          {advance && (
            <Modal open onClose={() => setAdvance(null)} title={`Advance — ${advance.name}`}>
              <div className="space-y-3">
                <div className="rounded-xl bg-muted p-3 text-xs text-muted-foreground">Move this inductee to <b className="capitalize">{advance.nextStatus.replace(/_/g, ' ')}</b>. This is logged to the audit trail.</div>
                <Field label="Notes (optional)"><TextInput value={advance.notes} onChange={(e) => setAdvance({ ...advance, notes: e.target.value })} placeholder="e.g. Box handed to student" /></Field>
                <button onClick={submitAdvance} disabled={busy === advance.id} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{busy === advance.id ? 'Updating...' : `Mark ${advance.nextStatus.replace(/_/g, ' ')}`}</button>
              </div>
            </Modal>
          )}
        </div>
      )}
    </div>
  );
}