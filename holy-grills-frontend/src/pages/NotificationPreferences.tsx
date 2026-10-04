import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Bell, Mail, Package, Truck, Flame, Tag } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import PreferenceRow from '@/components/notifications/PreferenceRow';
import PushPermissionBanner from '@/components/notifications/PushPermissionBanner';
import { msg } from '@/lib/messages';

// The 6 toggles map 1:1 to the notification_preferences table columns. No
// unbacked toggles (e.g. "Streak reminders") are added — see discrepancy #10.
const TOGGLES = [
  { key: 'push_enabled', label: 'Push notifications', desc: 'Receive alerts on your device', icon: Bell },
  { key: 'email_enabled', label: 'Email notifications', desc: 'Receive updates via email', icon: Mail },
  { key: 'order_updates', label: 'Order updates', desc: 'Status changes, confirmations', icon: Package },
  { key: 'delivery_updates', label: 'Delivery updates', desc: 'Rider assigned, out for delivery', icon: Truck },
  { key: 'hp_updates', label: 'HP updates', desc: 'HP earned, tiers, unlocks', icon: Flame },
  { key: 'promotions', label: 'Promotions', desc: 'Flash redeems, offers, events', icon: Tag },
];

export default function NotificationPreferences() {
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await liveApi.notifications.getPreferences();
      const data = result && result.data ? result.data : result || {};
      // Seed defaults matching the DB defaults so the UI is usable even if the
      // backend omits a field (all default to true per the schema).
      setPrefs({
        push_enabled: data.push_enabled ?? true,
        email_enabled: data.email_enabled ?? true,
        order_updates: data.order_updates ?? true,
        delivery_updates: data.delivery_updates ?? true,
        hp_updates: data.hp_updates ?? true,
        promotions: data.promotions ?? true,
      });
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggle = async (key, next) => {
    const prev = prefs;
    const updated = { ...prefs, [key]: next };
    setPrefs(updated);
    setSavingKey(key);
    try {
      await liveApi.notifications.updatePreferences({ [key]: next });
      toast({ title: msg('FE_NOTIFICATION_PREFERENCES_NOTIFICATION_SETTINGS_UPDATED', 'Notification settings updated.') });
    } catch (e) {
      setPrefs(prev);
      toast({ title: msg('FE_NOTIFICATION_PREFERENCES_FAILED_TO_UPDATE_NOTIFICATION', 'Failed to update notification preferences.'), variant: 'destructive' });
    }
    setSavingKey(null);
  };

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
          aria-label="Back to profile"
        >
          <ArrowLeft className="w-5 h-5 text-foreground" />
        </button>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Preferences</h1>
      </div>

      <PushPermissionBanner />

      <section className="space-y-2.5">
        <h2 className="font-heading font-extrabold text-base text-foreground px-1">What you receive</h2>
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
              disabled={savingKey === t.key}
            />
          );
        })}
      </section>

      <div className="rounded-2xl bg-secondary/60 border border-border p-4">
        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Transactional notifications (order status, delivery updates) always send regardless of your
          preferences. Promotional notifications are throttled, max 3 per day with a 6 hour minimum gap.
        </p>
      </div>
    </div>
  );
}