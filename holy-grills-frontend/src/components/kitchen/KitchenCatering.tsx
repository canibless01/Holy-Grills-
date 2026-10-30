import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';
import { formatDate } from '@/lib/hgUtils';

export default function KitchenCatering() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(null);
  const load = async () => {
    setError(false);
    try { setRows(await liveApi.admin.getCateringRequests()); } catch { setError(true); }
  };
  useEffect(() => { load(); }, []);
  const advance = async (row) => {
    setBusy(row.id);
    try { await liveApi.admin.updateCateringRequest(row.id, { status: row.status === 'confirmed' ? 'in_progress' : 'completed' }); await load(); }
    catch { setError(true); }
    finally { setBusy(null); }
  };
  if (error) return <div className="rounded-2xl bg-card border border-border p-4 space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>;
  return <div className="space-y-3">{rows.length === 0 && <p>{msg('FE_CATERING_NO_ASSIGNED', 'No catering requests assigned to you.')}</p>}{rows.map(row => <div key={row.id} className="rounded-2xl bg-card border border-border p-4 space-y-2">
    <h3 className="font-heading font-bold">{row.event_name}</h3><p>{formatDate(row.event_date)} · {row.expected_guests}</p><p className="capitalize">{row.status.replaceAll('_', ' ')}</p><p>{row.notes}</p>
    {['confirmed', 'in_progress'].includes(row.status) && <button disabled={!!busy} onClick={() => advance(row)} className="rounded-xl bg-primary text-white px-4 py-2 font-bold disabled:opacity-50">{row.status === 'confirmed' ? msg('FE_CATERING_START', 'Start preparation') : msg('FE_CATERING_COMPLETE', 'Mark completed')}</button>}
  </div>)}</div>;
}
