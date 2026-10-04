import React from 'react';
import { Flame, MapPin } from 'lucide-react';
import { useCampus } from '@/lib/campusContext';

// Domain 0 — guest campus gate. Blocking (non-cancelable) on campus-scoped
// routes; dismissible when shown as the homepage prompt.
export default function CampusGate() {
  const { gateOpen, gateAction, gateMode, campuses, selectCampus, dismissGate } = useCampus();
  if (!gateOpen || campuses.length === 0) return null;
  const dismissible = gateMode === 'prompt';

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
          <p className="text-xs text-muted-foreground mt-1">Pick your campus to {gateAction}. You only do this once this session.</p>
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
        {/* Campus-scoped routes (blocking): no close affordance — the action
            only proceeds once a campus is chosen. Homepage prompt: dismissible. */}
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