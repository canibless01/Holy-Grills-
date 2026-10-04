import React from 'react';
import { Smartphone, Bell, Gift, Check, Loader2 } from 'lucide-react';
import { getSetting } from '@/lib/featureConfig';

// Convert base64url VAPID key to Uint8Array for PushManager.subscribe
const urlBase64ToUint8Array = (base64) => {
  const padding = '='.repeat((4 - base64.length % 4) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
};

export default function StreakPwaBonus({ pwaStatus, onEnablePush, pushLoading }) {
  if (!pwaStatus) return null;

  const installHp = getSetting('pwa_install_hp', 50);
  const pushHp = getSetting('push_subscribe_hp', 25);
  const bonusHp = getSetting('pwa_push_bonus_hp', 75);

  const cells = [
    { icon: Smartphone, label: 'App Install', done: pwaStatus.pwa_install, hp: installHp },
    { icon: Bell, label: 'Push Alerts', done: pwaStatus.push_subscribe, hp: pushHp, action: !pwaStatus.push_subscribe },
    { icon: Gift, label: 'Bonus', done: pwaStatus.bonus_completed, hp: bonusHp, eligible: pwaStatus.eligible && !pwaStatus.bonus_completed },
  ];

  return (
    <div className="rounded-3xl bg-card border border-border p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <Smartphone className="w-4 h-4 text-primary" />
        <h3 className="font-heading font-bold text-sm text-foreground">Install & Push Bonuses</h3>
        <span className="ml-auto text-[10px] font-bold text-primary tabular-nums">{installHp + pushHp + bonusHp} HP total</span>
      </div>
      <div className="grid grid-cols-3 gap-2.5">
        {cells.map((c, i) => (
          <div key={i} className={`rounded-2xl p-3.5 text-center border transition-all ${
            c.done ? 'bg-emerald-50 border-emerald-200' :
            c.eligible ? 'bg-primary/5 border-primary/20' : 'bg-muted border-border'
          }`}>
            <div className={`w-9 h-9 rounded-xl mx-auto mb-2 flex items-center justify-center ${
              c.done ? 'bg-emerald-100' : c.eligible ? 'bg-primary/10' : 'bg-secondary'
            }`}>
              {c.done ? <Check className="w-4 h-4 text-emerald-600" /> : <c.icon className={`w-4 h-4 ${c.eligible ? 'text-primary' : 'text-muted-foreground'}`} />}
            </div>
            <div className="text-[10px] font-bold text-foreground">{c.label}</div>
            <div className="text-[9px] mt-0.5">
              {c.done ? <span className="text-emerald-600 font-semibold">+{c.hp} HP</span> :
               c.eligible ? <span className="text-primary font-semibold animate-pulse">Ready!</span> :
               <span className="text-muted-foreground">+{c.hp} HP</span>}
            </div>
          </div>
        ))}
      </div>

      {!pwaStatus.push_subscribe && (
        <button
          onClick={onEnablePush}
          disabled={pushLoading}
          className="w-full mt-3 py-2.5 rounded-2xl bg-primary/5 border border-primary/20 text-primary text-xs font-bold flex items-center justify-center gap-1.5 transition-all active:scale-[0.98] disabled:opacity-60"
        >
          {pushLoading ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Enabling…</> : <><Bell className="w-3.5 h-3.5" /> Enable Push Notifications (+{pushHp} HP)</>}
        </button>
      )}

      {!pwaStatus.pwa_install && (
        <p className="text-[10px] text-muted-foreground mt-2.5 text-center leading-relaxed">
          Install the app to your home screen to unlock the {installHp} HP install bonus.
        </p>
      )}
    </div>
  );
}