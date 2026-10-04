import { Send, Lock } from 'lucide-react';
import CountUp from '@/components/CountUp';

export default function WalletHpCard({ hpBalance, onSend, transferEnabled, deliveredCount }) {
  const active = hpBalance?.active || 0;
  const pending = hpBalance?.pending || 0;

  return (
    <div className="relative overflow-hidden rounded-3xl bg-gradient-dark p-6 text-white shadow-card">
      <div className="absolute -right-4 -top-6 text-[6rem] opacity-10 select-none leading-none">🔥</div>
      <div className="relative">
        <div className="text-[10px] font-bold uppercase tracking-widest text-white/60">Holy Points</div>
        <div className="font-heading text-4xl font-extrabold mt-1 tabular-nums leading-none">
          <CountUp value={active} /> <span className="text-base font-medium text-white/60">HP</span>
        </div>
        {pending > 0 && (
          <div className="text-[11px] text-white/50 mt-1">{pending} HP pending</div>
        )}
        <button
          onClick={onSend}
          disabled={!transferEnabled}
          className={`w-full mt-4 flex items-center justify-center gap-1.5 py-3 rounded-2xl font-bold text-sm transition-all active:scale-[0.98] ${
            transferEnabled
              ? 'bg-gradient-cta text-white shadow-glow hover:opacity-90'
              : 'bg-white/10 text-white/40 cursor-not-allowed'
          }`}
        >
          {transferEnabled ? <><Send className="w-4 h-4" /> Send HP</> : <><Lock className="w-3.5 h-3.5" /> HP Transfer Locked</>}
        </button>
        {!transferEnabled && (
          <div className="text-[10px] font-semibold text-white/50 mt-2 text-center">
            {deliveredCount != null ? `${Math.min(deliveredCount, 3)}/3 delivered orders to unlock` : 'Unlocks after 3 delivered orders'}
          </div>
        )}
      </div>
    </div>
  );
}