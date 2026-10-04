import { useState, useEffect, useCallback } from 'react';
import { Users, Plus, ChevronRight } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { formatDate } from '@/lib/hgUtils';
import CreateSquadModal from '@/components/squads/CreateSquadModal';
import MascotStandee from '@/components/mascot/MascotStandee';
import SquadDetail from '@/components/squads/SquadDetail';
import SquadsSkeleton from '@/components/skeletons/SquadsSkeleton';

export default function Squads() {
  const { user } = useHolyGrill();
  const [squads, setSquads] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    try { setSquads(await liveApi.squads.list()); } catch { setSquads([]); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (selectedId) {
    return <SquadDetail squadId={selectedId} currentUserId={user?.id} onBack={() => { setSelectedId(null); load(); }} />;
  }

  return (
    <div className="space-y-4 animate-fade-in pb-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className="hg-eyebrow">Feast together</span>
          <h1 className="font-heading font-bold text-xl text-foreground mt-0.5">My Squads 👥</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Your people. One order.</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow shrink-0 active:scale-95 transition">
          <Plus className="w-4 h-4" /> New squad
        </button>
      </div>

      {squads === null ? (
        <SquadsSkeleton />
      ) : squads.length === 0 ? (
        <div className="text-center py-16 space-y-3 rounded-2xl border-2 border-dashed border-border">
          <MascotStandee mascot="peace" className="w-28 h-28 mx-auto" alt="No squads yet" />
          <p className="text-sm font-semibold text-foreground">No squads yet.</p>
          <button onClick={() => setShowCreate(true)} className="px-5 py-2.5 rounded-xl bg-gradient-cta text-white text-xs font-bold shadow-glow">Create your first squad</button>
        </div>
      ) : (
        <div className="space-y-2.5">
          {squads.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelectedId(s.id)}
              className="w-full flex items-center gap-3 p-4 rounded-2xl bg-card border border-border hover:border-primary/40 active:scale-[0.99] transition-all text-left"
            >
              <div className="w-11 h-11 rounded-xl bg-gradient-dark flex items-center justify-center shrink-0">
                <Users className="w-5 h-5 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-heading font-bold text-sm text-foreground truncate">{s.name}</div>
                <div className="text-[11px] text-muted-foreground">
                  {s.creator_id === user?.id ? 'You organize this squad' : 'You\'re on the roster'} · created {formatDate(s.created_at)}
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
            </button>
          ))}
        </div>
      )}

      <CreateSquadModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => { setShowCreate(false); load(); }}
      />
    </div>
  );
}