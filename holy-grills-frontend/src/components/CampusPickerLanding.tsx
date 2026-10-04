/**
 * Campus picker landing (Track B, §6 item 1)
 * ============================================================================
 * Campus-scoped routes used to render a skeleton (while the campus list loads)
 * or nothing at all (while the blocking CampusGate is open). Neither is indexable
 * and neither tells a visitor what the page is for.
 *
 * This is the guest view for those routes when a campus still has to be chosen:
 * a real heading, a description of what the page offers, the campus list and a
 * short "what's waiting" list. The gate modal still opens on top of it — the
 * picker itself is content, not the chooser.
 *
 * It renders identically on the server (the build-time pre-render has no campus
 * and no API data) and on the first client render, which is what keeps hydration
 * clean. Campus names arrive from the API at runtime; before that the page names
 * the university from config, so the pre-rendered HTML never shows an empty list.
 */
import { Flame, MapPin } from 'lucide-react';
import APP_CONFIG from '@/config/app.config';
import { useCampus } from '@/lib/campusContext';

export interface CampusPickerCopy {
  /** <h1> — descriptive, since this is what a crawler indexes for the route. */
  title: string;
  intro: string;
  bullets: string[];
}

export default function CampusPickerLanding({ title, intro, bullets }: CampusPickerCopy) {
  const { campuses } = useCampus();
  // Real names once the public campus list resolves; the configured university
  // before that (and in the pre-rendered HTML, which runs no API calls).
  const names = campuses.length ? campuses.map((c) => c.name) : [APP_CONFIG.university];

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto py-2">
      <div className="text-center pt-2">
        <span className="hg-eyebrow">Choose your campus</span>
        <h1 className="font-heading font-extrabold text-2xl text-foreground mt-1">{title}</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">{intro}</p>
      </div>

      <ul className="space-y-2">
        {names.map((name) => (
          <li key={name} className="flex items-center gap-3 p-3 rounded-2xl border border-border bg-card">
            <span className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <MapPin className="w-4 h-4 text-primary" />
            </span>
            <span className="font-bold text-sm text-foreground">{name}</span>
          </li>
        ))}
      </ul>

      <div className="rounded-2xl border border-border bg-card p-4">
        <h2 className="font-heading font-bold text-sm text-foreground flex items-center gap-1.5">
          <Flame className="w-3.5 h-3.5 text-primary" /> What's waiting
        </h2>
        <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground">
          {bullets.map((b) => (
            <li key={b} className="flex gap-1.5">
              <span className="text-primary">•</span>
              {b}
            </li>
          ))}
        </ul>
      </div>

      <p className="text-[11px] text-muted-foreground text-center">
        Pick once and it sticks for the session — the campus picker opens on top of this page.
      </p>
    </div>
  );
}
