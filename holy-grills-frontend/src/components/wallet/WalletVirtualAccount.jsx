import React, { useState } from 'react';
import { Building2, Copy, Check } from 'lucide-react';
import { walletTopupMin, walletTopupHp } from '@/lib/appConfig';

export default function WalletVirtualAccount({ account }) {
  const [copied, setCopied] = useState(false);
  if (!account) return null;

  const copy = () => {
    navigator.clipboard?.writeText(account.account_number || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-3xl bg-card border border-border p-5 shadow-card">
      <div className="flex items-center gap-2 mb-3">
        <Building2 className="w-4 h-4 text-muted-foreground" />
        <h3 className="font-bold text-sm text-foreground">Virtual Account</h3>
      </div>
      <div className="flex items-center justify-between p-4 rounded-2xl bg-muted">
        <div className="min-w-0">
          <div className="font-heading font-bold text-xl text-foreground tabular-nums">{account.account_number}</div>
          <div className="text-xs text-muted-foreground mt-0.5 truncate">{account.bank_name} · {account.account_name}</div>
        </div>
        <button onClick={copy} className="p-2.5 rounded-full bg-card border border-border transition-all active:scale-90 shrink-0">
          {copied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4 text-muted-foreground" />}
        </button>
      </div>
      <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
        Transfer to this account to fund your wallet instantly. Top-ups of ₦{walletTopupMin().toLocaleString()}+ earn {walletTopupHp()} HP!
      </p>
    </div>
  );
}