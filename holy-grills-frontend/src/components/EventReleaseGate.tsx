import { Link, Outlet } from 'react-router-dom';
import { CalendarDays } from 'lucide-react';
import { isFeatureEnabled, useFeatureFlags } from '@/lib/featureConfig';
import { msg, useMessages } from '@/lib/messages';

export default function EventReleaseGate() {
  useFeatureFlags();
  useMessages();
  if (isFeatureEnabled('events', false)) return <Outlet />;
  return <section className="rounded-3xl border border-border bg-card p-8 text-center space-y-3">
    <CalendarDays className="w-10 h-10 text-primary mx-auto" />
    <h1 className="font-heading text-2xl font-bold">{msg('FE_EVENTS_COMING_SOON', 'Events are coming soon')}</h1>
    <p className="text-sm text-muted-foreground">{msg('FE_EVENTS_RELEASE_BODY', 'We are getting our events ready. Food ordering is open while we prepare.')}</p>
    <Link to="/menu" className="inline-flex rounded-full bg-gradient-cta text-white font-bold text-sm px-5 py-3">{msg('FE_ORDER_STREAK_MENU', 'Browse menu')}</Link>
  </section>;
}
