import { useState, useEffect } from 'react';
import { Users, Send, UserMinus, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

/**
 * SquadMembersPanel — per-order squad member management.
 * Order-scoped: removing a member here never touches the squad roster.
 * Resend re-invites an unregistered member; removal is blocked once the
 * order has been delivered (the backend enforces it too).
 */
/** A squad member row on an order (GET /api/orders/:id/squad-members). */
export interface SquadMemberRow {
  id: string | number;
  user_id?: string | number | null;
  email?: string;
  display_name?: string;
  hp_share?: number;
  is_registered?: boolean;
}

interface SquadMembersPanelProps {
  orderId: string;
  // Optional: when omitted the panel loads the roster itself.
  initialMembers?: SquadMemberRow[];
  delivered?: boolean;
}

export default function SquadMembersPanel({ orderId, initialMembers, delivered }: SquadMembersPanelProps) {
  const [members, setMembers] = useState<SquadMemberRow[] | null>(initialMembers || null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    if (initialMembers) return;
    liveApi.orders.getSquadMembers(orderId)
      .then((rows) => setMembers(Array.isArray(rows) ? rows : []))
      .catch(() => setMembers([]));
  }, [orderId, initialMembers]);

  if (!members || !members.length) return null;

  const resend = async (m: SquadMemberRow) => {
    setBusyId(m.id);
    try {
      await liveApi.orders.resendSquadMemberInvite(orderId, m.id);
      toast({ title: msg('FE_SQUAD_MEMBERS_PANEL_INVITE_RESENT', '📨 Invite resent'), description: m.email });
    } catch (e) {
      toast({ title: msg('FE_SQUAD_MEMBERS_PANEL_COULD_NOT_RESEND_INVITE', 'Could not resend invite'), description: e.message, variant: 'destructive' });
    }
    setBusyId(null);
  };

  const remove = async (m: SquadMemberRow) => {
    if (!confirm(`Remove ${m.display_name || m.email} from this order? The squad roster stays unchanged.`)) return;
    setBusyId(m.id);
    try {
      await liveApi.orders.removeSquadMember(orderId, m.id);
      setMembers((ms) => ms.filter((x) => x.id !== m.id));
      toast({ title: msg('FE_SQUAD_MEMBERS_PANEL_REMOVED_FROM_THIS_ORDER', 'Removed from this order') });
    } catch (e) {
      toast({ title: msg('FE_SQUAD_MEMBERS_PANEL_COULD_NOT_REMOVE_MEMBER', 'Could not remove member'), description: e.message, variant: 'destructive' });
    }
    setBusyId(null);
  };

  return (
    <div className="rounded-2xl bg-card border border-border p-4 shadow-card">
      <div className="flex items-center gap-2 mb-3">
        <Users className="w-4 h-4 text-primary" />
        <h3 className="font-bold text-sm text-foreground">Squad Members</h3>
        <span className="text-[11px] text-muted-foreground ml-auto">{members.length} on this order</span>
      </div>
      <div className="space-y-1.5">
        {members.map((m) => {
          const registered = m.is_registered !== false && m.user_id;
          return (
            <div key={m.id} className={`flex items-center gap-3 p-2.5 rounded-xl border ${registered ? 'bg-card border-border' : 'bg-accent/5 border-accent/20'}`}>
              <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center text-white text-sm font-bold shrink-0">
                {(m.display_name || m.email || '?').charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-foreground truncate">{m.display_name || m.email}</div>
                <div className="text-[11px] text-muted-foreground truncate">
                  {m.display_name ? `${m.email} · ` : ''}{registered ? 'joined' : 'invite pending'}
                  {m.hp_share != null ? ` · ${m.hp_share} HP share` : ''}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {!registered && (
                  <button onClick={() => resend(m)} disabled={busyId === m.id} className="p-2 rounded-lg text-primary hover:bg-primary/10 transition-colors disabled:opacity-50" aria-label="Resend invite">
                    {busyId === m.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  </button>
                )}
                {!delivered && (
                  <button onClick={() => remove(m)} disabled={busyId === m.id} className="p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50" aria-label="Remove from this order">
                    <UserMinus className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}