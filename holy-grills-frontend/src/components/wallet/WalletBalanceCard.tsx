import React from 'react';
import { ArrowDownLeft } from 'lucide-react';
import CountUp from '@/components/CountUp';
import { formatNaira } from '@/lib/hgUtils';

export default function WalletBalanceCard({ balance, onFund }) {
  return (
    <div className="relative overflow-hidden rounded-3xl bg-success p-6 text-white shadow-card">
      <div className="absolute -right-4 -top-6 text-[6rem] opacity-15 select-none leading-none">💰</div>
      <div className="relative">
        <div className="text-[10px] font-bold uppercase tracking-widest text-white/70">Wallet Balance</div>
        <div className="font-heading text-4xl font-extrabold mt-1 tabular-nums leading-none"><CountUp value={balance || 0} format={(v) => formatNaira(v)} /></div>
        <button
          onClick={onFund}
          className="w-full mt-4 flex items-center justify-center gap-1.5 py-3 rounded-2xl bg-white/15 backdrop-blur-sm text-white font-bold text-sm border border-white/20 transition-all active:scale-[0.98] hover:bg-white/20"
        >
          <ArrowDownLeft className="w-4 h-4" /> Fund Wallet
        </button>
      </div>
    </div>
  );
}