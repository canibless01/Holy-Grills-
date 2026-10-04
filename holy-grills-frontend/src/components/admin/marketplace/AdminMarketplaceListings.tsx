import React, { useState } from 'react';
import { Plus, Pencil, Trash2, Settings } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatNaira } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Pill } from '../AdminShared';
import ImageUploader from '../ImageUploader';
import AdminMarketplaceListingManager from './AdminMarketplaceListingManager';

const BLANK = { title: '', listing_type: 'voucher', price: 0, hp_price: 0, vendor_name: '', description: '', image_url: '', status: 'active', is_featured: false, sort_order: 0, is_out_of_stock: false, rejection_reason: '' };
const STATUSES = ['active', 'paused', 'archived', 'rejected', 'pending', 'draft'];
const STATUS_TONE = { active: 'green', paused: 'amber', archived: 'cocoa', rejected: 'red', pending: 'blue', draft: 'cocoa' };

export default function AdminMarketplaceListings({ listings, reload }) {
  const [modal, setModal] = useState(null);
  const [manager, setManager] = useState(null);

  const save = async () => {
    const body = {
      ...modal.item,
      price: Number(modal.item.price) || 0,
      hp_price: Number(modal.item.hp_price) || 0,
      sort_order: Number(modal.item.sort_order) || 0,
    };
    if (body.status !== 'rejected') delete body.rejection_reason;
    try {
      if (modal.isNew) {
        await liveApi.admin.createListing(body);
        toast({ title: 'Listing created' });
      } else {
        await liveApi.admin.updateListing(modal.item.id, body);
        toast({ title: 'Listing updated' });
      }
      setModal(null);
      await reload();
    } catch (e) {
      toast({ title: 'Save failed', description: e.message, variant: 'destructive' });
    }
  };

  const remove = async (id) => {
    if (!confirm('Delete this listing? This cannot be undone.')) return;
    try {
      const res = await liveApi.admin.deleteListing(id);
      toast({ title: 'Listing deleted', description: res?.message });
      await reload();
    } catch (e) {
      toast({ title: 'Delete failed', description: e.message, variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <button onClick={() => setModal({ item: { ...BLANK }, isNew: true })} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold">
          <Plus className="w-4 h-4" /> Add Listing
        </button>
      </div>
      {listings.map((m) => (
        <div key={m.id} className="rounded-2xl bg-white border border-border p-3 flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <div className="font-bold text-sm text-foreground truncate">{m.title}</div>
            <div className="text-xs text-muted-foreground truncate">{m.listing_type} · {formatNaira(m.price)} / {m.hp_price} HP · {m.vendor_name}</div>
          </div>
          <Pill tone={STATUS_TONE[m.status] || 'cocoa'}>{m.status}</Pill>
          <button onClick={() => setManager(m)} title="Manage stock & codes" className="p-2 rounded-lg hover:bg-primary/10"><Settings className="w-4 h-4 text-primary" /></button>
          <button onClick={() => setModal({ item: { ...m }, isNew: false })} className="p-2 rounded-lg hover:bg-muted"><Pencil className="w-4 h-4 text-muted-foreground" /></button>
          <button onClick={() => remove(m.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
        </div>
      ))}
      {listings.length === 0 && <p className="text-xs text-muted-foreground text-center py-6">No listings yet.</p>}

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.isNew ? 'New Listing' : 'Edit Listing'}>
        {modal && (
          <div className="space-y-3">
            <Field label="Title"><TextInput value={modal.item.title} onChange={(e) => setModal({ ...modal, item: { ...modal.item, title: e.target.value } })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Type">
                <select value={modal.item.listing_type} onChange={(e) => setModal({ ...modal, item: { ...modal.item, listing_type: e.target.value } })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                  {['voucher', 'code', 'digital_code', 'manual', 'subscription'].map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="Vendor"><TextInput value={modal.item.vendor_name} onChange={(e) => setModal({ ...modal, item: { ...modal.item, vendor_name: e.target.value } })} /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Price (₦)"><TextInput type="number" value={modal.item.price} onChange={(e) => setModal({ ...modal, item: { ...modal.item, price: e.target.value } })} /></Field>
              <Field label="HP price"><TextInput type="number" value={modal.item.hp_price} onChange={(e) => setModal({ ...modal, item: { ...modal.item, hp_price: e.target.value } })} /></Field>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Status">
                <select value={modal.item.status} onChange={(e) => setModal({ ...modal, item: { ...modal.item, status: e.target.value } })} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm">
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Sort order"><TextInput type="number" value={modal.item.sort_order} onChange={(e) => setModal({ ...modal, item: { ...modal.item, sort_order: e.target.value } })} /></Field>
            </div>
            <Field label="Description"><textarea value={modal.item.description} onChange={(e) => setModal({ ...modal, item: { ...modal.item, description: e.target.value } })} rows={2} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm" /></Field>
            {modal.item.status === 'rejected' && (
              <Field label="Rejection reason (required to reject)"><TextInput value={modal.item.rejection_reason} onChange={(e) => setModal({ ...modal, item: { ...modal.item, rejection_reason: e.target.value } })} /></Field>
            )}
            <label className="flex items-center gap-2 text-xs font-bold text-foreground">
              <input type="checkbox" checked={!!modal.item.is_featured} onChange={(e) => setModal({ ...modal, item: { ...modal.item, is_featured: e.target.checked } })} /> Featured
            </label>
            <label className="flex items-center gap-2 text-xs font-bold text-foreground">
              <input type="checkbox" checked={!!modal.item.is_out_of_stock} onChange={(e) => setModal({ ...modal, item: { ...modal.item, is_out_of_stock: e.target.checked } })} /> Mark out of stock
            </label>
            <Field label="Image"><ImageUploader value={modal.item.image_url} onChange={(url) => setModal({ ...modal, item: { ...modal.item, image_url: url } })} folder="marketplace" /></Field>
            <button onClick={save} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">{modal.isNew ? 'Create Listing' : 'Save Changes'}</button>
          </div>
        )}
      </Modal>

      {manager && <AdminMarketplaceListingManager listing={manager} onClose={() => setManager(null)} reload={reload} />}
    </div>
  );
}