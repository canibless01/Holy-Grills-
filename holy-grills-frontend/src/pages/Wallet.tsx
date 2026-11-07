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
import { msg } from '@/lib/messages';
import { useFeatureFlags, showHpTransferUI } from '@/lib/featureConfig';
import { hpTransferMinOrders } from '@/lib/appConfig';

export default function Wallet() {
  useFeatureFlags();
  const [searchParams, setSearchParams] = useSearchParams();
  const { wallet, refreshWallet, refreshHp, hpBalance } = useHolyGrill();
  const [walletTxns, setWalletTxns] = useState([]);
  const [hpTxns, setHpTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(() => !!searchParams.get('reference'));
  const [historyError, setHistoryError] = useState(false);
  const [historyRetry, setHistoryRetry] = useState(0);
  const [fundingStatus, setFundingStatus] = useState<'pending' | 'error' | 'review' | null>(null);
  const [showFund, setShowFund] = useState(false);
  const [showTransfer, setShowTransfer] = useState(false);
  const [activeTab, setActiveTab] = useState('all');
  // Eligibility and the release gate are independent requirements.
  const [deliveredCount, setDeliveredCount] = useState(null);
  const transferReleased = showHpTransferUI();
  useEffect(() => {
    if (!transferReleased) return;
    let current = true;
    liveApi.orders.list({ status: 'delivered', limit: 100 })
      .then((list) => { if (current) setDeliveredCount(Array.isArray(list) ? list.length : 0); })
      .catch(() => { if (current) setDeliveredCount(null); });
    return () => { current = false; };
  }, [transferReleased]);
  const transferMinimum = hpTransferMinOrders();
  const hpTransferEnabled = transferReleased && deliveredCount != null && deliveredCount >= transferMinimum;

  const checkFunding = async (reference: string, refreshHistory = true) => {
    setVerifying(true);
    try {
      const result = await liveApi.wallet.verifyCardFunding({ reference });
      if (result.payment_status !== 'paid') {
        setFundingStatus('pending');
        return;
      }
      await Promise.all([refreshWallet(), refreshHp()]);
      if (refreshHistory) setHistoryRetry(value => value + 1);
      setFundingStatus(null);
      toast({ title: msg('FE_WALLET_WALLET_FUNDED', 'Wallet funded ❤️‍🔥'), description: msg('FE_WALLET_YOUR_BALANCE_IS_UPDATED', 'Your balance is updated.') });
      const params = new URLSearchParams(searchParams);
      for (const key of ['reference', 'trxref', 'status']) params.delete(key);
      setSearchParams(params, { replace: true });
    } catch (error) {
      setFundingStatus(error?.status === 409 ? 'review' : 'error');
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    let current = true;
    const load = async () => {
      setLoading(true); setHistoryError(false);
      const reference = searchParams.get('reference');
      if (reference && historyRetry === 0) {
        await checkFunding(reference, false);
      }
      try {
        const [wt, ht] = await Promise.allSettled([
          liveApi.wallet.getTransactions({ limit: 30 }),
          liveApi.hp.getTransactions({ limit: 30 }),
        ]);
        if (!current) return;
        setHistoryError(wt.status === 'rejected' || ht.status === 'rejected');
        if (wt.status === 'fulfilled') setWalletTxns(Array.isArray(wt.value) ? wt.value : (wt.value?.transactions || wt.value?.items || []));
        if (ht.status === 'fulfilled') setHpTxns(Array.isArray(ht.value) ? ht.value : (ht.value?.transactions || ht.value?.items || []));
      } catch (e) { console.error(e); }
      if (current) setLoading(false);
    };
    load();
    return () => { current = false; };
  }, [historyRetry]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFundSuccess = async () => {
    await Promise.all([refreshWallet(), refreshHp()]);
    setHistoryRetry(value => value + 1);
    toast({ title: msg('FE_WALLET_WALLET_FUNDED', 'Wallet funded ❤️‍🔥') });
  };

  if (verifying) return <WalletSkeleton />;

  const balance = wallet?.balance ?? wallet?.wallet_balance ?? null;
  const virtualAccount = wallet?.virtual_account;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto">
      <div>
        <span className="hg-eyebrow">Your pocket</span>
        <h1 className="font-heading font-extrabold text-2xl text-foreground">Wallet</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Fund once. Pay faster.</p>
      </div>

      {fundingStatus && (
        <div role="status" className="rounded-2xl border border-border bg-card p-4 space-y-2">
          <p className="text-sm">{fundingStatus === 'pending'
            ? msg('FE_ORDER_PAYMENT_PENDING', 'Payment has not been confirmed. You can continue payment or check again.')
            : fundingStatus === 'review'
              ? msg('FE_WALLET_PAYMENT_REVIEW', 'This payment needs support review. Do not start another payment.')
              : msg('FE_WALLET_PAYMENT_CHECK_FAILED', 'Payment verification is unavailable. Check again before starting another payment.')}</p>
          {fundingStatus !== 'review' && <button className="text-sm font-bold text-primary" onClick={() => checkFunding(searchParams.get('reference') || '')}>
            {msg('FE_ORDER_PAYMENT_CHECK', 'I have paid — check payment')}
          </button>}
        </div>
      )}

      {balance === 0 && (
        <div className="flex justify-center">
          <MascotStandee mascot="thinking" className="w-32 h-32" alt="Your wallet is empty" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <WalletBalanceCard balance={balance} onFund={() => setShowFund(true)} />
        <WalletHpCard hpBalance={hpBalance} onSend={() => setShowTransfer(true)} transferEnabled={hpTransferEnabled} transferVisible={transferReleased} minimumOrders={transferMinimum} deliveredCount={deliveredCount} />
      </div>

      <WalletVirtualAccount account={virtualAccount} />

      {historyError && <p role="alert" className="text-sm text-destructive">
        {msg('FE_WALLET_HISTORY_UNAVAILABLE', 'Some transaction history could not be loaded.')}{' '}
        <button onClick={() => setHistoryRetry(value => value + 1)} className="underline">{msg('FE_LOOKUP_RETRY', 'Retry')}</button>
      </p>}
      <WalletTransactionList
        walletTxns={walletTxns}
        hpTxns={hpTxns}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        loading={loading}
      />

      <WalletFundModal
        open={showFund}
        onClose={() => setShowFund(false)}
        wallet={wallet}
        onSuccess={handleFundSuccess}
      />

      <HpTransferModal open={showTransfer && transferReleased} onClose={() => setShowTransfer(false)} />
    </div>
  );
}
