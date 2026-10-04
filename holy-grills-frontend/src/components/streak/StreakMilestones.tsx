import { useState } from 'react';
import { Target, Award, Flame, Check, Download, Bell } from 'lucide-react';
import { isStandalone, hasInstallPrompt, triggerInstall } from '@/lib/installPromptStore';
import { toast } from '@/components/ui/use-toast';
import SocialFollowChallenge from '@/components/challenges/SocialFollowChallenge';

// Detect the two browser-action challenges by title / slug / trigger_type.
const challengeText = (ch) => `${ch.title || ch.name || ''} ${ch.slug || ''} ${ch.trigger_type || ''}`.toLowerCase();
const isInstallChallenge = (ch) => {
  const t = challengeText(ch);
  return t.includes('install') || ch.trigger_type === 'install_app';
};
const isPushChallenge = (ch) => {
  const t = challengeText(ch);
  return t.includes('push') || t.includes('notification') || ch.trigger_type === 'enable_push';
};
// Social-follow milestone — has its own dedicated claim endpoint + a social_link
// the student must follow first, so it renders SocialFollowChallenge instead of
// the generic claim button.
const isSocialFollowChallenge = (ch) => ch.trigger_type === 'social_follow' || (challengeText(ch).includes('social') && challengeText(ch).includes('follow'));

export default function StreakMilestones({ badges, availableChallenges, completedChallenges, completing, onComplete, onSocialFollowClaimed }) {
  const [actioning, setActioning] = useState(null);
  if (badges.length === 0 && availableChallenges.length === 0 && completedChallenges.length === 0) return null;

  const allChallenges = [...availableChallenges, ...completedChallenges];
  const completedIds = new Set(completedChallenges.map((c) => c.id));

  // Perform the real browser action (install / push) before claiming the HP.
  const handleAction = async (ch) => {
    setActioning(ch.id);
    try {
      if (isInstallChallenge(ch)) {
        if (isStandalone()) {
          // Already installed — just claim the reward.
          await onComplete(ch);
        } else if (hasInstallPrompt()) {
          const res = await triggerInstall();
          if (res?.outcome === 'accepted') {
            await onComplete(ch);
          } else if (res?.outcome === 'dismissed') {
            toast({ title: 'Install dismissed', description: 'Tap again to retry the install prompt.' });
          } else {
            toast({ title: 'Install unavailable', description: 'Use your browser menu → "Add to Home Screen" to install, then come back.' });
          }
        } else {
          toast({ title: 'Install from your browser', description: 'Open your browser menu and tap "Add to Home Screen" / "Install app", then come back to claim.' });
        }
      } else if (isPushChallenge(ch)) {
        if (!('Notification' in window)) {
          await onComplete(ch);
        } else if (Notification.permission === 'granted') {
          await onComplete(ch);
        } else {
          const perm = await Notification.requestPermission();
          if (perm === 'granted') {
            await onComplete(ch);
          } else {
            toast({ title: 'Notifications blocked', description: 'Enable push in your browser settings, then come back to claim.' });
          }
        }
      } else {
        await onComplete(ch);
      }
    } finally {
      setActioning(null);
    }
  };

  // The button label + icon for a browser-action challenge.
  const actionLabel = (ch) => {
    if (isInstallChallenge(ch)) return { label: 'Install App', icon: Download };
    if (isPushChallenge(ch)) return { label: 'Enable Push', icon: Bell };
    return { label: 'Claim', icon: null };
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Target className="w-4 h-4 text-primary" />
        <h2 className="font-heading font-bold text-base text-foreground">Milestones</h2>
      </div>

      {badges.length > 0 && (
        <div className="rounded-3xl bg-accent/10 border border-accent/20 p-4 shadow-card">
          <div className="flex items-center gap-2 mb-3">
            <Award className="w-4 h-4 text-accent" />
            <span className="text-xs font-bold text-foreground">Badges Earned</span>
            <span className="ml-auto text-[10px] font-bold text-accent-foreground tabular-nums">{badges.length}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {badges.map((b, i) => (
              <span key={i} className="text-xs font-bold px-3 py-1.5 rounded-full bg-card border border-accent/20 text-accent-foreground flex items-center gap-1.5">
                <span className="text-sm">{b.icon_won || '🏅'}</span> {b.title || b.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {allChallenges.map((ch) => {
        const isCompleted = completedIds.has(ch.id);
        const progress = ch.progress || ch.current_progress || 0;
        const target = ch.trigger_value || ch.target || 1;
        const pct = Math.min(100, (progress / target) * 100);
        const isAction = !isCompleted && (isInstallChallenge(ch) || isPushChallenge(ch));
        const isSocial = !isCompleted && isSocialFollowChallenge(ch);
        const al = actionLabel(ch);
        const ActionIcon = al.icon;
        const busy = completing === ch.id || actioning === ch.id;
        return (
          <div key={ch.id} className="rounded-3xl bg-card border border-border p-4 shadow-card">
            <div className="flex items-start justify-between mb-2 gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${isCompleted ? 'bg-emerald-100' : 'bg-primary/10'}`}>
                  {isCompleted ? <Check className="w-4 h-4 text-emerald-600" /> : isAction && ActionIcon ? <ActionIcon className="w-4 h-4 text-primary" /> : <Target className="w-4 h-4 text-primary" />}
                </div>
                <h3 className="font-bold text-sm text-foreground truncate">{ch.title || ch.name}</h3>
              </div>
              <span className="flex items-center gap-1 text-xs font-bold text-primary shrink-0">
                <Flame className="w-3 h-3" />+{ch.hp_awarded || ch.hp_award || 0}
              </span>
            </div>
            {ch.description && <p className="text-xs text-muted-foreground mb-3 leading-relaxed">{ch.description}</p>}
            <div className="flex items-center gap-2.5">
              <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ${isCompleted ? 'bg-emerald-500' : 'bg-gradient-cta'}`} style={{ width: `${pct}%` }} />
              </div>
              <span className="text-xs font-bold text-foreground tabular-nums shrink-0">{progress}/{target}</span>
            </div>
            {!isCompleted && (
              isSocial ? (
                <SocialFollowChallenge challenge={ch} onClaimed={onSocialFollowClaimed} />
              ) : (
                <div className="flex justify-end mt-3">
                  <button
                    onClick={() => (isAction ? handleAction(ch) : onComplete(ch))}
                    disabled={busy}
                    className="px-4 py-1.5 rounded-full bg-primary text-white text-xs font-bold flex items-center gap-1.5 transition-all active:scale-95 disabled:opacity-50"
                  >
                    {busy ? <><div className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" /> {isAction ? 'Working…' : 'Claiming…'}</> : <>{ActionIcon && <ActionIcon className="w-3.5 h-3.5" />}{al.label}</>}
                  </button>
                </div>
              )
            )}
          </div>
        );
      })}
    </div>
  );
}