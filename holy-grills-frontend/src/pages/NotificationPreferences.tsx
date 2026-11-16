import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Bell, Mail, Package, Truck, Flame, Tag } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import PreferenceRow from '@/components/notifications/PreferenceRow';
import PushPermissionBanner from '@/components/notifications/PushPermissionBanner';
import { msg, useMessages } from '@/lib/messages';

export default function NotificationPreferences() {
  useMessages();
  const TOGGLES = [
    { key: 'push_enabled', label: msg('FE_PREF_PUSH', 'Push notifications'), desc: msg('FE_PREF_PUSH_HELP', 'Receive alerts on your device'), icon: Bell },
    { key: 'email_enabled', label: msg('FE_PREF_EMAIL', 'Email notifications'), desc: msg('FE_PREF_EMAIL_HELP', 'Receive updates via email'), icon: Mail },
    { key: 'order_updates', label: msg('FE_PREF_ORDER', 'Order updates'), desc: msg('FE_PREF_ORDER_HELP', 'Status changes, confirmations'), icon: Package },
    { key: 'delivery_updates', label: msg('FE_PREF_DELIVERY', 'Delivery updates'), desc: msg('FE_PREF_DELIVERY_HELP', 'Rider assigned, out for delivery'), icon: Truck },
    { key: 'hp_updates', label: msg('FE_PREF_HP', 'HP updates'), desc: msg('FE_PREF_HP_HELP', 'HP earned, tiers, unlocks'), icon: Flame },
    { key: 'promotions', label: msg('FE_PREF_PROMOTIONS', 'Promotions'), desc: msg('FE_PREF_PROMOTIONS_HELP', 'Flash redeems, offers, events'), icon: Tag },
  ];
  const { user } = useHolyGrill();
  const readVersion = useRef(0);
  const saveLock = useRef(false);
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    const version = ++readVersion.current;
    setLoading(true);
    setLoadError(false);
    try {
      const result = await liveApi.notifications.getPreferences();
      if (version !== readVersion.current) return;
      const data = result && result.data ? result.data : result || {};
      // The backend returns effective channel settings, including legacy opt-outs.
      setPrefs({
        push_enabled: data.push_enabled ?? true,
        email_enabled: data.email_enabled ?? true,
        order_updates: data.order_updates ?? true,
        delivery_updates: data.delivery_updates ?? true,
        hp_updates: data.hp_updates ?? true,
        promotions: data.promotions ?? true,
      });
    } catch {
      if (version === readVersion.current) setLoadError(true);
    }
    if (version === readVersion.current) setLoading(false);
  }, [user?.id]);

  useEffect(() => { void load(); return () => { readVersion.current++; }; }, [load]);

  const toggle = async (key, next) => {
    if (saveLock.current || !prefs) return;
    saveLock.current = true;
    const version = readVersion.current;
    const previousValue = prefs[key];
    setPrefs(current => ({ ...current, [key]: next }));
    setSavingKey(key);
    try {
      await liveApi.notifications.updatePreferences({ [key]: next });
      if (version !== readVersion.current) return;
      toast({ title: msg('FE_NOTIFICATION_PREFERENCES_NOTIFICATION_SETTINGS_UPDATED', 'Notification settings updated.') });
    } catch {
      if (version !== readVersion.current) return;
      setPrefs(current => ({ ...current, [key]: previousValue }));
      toast({ title: msg('FE_NOTIFICATION_PREFERENCES_FAILED_TO_UPDATE_NOTIFICATION', 'Failed to update notification preferences.'), variant: 'destructive' });
    } finally { saveLock.current = false; setSavingKey(null); }
  };

  if (loadError) return <div className="text-center py-16 space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;

  if (loading || !prefs) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in max-w-xl mx-auto">
      <div className="flex items-center gap-2">
        <button
          onClick={() => navigate('/profile')}
          className="p-2 -ml-2 rounded-full hover:bg-secondary active:scale-95 transition"
          aria-label={msg('FE_PREF_BACK', 'Back to profile')}
        >
          <ArrowLeft className="w-5 h-5 text-foreground" />
        </button>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">{msg('FE_PREF_TITLE', 'Preferences')}</h1>
      </div>

      <PushPermissionBanner enabled={prefs.push_enabled} onEnabled={() => setPrefs(previous => ({ ...previous, push_enabled: true }))} />

      <section className="space-y-2.5">
        <h2 className="font-heading font-extrabold text-base text-foreground px-1">{msg('FE_PREF_RECEIVE', 'What you receive')}</h2>
        {TOGGLES.map((t) => {
          const Icon = t.icon;
          return (
            <PreferenceRow
              key={t.key}
              icon={Icon}
              label={t.label}
              desc={t.desc}
              enabled={!!prefs[t.key]}
              onToggle={(next) => toggle(t.key, next)}
              disabled={!!savingKey}
            />
          );
        })}
      </section>

      <div className="rounded-2xl bg-secondary/60 border border-border p-4">
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          {msg('FE_PREF_POLICY', 'Your channel and category choices control alerts. Account and wallet receipts are separate from promotional preferences. Promotional alerts follow the platform rate limits.')}
        </p>
      </div>
    </div>
  );
}
