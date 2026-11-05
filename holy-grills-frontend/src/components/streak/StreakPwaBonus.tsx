import { Smartphone, Bell, Gift, Check, Loader2 } from 'lucide-react';
import { getSetting } from '@/lib/featureConfig';

export default function StreakPwaBonus({ pwaStatus, onAction, busy, error, installed, installAvailable, pushSupported }) {
  const installHp = getSetting('pwa_install_hp', 50);
  const pushHp = getSetting('push_subscribe_hp', 25);
  const bonusHp = getSetting('pwa_push_bonus_hp', 75);
  const cells = [
    { icon: Smartphone, label: 'App Install', done: pwaStatus?.pwa_install, hp: installHp },
    { icon: Bell, label: 'Push Alerts', done: pwaStatus?.push_subscribe, hp: pushHp },
    { icon: Gift, label: 'Bonus', done: pwaStatus?.bonus_completed, hp: bonusHp },
  ];
  const nextStep = !pwaStatus?.pwa_install ? 0 : !pwaStatus?.push_subscribe ? 1 : 2;
  const completed = !!pwaStatus?.bonus_completed;
  const label = !pwaStatus ? 'Retry loading bonuses' : nextStep === 0 ? installed ? 'App installed — record install' : installAvailable ? 'Install app' : 'How to install' : nextStep === 1 ? pushSupported ? 'Enable push alerts' : 'Check push availability' : pwaStatus.bonus_configured === false ? 'Retry bonus availability' : 'Claim bonus';
  return (
    <div className="rounded-3xl bg-card border border-border p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <Smartphone className="w-4 h-4 text-primary" />
        <h3 className="font-heading font-bold text-sm text-foreground">Install & Push Bonuses</h3>
        <span className="ml-auto text-[10px] font-bold text-primary tabular-nums">{installHp + pushHp + bonusHp} HP total</span>
      </div>
      <div className="grid grid-cols-3 gap-2.5">
        {cells.map((cell, index) => (
          <button key={cell.label} onClick={onAction} disabled={busy || completed || index !== nextStep || !pwaStatus}
            className={`rounded-2xl p-3 text-center border transition-all ${cell.done ? 'tone-success border-success/30' : index === nextStep ? 'bg-primary/5 border-primary/20' : 'bg-muted border-border'}`}>
            <div className="w-9 h-9 rounded-xl mx-auto mb-2 flex items-center justify-center bg-secondary">
              {cell.done ? <Check className="w-4 h-4 text-success" /> : <cell.icon className="w-4 h-4 text-primary" />}
            </div>
            <div className="text-[10px] font-bold text-foreground">{index + 1}. {cell.label}</div>
            <div className="text-[10px] mt-1 text-muted-foreground">{cell.done ? 'Completed' : `+${cell.hp} HP`}</div>
          </button>
        ))}
      </div>
      {!completed && <button onClick={onAction} disabled={busy} className="w-full mt-3 py-2.5 rounded-2xl bg-primary/5 border border-primary/20 text-primary text-xs font-bold flex items-center justify-center gap-1.5 disabled:opacity-60">
        {busy ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Working…</> : label}
      </button>}
      {error && <p role="alert" className="text-xs text-destructive mt-3">{error}</p>}
      {!error && !pwaStatus && <p role="status" className="text-xs text-muted-foreground mt-3">Loading bonus status…</p>}
      {completed && <p role="status" className="text-xs text-success mt-3 text-center">All bonuses claimed.</p>}
    </div>
  );
}
