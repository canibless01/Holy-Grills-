import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Users, UserPlus, UserMinus, Mail, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira, formatDate, ORDER_STATUS_LABELS } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';

export default function SquadDetail({ squadId, currentUserId, onBack }) {
  const navigate = useNavigate();
  const [squad, setSquad] = useState(null);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newEmail, setNewEmail] = useState('');
  const [adding, setAdding] = useState(false);

  const load = async () => {
    try {
      const [s, o] = await Promise.allSettled([liveApi.squads.get(squadId), liveApi.squads.getOrders(squadId)]);
      if (s.status === 'fulfilled') setSquad(s.value);
      if (o.status === 'fulfilled') setOrders(Array.isArray(o.value) ? o.value : []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [squadId]);

  const isOrganizer = squad && squad.creator_id === currentUserId;

  const handleAddMember = async () => {
    const email = newEmail.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { toast({ title: 'Enter a valid email address' }); return; }
    setAdding(true);
    try {
      await liveApi.squads.addMember(squadId, { email });
      setNewEmail('');
      toast({ title: '👍 Member added', description: email });
      load();
    } catch (e) {
      toast({ title: 'Could not add member', description: e.message, variant: 'destructive' });
    }
    setAdding(false);
  };

  const handleRemoveMember = async (m) => {
    if (!confirm(`Remove ${m.display_name || m.email} from the squad?`)) return;
    try {
      await liveApi.squads.removeMember(squadId, m.id);
      toast({ title: 'Member removed', description: 'They no longer join new squad orders.' });
      load();
    } catch (e) {
      toast({ title: 'Could not remove member', description: e.message, variant: 'destructive' });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 animate-fade-in">
        <Loader2 className="w-6 h-6 text-muted-foreground animate-spin" />
      </div>
    );
  }

  if (!squad) {
    return (
      <div className="space-y-4 animate-fade-in">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ChevronLeft className="w-4 h-4" /> Back to squads
        </button>
        <div className="text-center py-16 space-y-3">
          <p className="text-sm text-muted-foreground">Squad not found.</p>
        </div>
      </div>
    );
  }

  const roster = squad.roster || [];

  return (
    <div className="space-y-4 animate-fade-in pb-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Back to squads
      </button>

      <div className="rounded-2xl bg-gradient-dark p-5 text-white relative overflow-hidden">
        <div className="absolute -right-6 -top-6 text-8xl opacity-20 select-none">👥</div>
        <div className="relative">
          <span className="text-[10px] font-bold uppercase tracking-wider text-accent">Squad</span>
          <h1 className="font-heading font-extrabold text-xl mt-0.5">{squad.name}</h1>
          <p className="text-xs text-white/70 mt-1">
            {isOrganizer ? 'You organize this squad' : 'You\'re on this roster'} · created {formatDate(squad.created_at)}
          </p>
        </div>
      </div>

      {/* Roster */}
      <div className="rounded-2xl bg-card border border-border p-4">
        <div className="flex items-center gap-2 mb-3">
          <Users className="w-4 h-4 text-primary" />
          <h3 className="font-heading font-bold text-sm text-foreground">Roster</h3>
          <span className="text-[11px] text-muted-foreground ml-auto">{roster.filter((m) => m.is_active !== false).length} active</span>
        </div>

        {isOrganizer && (
          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddMember(); } }}
                placeholder="Add a friend by email"
                className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
              />
            </div>
            <button onClick={handleAddMember} disabled={adding} className="px-3.5 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow disabled:opacity-60 shrink-0 flex items-center gap-1">
              {adding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserPlus className="w-3.5 h-3.5" />} Add
            </button>
          </div>
        )}

        {roster.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center">No members yet — invite your crew to start earning together.</p>
        ) : (
          <div className="space-y-1.5">
            {roster.map((m) => (
              <div key={m.id} className={`flex items-center gap-3 p-2.5 rounded-xl border ${m.is_active === false ? 'bg-muted/50 border-border opacity-60' : 'bg-card border-border'}`}>
                <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center text-white text-sm font-bold shrink-0">
                  {(m.display_name || m.email || '?').charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-foreground truncate">{m.display_name || m.email}</div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {m.display_name ? m.email : ''}
                    {m.is_active === false ? ' · removed' : ''}
                  </div>
                </div>
                {m.is_active !== false && (
                  <div className="text-right shrink-0">
                    <div className="text-xs font-bold text-primary tabular-nums">{m.cumulative_hp ?? 0} HP</div>
                    <div className="text-[9px] text-muted-foreground uppercase tracking-wide">{m.user_id ? 'joined' : 'invite sent'}</div>
                  </div>
                )}
                {isOrganizer && m.is_active !== false && (
                  <button onClick={() => handleRemoveMember(m)} className="text-muted-foreground hover:text-destructive transition-colors shrink-0 p-1" aria-label="Remove member">
                    <UserMinus className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Order history */}
      <div className="rounded-2xl bg-card border border-border p-4">
        <h3 className="font-heading font-bold text-sm text-foreground mb-3">Squad order history</h3>
        {orders.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center">No squad orders yet — tag an order to this squad at checkout.</p>
        ) : (
          <div className="space-y-1.5">
            {orders.map((o) => (
              <button
                key={o.id}
                onClick={() => navigate(`/orders/${o.id}`)}
                className="w-full flex items-center gap-3 p-2.5 rounded-xl border border-border hover:border-primary/40 transition-colors text-left"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-foreground">#{(o.order_number || o.id || '').toUpperCase()}</div>
                  <div className="text-[11px] text-muted-foreground">
                    {o.squad_item_count ?? '—'} items · {formatDate(o.created_at)}
                    {o.delivered_at ? ` · delivered ${formatDate(o.delivered_at)}` : ''}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xs font-bold text-foreground">{formatNaira(o.total_amount)}</div>
                  <div className="text-[10px] text-muted-foreground capitalize">{ORDER_STATUS_LABELS[o.status] || o.status}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}