import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import WalletSkeleton from '@/components/skeletons/WalletSkeleton';
import HpTransferModal from '@/components/HpTransferModal';
import WalletBalanceCard from '@/components/wallet/WalletBalanceCard';
import WalletHpCard from '@/components/wallet/WalletHpCard';
import WalletVirtualAccount from '@/components/wallet/WalletVirtualAccount';
import WalletTransactionList from '@/components/wallet/WalletTransactionList';
import WalletFundModal from '@/components/wallet/WalletFundModal';
import MascotStandee from '@/components/mascot/MascotStandee';

export default function Wallet() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { wallet, refreshWallet, refreshHp, hpBalance } = useHolyGrill();
  const [walletTxns, setWalletTxns] = useState([]);
  const [hpTxns, setHpTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [showFund, setShowFund] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [activeTab, setActiveTab] = useState('all');
  // HP transfer trust gate — the ONLY gate is a minimum of 3 delivered orders
  // (the backend enforces the same rule and returns a specific 400 if not met).
  // No feature flag: once a student has 3 delivered orders, transfer is active.
  const [deliveredCount, setDeliveredCount] = useState(null);
  useEffect(() => {
    liveApi.orders.list({ status: 'delivered', limit: 100 })
      .then((list) => setDeliveredCount(Array.isArray(list) ? list.length : 0))
      .catch(() => setDeliveredCount(0));
  }, []);
  const hpTransferEnabled = deliveredCount != null && deliveredCount >= 3;

  useEffect(() => {
    const load = async () => {
      const reference = searchParams.get('reference');
      if (reference) {
        setVerifying(true);
        try {
          await refreshWallet();
          await refreshHp();
          toast({ title: 'Wallet funded ❤️‍🔥', description: 'Your balance is updated.' });
        } catch { /* ignore */ }
        setVerifying(false);
        searchParams.delete('reference');
        searchParams.delete('trxref');
        searchParams.delete('status');
        setSearchParams(searchParams, { replace: true });
      }
      try {
        const [wt, ht] = await Promise.allSettled([
          liveApi.wallet.getTransactions({ limit: 30 }),
          liveApi.hp.getTransactions({ limit: 30 }),
        ]);
        if (wt.status === 'fulfilled') setWalletTxns(Array.isArray(wt.value) ? wt.value : (wt.value?.transactions || wt.value?.items || []));
        if (ht.status === 'fulfilled') setHpTxns(Array.isArray(ht.value) ? ht.value : (ht.value?.transactions || ht.value?.items || []));
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFundSuccess = async () => {
    await refreshWallet();
    await refreshHp();
    const [wt, ht] = await Promise.allSettled([
      liveApi.wallet.getTransactions({ limit: 30 }),
      liveApi.hp.getTransactions({ limit: 30 }),
    ]);
    if (wt.status === 'fulfilled') setWalletTxns(Array.isArray(wt.value) ? wt.value : (wt.value?.transactions || wt.value?.items || []));
    if (ht.status === 'fulfilled') setHpTxns(Array.isArray(ht.value) ? ht.value : (ht.value?.transactions || ht.value?.items || []));
    toast({ title: 'Wallet funded ❤️‍🔥' });
  };

  if (loading || verifying) return <WalletSkeleton />;

  const balance = wallet?.balance ?? wallet?.wallet_balance ?? 0;
  const virtualAccount = wallet?.virtual_account;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto">
      <div>
        <span className="hg-eyebrow">Your pocket</span>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Wallet</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Fund once. Pay faster.</p>
      </div>

      {balance === 0 && (
        <div className="flex justify-center">
          <MascotStandee mascot="thinking" className="w-32 h-32" alt="Your wallet is empty" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <WalletBalanceCard balance={balance} onFund={() => setShowFund(true)} />
        <WalletHpCard hpBalance={hpBalance} onSend={() => setShowTransfer(true)} transferEnabled={hpTransferEnabled} deliveredCount={deliveredCount} />
      </div>

      <WalletVirtualAccount account={virtualAccount} />

      <WalletTransactionList
        walletTxns={walletTxns}
        hpTxns={hpTxns}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        loading={false}
      />

      <WalletFundModal
        open={showFund}
        onClose={() => setShowFund(false)}
        wallet={wallet}
        onSuccess={handleFundSuccess}
      />

      <HpTransferModal open={showTransfer} onClose={() => setShowTransfer(false)} />
    </div>
  );
}