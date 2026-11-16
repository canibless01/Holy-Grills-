import { useEffect, useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { apiClient } from '@/lib/apiClient';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { msg } from '@/lib/messages';
import { formatDate, formatNaira } from '@/lib/hgUtils';

export default function CateringStatus() {
  const { requestId } = useParams();
  const location = useLocation();
  const { isAuthenticated } = useHolyGrill();
  const [email, setEmail] = useState(location.state?.email || '');
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true); setError(false);
    try { setReceipt(await apiClient.get(`/events/catering-requests/${requestId}`, isAuthenticated ? {} : { email })); }
    catch { setError(true); }
    finally { setBusy(false); }
  };
  useEffect(() => { if (isAuthenticated) load(); }, [requestId, isAuthenticated]);
  return <div className="max-w-xl mx-auto py-6 space-y-4"><h1 className="font-heading font-extrabold text-2xl">{msg('FE_CATERING_TRACK_TITLE', 'Your catering request')}</h1>
    {!isAuthenticated && <label className="block space-y-2"><span>{msg('FE_CATERING_RECEIPT_EMAIL', 'Email used for this request')}</span><input type="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full rounded-xl border border-border p-3" /></label>}
    {error && <p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p>}
    <button onClick={load} disabled={busy || (!isAuthenticated && !email)} className="rounded-xl bg-primary text-white font-bold px-4 py-2 disabled:opacity-50">{error ? msg('FE_PLATFORM_RETRY', 'Retry') : msg('FE_CATERING_LOAD_RECEIPT', 'View request')}</button>
    {receipt && <div className="rounded-2xl bg-card border border-border p-4 space-y-3"><h2 className="font-heading font-bold">{receipt.event_name}</h2><p>{formatDate(receipt.event_date)}</p><p className="capitalize">{receipt.status.replaceAll('_', ' ')}</p><p>{receipt.expected_guests}</p>{receipt.quoted_amount !== null && <p>{formatNaira(receipt.quoted_amount)}</p>}</div>}
  </div>;
}
