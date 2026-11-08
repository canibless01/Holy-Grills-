import { lazy, Suspense, useState, useEffect } from 'react';
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
import { ChevronDown, Repeat2 } from 'lucide-react';

const AutoFundingPanel = lazy(() => import('@/components/wallet/AutoFundingPanel'));

export default function Wallet() {
  useFeatureFlags();
  const [searchParams, setSearchParams] = useSearchParams();
  const { wallet, refreshWallet, refreshHp, hpBalance } = useHolyGrill();
  const [walletTxns, setWalletTxns] = useState([]);
  const [hpTxns, setHpTxns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(() => !!searchParams.get('reference') && !searchParams.has('auto_funding'));
  const [showAutoFunding, setShowAutoFunding] = useState(() => searchParams.has('auto_funding'));
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
      if (reference && !searchParams.has('auto_funding') && historyRetry === 0) {
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

      <section id="automatic-funding" className="overflow-hidden rounded-3xl border border-border bg-card p-4 sm:p-5 space-y-5">
        <div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Repeat2 className="h-5 w-5" aria-hidden="true" /></div><div className="min-w-0"><h2 className="font-heading font-bold">Automatic funding</h2><p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">Small top-ups. Ready whenever you are.</p></div></div>
          <button type="button" aria-label={showAutoFunding ? 'Hide details' : 'Set up or manage'} className="flex h-10 shrink-0 items-center gap-2 rounded-xl bg-background px-3 text-xs font-bold text-primary" aria-expanded={showAutoFunding} aria-controls="automatic-funding-panel" onClick={() => setShowAutoFunding(value => !value)}><span className="hidden sm:inline">{showAutoFunding ? 'Hide' : 'Set up'}</span><ChevronDown className={`h-4 w-4 transition-transform ${showAutoFunding ? 'rotate-180' : ''}`} aria-hidden="true" /></button></div>
        {showAutoFunding && <div id="automatic-funding-panel"><Suspense fallback={<p role="status" className="text-sm">Loading automatic funding…</p>}><AutoFundingPanel reference={searchParams.has('auto_funding') ? (searchParams.get('reference') || searchParams.get('trxref')) : null} planId={searchParams.get('auto_funding')} onPaid={async () => {
          await Promise.all([refreshWallet(), refreshHp()]);
          setHistoryRetry(value => value + 1);
          // The provider reference is verified and committed. Keep the expanded
          // plan, but do not reprocess a one-time callback on later renders.
          const params = new URLSearchParams(searchParams);
          for (const key of ['reference', 'trxref', 'status']) params.delete(key);
          setSearchParams(params, { replace: true });
        }} /></Suspense></div>}
      </section>

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
        onAutoFunding={() => { setShowFund(false); setShowAutoFunding(true); setTimeout(() => document.getElementById('automatic-funding')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0); }}
      />

      <HpTransferModal open={showTransfer && transferReleased} onClose={() => setShowTransfer(false)} />
    </div>
  );
}
