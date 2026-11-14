import { ArrowDownLeft, ArrowUpRight } from 'lucide-react';
import CountUp from '@/components/CountUp';
import { msg } from '@/lib/messages';
import { formatWalletMoney as formatNaira } from '@/lib/hgUtils';

export default function WalletBalanceCard({ balance, onFund, onSend = null }) {
  return (
    <div className="relative overflow-hidden rounded-3xl bg-success p-6 text-white shadow-card">
      <div className="absolute -right-4 -top-6 text-[6rem] opacity-15 select-none leading-none">💰</div>
      <div className="relative">
        <div className="text-[10px] font-bold uppercase tracking-widest text-white/70">Wallet Balance</div>
        <div className="font-heading text-4xl font-extrabold mt-1 tabular-nums leading-none">{balance == null ? <span role="status" aria-label={msg('FE_WALLET_BALANCE_LOADING', 'Loading wallet balance')} className="inline-block w-32 h-9 rounded bg-white/20 animate-pulse" /> : <CountUp value={balance} format={(v) => formatNaira(v)} />}</div>
        <div className={`mt-4 grid gap-2 ${onSend ? 'grid-cols-2' : 'grid-cols-1'}`}><button
          onClick={onFund}
          className="w-full flex items-center justify-center gap-1.5 py-3 rounded-2xl bg-white/15 backdrop-blur-sm text-white font-bold text-sm border border-white/20 transition-all active:scale-[0.98] hover:bg-white/20"
        >
          <ArrowDownLeft className="w-4 h-4" /> Fund Wallet
        </button>
        {onSend && <button onClick={onSend} className="flex items-center justify-center gap-1.5 rounded-2xl border border-white/20 bg-white/15 py-3 text-sm font-bold text-white hover:bg-white/20"><ArrowUpRight className="h-4 w-4" />Send money</button>}</div>
      </div>
    </div>
  );
}