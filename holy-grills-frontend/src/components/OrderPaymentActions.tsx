import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { CreditCard } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { msg, useMessages } from '@/lib/messages';
import { formatNaira } from '@/lib/hgUtils';
import { isAllowedPaymentUrl } from '@/lib/safeNavigation';

export default function OrderPaymentActions({ order, claimToken, onUpdated, autoStart = false }) {
  useMessages();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const busyRef = useRef(false);
  const started = useRef('');
  const pending = order?.payment_status === 'pending' && !['cancelled', 'refunded'].includes(order?.status) && Number(order?.card_amount_used) > 0;
  const run = async (verify = false) => {
    if (busyRef.current || !pending) return;
    busyRef.current = true; setBusy(true); setError('');
    try {
      const body = claimToken ? { claim_token: claimToken } : {};
      const result = verify ? await mockApi.orders.verifyPayment(order.id, body) : await mockApi.orders.initializePayment(order.id, body);
      if (result.payment_status === 'paid') { await onUpdated(); return; }
      if (verify) { setError(result.message || msg('FE_ORDER_PAYMENT_PENDING', 'Payment has not been confirmed. You can continue payment or check again.')); return; }
      if (!isAllowedPaymentUrl(result.authorization_url)) throw new Error(msg('FE_ORDER_PAYMENT_INVALID_LINK', 'The payment link could not be verified. Please retry.'));
      window.location.assign(result.authorization_url);
    } catch (e) { setError(e.message || msg('FE_ORDER_PAYMENT_UNAVAILABLE', 'Payment is unavailable. Your order is saved; please retry here.')); }
    finally { busyRef.current = false; setBusy(false); }
  };
  useEffect(() => {
    if (!pending || started.current === order.id) return;
    started.current = order.id;
    const returning = new URLSearchParams(location.search).has('payment_return');
    if (returning) void run(true);
    else if (autoStart) void run();
  }, [order?.id, pending, autoStart, location.search]);
  if (!pending) return null;
  return <section aria-label={msg('FE_ORDER_PAYMENT_SECTION', 'Order payment')} className="rounded-2xl border border-primary/30 bg-card p-4 space-y-3 text-left">
    <h2 className="font-bold flex items-center gap-2"><CreditCard className="w-4 h-4" />{msg('FE_ORDER_PAYMENT_REQUIRED', 'Payment required')}</h2>
    <p className="text-sm text-muted-foreground">{msg('FE_ORDER_PAYMENT_REQUIRED_BODY', 'Your order is saved. The kitchen can start preparing it after payment is confirmed.')}</p>
    {Number(order.wallet_amount_used) > 0 && <p className="text-sm">{msg('FE_ORDER_PAYMENT_WALLET_RESERVED', 'Wallet contribution already deducted: {amount}', { amount: formatNaira(order.wallet_amount_used) })}</p>}
    <p className="text-sm font-semibold">{msg('FE_ORDER_PAYMENT_CARD_DUE', 'Card amount due: {amount}', { amount: formatNaira(order.card_amount_used) })}</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    <button disabled={busy} onClick={() => run()} className="w-full py-3 rounded-xl bg-gradient-cta text-white font-bold disabled:opacity-50">{busy ? msg('FE_ORDER_PAYMENT_BUSY', 'Checking payment…') : msg('FE_ORDER_PAYMENT_PAY', 'Pay {amount}', { amount: formatNaira(order.card_amount_used) })}</button>
    <button disabled={busy} onClick={() => run(true)} className="w-full py-2 text-sm font-semibold underline disabled:opacity-50">{msg('FE_ORDER_PAYMENT_CHECK', 'I have paid — check payment')}</button>
  </section>;
}
