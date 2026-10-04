import { useState, useEffect } from 'react';
import { Upload, Loader2, Package, MapPin } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { useCampus } from '@/lib/campusContext';
import type { ListingAvailabilityPayload } from '@/types/marketplace';
import { Modal, Field, TextInput } from '../AdminShared';
import { msg } from '@/lib/messages';

// Per-listing management: live code inventory counts (from the admin detail
// endpoint), per-campus availability override (inventory/price/stock flag) and
// bulk code upload. The availability PATCH resolves campus_id server-side from
// the admin's JWT/X-Campus-ID when omitted — we pass the admin campus selector
// value explicitly so a super-admin editing a specific campus targets it.
export default function AdminMarketplaceListingManager({ listing, onClose, reload }) {
  const { adminCampus, adminCampusId } = useCampus();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [avail, setAvail] = useState({ inventory_count: '', low_inventory_threshold: '', price_override: '', is_out_of_stock: false });
  const [savingAvail, setSavingAvail] = useState(false);
  const [codesText, setCodesText] = useState('');
  const [uploading, setUploading] = useState(false);

  const loadDetail = async () => {
    setLoading(true);
    try {
      const d = await liveApi.admin.getMarketplaceListing(listing.id);
      setDetail(d);
    } catch (e) {
      toast({ title: msg('FE_ADMIN_MARKETPLACE_LISTING_MANAGER_COULD_NOT_LOAD_LISTING_DETAIL', 'Could not load listing detail'), description: e.message, variant: 'destructive' });
    }
    setLoading(false);
  };
  useEffect(() => { loadDetail(); }, [listing.id]);

  const saveAvailability = async () => {
    setSavingAvail(true);
    const body: ListingAvailabilityPayload = {};
    if (avail.inventory_count !== '') body.inventory_count = Number(avail.inventory_count);
    if (avail.low_inventory_threshold !== '') body.low_inventory_threshold = Number(avail.low_inventory_threshold);
    if (avail.price_override !== '') body.price_override = Number(avail.price_override);
    body.is_out_of_stock = !!avail.is_out_of_stock;
    if (adminCampusId) body.campus_id = adminCampusId;
    try {
      await liveApi.admin.updateListingAvailability(listing.id, body);
      toast({ title: msg('FE_ADMIN_MARKETPLACE_LISTING_MANAGER_AVAILABILITY_UPDATED', 'Availability updated') });
      await reload();
      await loadDetail();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_MARKETPLACE_LISTING_MANAGER_UPDATE_FAILED', 'Update failed'), description: e.message, variant: 'destructive' });
    }
    setSavingAvail(false);
  };

  const uploadCodes = async () => {
    setUploading(true);
    const codes = codesText.split('\n').map((s) => s.trim()).filter(Boolean);
    try {
      const res = await liveApi.admin.uploadListingCodes(listing.id, { codes });
      toast({ title: msg('FE_ADMIN_MARKETPLACE_LISTING_MANAGER_CODES_UPLOADED', 'Codes uploaded'), description: `Uploaded ${res?.uploaded || 0}${res?.skipped_duplicates?.length ? ` · skipped ${res.skipped_duplicates.length} duplicates` : ''}` });
      setCodesText('');
      await reload();
      await loadDetail();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_MARKETPLACE_LISTING_MANAGER_UPLOAD_FAILED', 'Upload failed'), description: e.message, variant: 'destructive' });
    }
    setUploading(false);
  };

  const campusName = adminCampus?.name || (adminCampusId ? 'Selected campus' : 'Your campus');

  return (
    <Modal open onClose={onClose} title={`Manage — ${listing.title}`}>
      <div className="space-y-4">
        {loading ? (
          <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
        ) : detail ? (
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-secondary p-2.5">
              <div className="font-bold text-base text-foreground">{detail.codes_total ?? '—'}</div>
              <div className="text-[10px] text-muted-foreground">Codes total</div>
            </div>
            <div className="rounded-xl bg-secondary p-2.5">
              <div className="font-bold text-base text-foreground">{detail.codes_remaining ?? '—'}</div>
              <div className="text-[10px] text-muted-foreground">Remaining</div>
            </div>
            <div className="rounded-xl bg-secondary p-2.5">
              <div className="font-bold text-base text-foreground">{detail.purchase_count ?? '—'}</div>
              <div className="text-[10px] text-muted-foreground">Purchases</div>
            </div>
          </div>
        ) : null}

        <div className="rounded-2xl border border-border p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-foreground"><MapPin className="w-3.5 h-3.5 text-primary" /> Availability — {campusName}</div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Inventory count"><TextInput type="number" placeholder="optional" value={avail.inventory_count} onChange={(e) => setAvail({ ...avail, inventory_count: e.target.value })} /></Field>
            <Field label="Low-stock threshold"><TextInput type="number" placeholder="optional" value={avail.low_inventory_threshold} onChange={(e) => setAvail({ ...avail, low_inventory_threshold: e.target.value })} /></Field>
          </div>
          <Field label="Price override (₦)" hint="Leave blank to use the listing's base price."><TextInput type="number" placeholder="optional" value={avail.price_override} onChange={(e) => setAvail({ ...avail, price_override: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-xs font-bold text-foreground">
            <input type="checkbox" checked={avail.is_out_of_stock} onChange={(e) => setAvail({ ...avail, is_out_of_stock: e.target.checked })} /> Force out of stock for this campus
          </label>
          <button onClick={saveAvailability} disabled={savingAvail} className="w-full py-2.5 rounded-full bg-primary text-white text-xs font-bold flex items-center justify-center gap-2 disabled:opacity-50">
            {savingAvail ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Saving…</> : 'Save Availability'}
          </button>
        </div>

        <div className="rounded-2xl border border-border p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-foreground"><Package className="w-3.5 h-3.5 text-primary" /> Upload Access Codes</div>
          <p className="text-[11px] text-muted-foreground">One code per line. Duplicates are skipped.</p>
          <textarea value={codesText} onChange={(e) => setCodesText(e.target.value)} rows={5} placeholder={'CODE-ABCD-1234\nCODE-EFGH-5678'} className="w-full p-2.5 rounded-xl border border-border text-xs font-mono" />
          <button onClick={uploadCodes} disabled={uploading || !codesText.trim()} className="w-full py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold flex items-center justify-center gap-2 disabled:opacity-50">
            {uploading ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Uploading…</> : <><Upload className="w-3.5 h-3.5" /> Upload Codes</>}
          </button>
        </div>
      </div>
    </Modal>
  );
}