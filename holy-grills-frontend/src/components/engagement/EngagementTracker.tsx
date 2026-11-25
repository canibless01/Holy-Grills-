import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { hasAnalyticsConsent, onConsentChange } from '@/lib/cookieConsent';
import { clearEngagementVisitor, engagementPath, recordEngagementPage } from '@/lib/engagementTracking';

/** Deferred, first-party analytics. Never blocks navigation, checkout or session recovery. */
export default function EngagementTracker() {
  const location = useLocation(); const { user, isLoading } = useHolyGrill(); const { campusId } = useCampus();
  const [consent, setConsent] = useState(false);
  const intent = useRef<{ key: string; id: string } | null>(null);
  useEffect(() => { setConsent(hasAnalyticsConsent()); const unsubscribe = onConsentChange(() => {
    const accepted = hasAnalyticsConsent(); setConsent(accepted); if (!accepted) clearEngagementVisitor();
  }); return () => { unsubscribe(); }; }, []);
  useEffect(() => {
    const path = engagementPath(location.pathname);
    if (!consent || isLoading || !campusId || !path || (user && user.role !== 'student')) return;
    const key = `${location.key}:${location.pathname}:${campusId}`;
    if (intent.current?.key !== key) intent.current = { key, id: crypto.randomUUID() };
    const id = intent.current.id;
    let active = true; let retry: ReturnType<typeof setTimeout> | undefined;
    const send = () => { void recordEngagementPage(id, path, campusId, !!user?.id).catch(() => {
      if (active) retry = setTimeout(() => { void recordEngagementPage(id, path, campusId, !!user?.id).catch(() => undefined); }, 1500);
    }); };
    const timer = setTimeout(send, 700);
    return () => { active = false; clearTimeout(timer); if (retry) clearTimeout(retry); };
  }, [location.key, location.pathname, campusId, consent, isLoading, user?.id, user?.role]);
  return null;
}
