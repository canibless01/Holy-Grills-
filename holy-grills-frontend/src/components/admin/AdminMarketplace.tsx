import { useState, useEffect, useCallback } from 'react';
import { msg } from '@/lib/messages';
import { liveApi } from '@/lib/liveApi';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import AdminMarketplaceListings from './marketplace/AdminMarketplaceListings';
import AdminMarketplaceRequests from './marketplace/AdminMarketplaceRequests';
import AdminMarketplacePurchases from './marketplace/AdminMarketplacePurchases';
import AdminMarketplaceReports from './marketplace/AdminMarketplaceReports';

const TABS = [
  { id: 'listings', label: 'Listings' },
  { id: 'requests', label: 'Vendor Requests' },
  { id: 'purchases', label: 'Purchases' },
  { id: 'reports', label: 'Reports' },
];

export default function AdminMarketplace() {
  const [tab, setTab] = useState('listings');
  const [listings, setListings] = useState([]);
  const [requests, setRequests] = useState([]);
  const [purchases, setPurchases] = useState([]);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    const [l, r, p, rep] = await Promise.allSettled([
      liveApi.admin.getMarketplaceListings(),
      liveApi.admin.getListingRequests(),
      liveApi.admin.getMarketplacePurchases(),
      liveApi.admin.getMarketplaceReports({ status: 'open' }),
    ]);
    setListings(l.status === 'fulfilled' ? l.value : []);
    setRequests(r.status === 'fulfilled' ? r.value : []);
    setPurchases(p.status === 'fulfilled' ? p.value : []);
    setReports(rep.status === 'fulfilled' ? rep.value : []);
    setLoadError([l, r, p, rep].some((result) => result.status === 'rejected'));
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <StaffPanelSkeleton />;
  if (loadError) return <div role="alert" className="rounded-2xl bg-card border border-border p-4 text-sm">
    {msg('REFERENCE_DATA_UNAVAILABLE', 'This list is temporarily unavailable. Please try again.')}
    <button type="button" onClick={load} className="ml-2 underline text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button>
  </div>;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-full bg-secondary overflow-x-auto scrollbar-hide">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`flex-1 min-w-[80px] py-2 rounded-full text-xs font-bold whitespace-nowrap ${tab === t.id ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground'}`}>{t.label}</button>
        ))}
      </div>

      {tab === 'listings' && <AdminMarketplaceListings listings={listings} reload={load} />}
      {tab === 'requests' && <AdminMarketplaceRequests requests={requests} reload={load} />}
      {tab === 'purchases' && <AdminMarketplacePurchases purchases={purchases} reload={load} />}
      {tab === 'reports' && <AdminMarketplaceReports reports={reports} reload={load} />}
    </div>
  );
}