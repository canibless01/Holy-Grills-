import { Flame, MapPin } from 'lucide-react';
import { useCampus } from '@/lib/campusContext';
import { msg } from '@/lib/messages';

// Domain 0 — guest campus gate. The ONE campus picker, and the only place the
// campus list is rendered.
//
// Two modes:
//   'prompt'   — dismissible. Used on browse pages, where a guest must never be
//                trapped behind a picker.
//   'blocking' — not dismissible. Used on campus-scoped routes (menu, cart,
//                checkout, events, marketplace, leaderboard): those pages have
//                no meaningful content without a campus, so the guest picks one
//                or goes back. There is deliberately no close affordance and no
//                backdrop-dismiss in this mode.
//
// Campus-scoped pages render a compact placeholder instead of their content
// while no campus is chosen (src/components/CampusScope.tsx) rather than a
// second copy of this list, so the two are never on screen together.
//
// Signed-in users never see this: they are scoped server-side by the campus_id
// they chose at registration (see campusContext + CampusScope).
export default function CampusGate() {
  const {
    gateOpen, gateMode, campuses, campusesLoading, campusesError,
    selectCampus, dismissGate, reloadCampuses,
  } = useCampus();
  const dismissible = gateMode === 'prompt';
  const subtitle = msg('FE_CAMPUS_GATE_SUBTITLE', 'Pick your campus so we can show its menu, gates and delivery fees.');

  if (!gateOpen) return null;

  // A gate with nothing to choose from used to render `null`. That left the
  // route showing only its "Choose your campus" placeholder behind a button
  // that opened nothing: no list, no way out, and no explanation. Render a real
  // state instead — a spinner while the list is in flight, and a retry when it
  // cannot be read (the public /campuses endpoint failing, or a single-campus
  // deploy with no public list).
  if (campusesLoading) {
    return (
      <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4">
        <div className="bg-white rounded-3xl p-6 w-full max-w-sm text-center">
          <div className="w-8 h-8 mx-auto rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
          <p className="mt-4 text-sm font-semibold text-muted-foreground">Loading campuses…</p>
        </div>
      </div>
    );
  }

  if (campuses.length === 0) {
    return (
      <div className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4">
        <div className="bg-white rounded-3xl p-6 w-full max-w-sm text-center">
          <div className="w-12 h-12 rounded-2xl bg-gradient-cta flex items-center justify-center mx-auto mb-3 shadow-glow">
            <MapPin className="w-6 h-6 text-white" />
          </div>
          <h2 className="font-heading font-bold text-lg text-foreground">Choose your campus</h2>
          <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">
            {campusesError
              ? msg('FE_CAMPUS_GATE_LOAD_FAILED', "We couldn't load the campus list. Check your connection and try again.")
              : subtitle}
          </p>
          <button
            onClick={() => reloadCampuses()}
            className="mt-5 w-full py-3 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition"
          >
            {msg('FE_CAMPUS_GATE_RETRY', 'Try again')}
          </button>
          {dismissible && (
            <button
              onClick={dismissGate}
              className="mt-2 w-full py-2.5 rounded-full border border-border text-xs font-bold text-muted-foreground hover:text-foreground active:scale-95 transition"
            >
              Not now
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-[200] bg-black/60 backdrop-blur-md flex items-end sm:items-center justify-center p-4"
      onClick={dismissible ? dismissGate : undefined}
    >
      <div className="bg-white rounded-3xl p-6 w-full max-w-sm animate-slide-up">
        <div className="flex flex-col items-center text-center mb-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-cta flex items-center justify-center mb-2 shadow-glow">
            <Flame className="w-6 h-6 text-white" />
          </div>
          <h2 className="font-heading font-bold text-lg text-foreground">Choose your campus</h2>
          <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{subtitle}</p>
        </div>
        <div className="space-y-2 max-h-72 overflow-y-auto">
          {campuses.map((c) => (
            <button
              key={c.id}
              onClick={() => selectCampus(c.id)}
              className="w-full flex items-center gap-3 p-3 rounded-2xl border border-border hover:border-primary/60 hover:bg-primary/10 transition text-left active:scale-[0.99]"
            >
              <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                <MapPin className="w-4 h-4 text-primary" />
              </div>
              <div className="flex-1">
                <div className="font-bold text-sm text-foreground">{c.name}</div>
              </div>
            </button>
          ))}
        </div>
        {/* Campus-scoped routes (blocking) intentionally offer no way out — the
            action only proceeds once a campus is chosen. */}
        {dismissible && (
          <button
            onClick={(e) => { e.stopPropagation(); dismissGate(); }}
            className="mt-3 w-full py-2.5 rounded-full border border-border text-xs font-bold text-muted-foreground hover:text-foreground active:scale-95 transition"
          >
            Not now
          </button>
        )}
      </div>
    </div>
  );
}
