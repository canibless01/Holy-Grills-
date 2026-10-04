import { useState, useEffect } from 'react';
import { Plus } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { Modal, Field, TextInput, Toggle, Pill } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

// Full CRUD for menu categories (POST/PATCH/DELETE /menu/categories). The list
// reuses the public GET /menu/categories so admins see exactly what students see.
// "Delete" is a soft-deactivate (backend sets is_active=false); reactivating an
// inactive category flips it back on.
export default function AdminCategories({ open, onClose, onChanged }) {
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ name: '', slug: '', description: '', sort_order: 0, is_active: true });
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const c = await liveApi.menu.getCategories();
      setCats(Array.isArray(c) ? c : (c?.categories || []));
    } catch { setCats([]); }
    setLoading(false);
  };
  useEffect(() => { if (open) load(); }, [open]);

  const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '');

  const create = async () => {
    if (!form.name.trim()) { toast({ title: msg('FE_ADMIN_CATEGORIES_NAME_IS_REQUIRED', 'Name is required'), variant: 'destructive' }); return; }
    setSaving(true);
    try {
      await liveApi.admin.createCategory({
        name: form.name.trim(),
        slug: slugify(form.slug || form.name),
        description: form.description,
        sort_order: Number(form.sort_order) || 0,
        is_active: form.is_active !== false,
      });
      toast({ title: msg('FE_ADMIN_CATEGORIES_CATEGORY_CREATED', '✅ Category created') });
      setForm({ name: '', slug: '', description: '', sort_order: 0, is_active: true });
      await load(); onChanged?.();
    } catch (e) { toast({ title: msg('FE_ADMIN_CATEGORIES_FAILED_TO_CREATE_CATEGORY', 'Failed to create category'), description: e.message, variant: 'destructive' }); }
    setSaving(false);
  };

  const toggleActive = async (cat) => {
    try {
      if (cat.is_active) { await liveApi.admin.deleteCategory(cat.id); toast({ title: msg('FE_ADMIN_CATEGORIES_CATEGORY_DEACTIVATED', 'Category deactivated') }); }
      else { await liveApi.admin.updateCategory(cat.id, { is_active: true }); toast({ title: msg('FE_ADMIN_CATEGORIES_CATEGORY_REACTIVATED', 'Category reactivated') }); }
      await load(); onChanged?.();
    } catch (e) { toast({ title: msg('FE_ADMIN_CATEGORIES_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Menu Categories">
      <div className="space-y-3">
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {loading && <p className="text-xs text-muted-foreground">Loading…</p>}
          {!loading && cats.length === 0 && <p className="text-xs text-muted-foreground text-center py-3">No categories yet.</p>}
          {cats.map((c) => (
            <div key={c.id} className="rounded-xl bg-white border border-border p-2.5 flex items-center gap-2">
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm text-foreground truncate">{c.name}</div>
                <div className="text-[11px] text-muted-foreground truncate">{c.slug} · order {c.sort_order ?? 0}</div>
              </div>
              <Pill tone={c.is_active ? 'green' : 'cocoa'}>{c.is_active ? 'Active' : 'Hidden'}</Pill>
              <button onClick={() => toggleActive(c)} className={`px-2.5 py-1.5 rounded-full text-xs font-bold shrink-0 ${c.is_active ? 'bg-red-50 text-red-600' : 'bg-green-600 text-white'}`}>{c.is_active ? 'Deactivate' : 'Activate'}</button>
            </div>
          ))}
        </div>
        <div className="pt-2 border-t border-border space-y-2">
          <div className="text-xs font-bold text-foreground uppercase">New category</div>
          <Field label="Name"><TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Breakfast" /></Field>
          <Field label="Slug" hint="Leave blank to generate from the name."><TextInput value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="breakfast" /></Field>
          <Field label="Description"><TextInput value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-2 items-end">
            <Field label="Sort order"><TextInput type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} /></Field>
            <label className="flex items-center gap-2 text-sm text-foreground font-semibold pb-2.5"><Toggle checked={form.is_active} onChange={(v) => setForm({ ...form, is_active: v })} /> Active</label>
          </div>
          <button onClick={create} disabled={saving} className="w-full py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold flex items-center justify-center gap-1.5 disabled:opacity-50"><Plus className="w-4 h-4" /> Create category</button>
        </div>
      </div>
    </Modal>
  );
}