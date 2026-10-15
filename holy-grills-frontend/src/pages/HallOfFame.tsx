import { useState, useEffect, useMemo } from 'react';
import { Share2, Award } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { isFeatureEnabled, useFeatureFlags } from '@/lib/featureConfig';
import HallOfFameSkeleton from '@/components/skeletons/HallOfFameSkeleton';
import MascotStandee from '@/components/mascot/MascotStandee';
import ShareSheet from '@/components/ShareSheet';
import { msg } from '@/lib/messages';

export default function HallOfFame() {
  useFeatureFlags();
  const [inductees, setInductees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [yearFilter, setYearFilter] = useState<string | number>('all');
  const [sharePayload, setSharePayload] = useState(null);
  const enabled = isFeatureEnabled('hall_of_fame', true);

  useEffect(() => {
    if (!enabled) { setLoading(false); return; }
    (async () => {
      try {
        const res = await liveApi.leaderboard.getInductees();
        // unwrap() already handles the inductees/winners/hall_of_fame keys.
        setInductees(res);
      } catch (e) {
        setError(msg('FE_HALL_OF_FAME_SOMETHING_SLIPPED_TRY_AGAIN', 'Something slipped. Try again.'));
      }
      setLoading(false);
    })();
  }, [enabled]);

  const years = useMemo(() => {
    const set = new Set<number>();
    inductees.forEach((entry) => {
      const dateStr = entry.inducted_at || entry.period_key || entry.period_label;
      if (dateStr) set.add(new Date(dateStr).getFullYear());
    });
    return ['all', ...Array.from(set).sort((a, b) => b - a)];
  }, [inductees]);

  const filtered = useMemo(() => {
    if (yearFilter === 'all') return inductees;
    return inductees.filter((entry) => {
      const dateStr = entry.inducted_at || entry.period_key || entry.period_label;
      return dateStr && new Date(dateStr).getFullYear() === Number(yearFilter);
    });
  }, [inductees, yearFilter]);

  // Share card comes from the admin-uploaded Hall of Fame template (storefront
  // share_template section keyed 'hall_of_fame_share') — tapping an inductee
  // opens it directly, with no intermediate card step.
  const handleShare = (inductee) => {
    const w = inductee?.winner || inductee || {};
    const name = w.full_name || w.name || inductee?.full_name || inductee?.name || 'This griller';
    const finishes = w.top4_finish_count || inductee?.top4_finish_count || w.streak_count || w.top4_finishes || 3;
    setSharePayload({
      headline: name,
      name,
      hp: w.hp_earned ?? inductee?.hp_earned ?? 0,
      value: `${finishes} Top 4 finishes`,
      caption: `${name} just got inducted into the Holy Grills Hall of Fame! 🔥`,
      link: typeof window !== 'undefined' ? window.location.origin : '',
    });
  };

  if (loading) return <HallOfFameSkeleton />;

  if (!enabled) {
    return (
      <div className="text-center py-16 px-4">
        <MascotStandee mascot="peace" className="w-32 h-32 mx-auto mb-3" alt="Hall of Fame coming soon" />
        <h2 className="font-heading font-bold text-lg text-foreground">Hall of Fame is coming soon</h2>
        <p className="text-sm text-muted-foreground mt-1">Inductees are added after each season. Check back!</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Hero strip — the page IS a trophy case, so it opens on the dark brand
          bed + living gold, the same materials as the Holy tier ring. */}
      <div className="rounded-3xl bg-gradient-dark relative overflow-hidden shadow-glow p-6 text-white">
        <div className="absolute inset-0 tier-shimmer-holy opacity-[0.08] pointer-events-none" />
        <div className="relative flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-cta flex items-center justify-center text-2xl shrink-0 shadow-glow">🏅</div>
          <div>
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-accent block">Legends</span>
            <h1 className="font-heading font-extrabold text-2xl leading-tight">Hall of Fame</h1>
            <p className="text-xs text-white/70 mt-0.5">Month after month at the top. Tap a name to share their card.</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl tone-error border border-destructive/30 p-4 flex items-center justify-between gap-3">
          <span className="text-sm text-destructive font-medium">{error}</span>
          <button onClick={() => window.location.reload()} className="px-3 py-1.5 rounded-xl bg-destructive text-white text-xs font-bold">Retry</button>
        </div>
      )}

      {/* Year filter */}
      {years.length > 2 && (
        <div className="flex gap-2 overflow-x-auto scrollbar-hide">
          {years.map((y) => (
            <button
              key={y}
              onClick={() => setYearFilter(y)}
              className={`shrink-0 px-4 py-2 rounded-xl text-xs font-semibold transition-all ${yearFilter === String(y) ? 'bg-primary text-white' : 'bg-card text-foreground border border-border'}`}
            >
              {y === 'all' ? 'All Time' : y}
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="rounded-2xl bg-card border border-border p-8 text-center shadow-card">
          <MascotStandee mascot="peace" className="w-28 h-28 mx-auto mb-2" alt="No Hall of Fame inductees yet" />
          <p className="text-sm font-semibold text-foreground">The first spot is open.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {filtered.map((entry, i) => {
            const w = entry.winner || entry;
            const name = w.full_name || w.name || 'Griller';
            const finishes = w.top4_finish_count || entry.top4_finish_count || w.streak_count || w.top4_finishes || 3;
            const period = entry.period_key || entry.period_label || entry.inducted_at;
            return (
              <div
                key={entry.id || w.user_id || i}
                onClick={() => handleShare(entry)}
                className="rounded-2xl bg-gradient-dark p-4 text-white relative overflow-hidden cursor-pointer hg-press"
              >
                {/* Plaque treatment — gold shimmer bed + a living-gold top edge
                    + a holy-ring avatar, so each inductee reads as a mounted
                    plaque rather than a dark row. */}
                <div className="absolute inset-0 tier-shimmer-holy opacity-10 pointer-events-none" />
                <div className="absolute inset-x-0 top-0 h-[3px] tier-shimmer-holy" />
                <div className="flex items-center gap-3 relative">
                  <div className="w-12 h-12 rounded-full tier-ring-holy p-[3px] shrink-0">
                    <span className="w-full h-full rounded-full bg-gradient-dark flex items-center justify-center text-xl font-bold">{name.charAt(0)}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-heading font-bold text-base flex items-center gap-1.5 truncate">
                      {name}
                      <span className="text-accent shrink-0">🏅</span>
                    </div>
                    <div className="text-xs text-accent/90 font-semibold flex items-center gap-1">
                      <Award className="w-3 h-3 shrink-0" /> {finishes} Top 4 {finishes === 1 ? 'finish' : 'finishes'}
                    </div>
                    {period && <div className="text-[10px] text-white/50 mt-0.5">Inducted {new Date(period).toLocaleDateString()}</div>}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleShare(entry); }}
                    className="px-3 py-2 rounded-full bg-accent text-accent-foreground text-xs font-bold flex items-center gap-1 active:scale-95 transition-transform shrink-0"
                  >
                    <Share2 className="w-3.5 h-3.5" /> Share
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ShareSheet
        open={!!sharePayload}
        onClose={() => setSharePayload(null)}
        type="achievement"
        templateKey="hall_of_fame_share"
        payload={sharePayload || {}}
      />
    </div>
  );
}