import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { Card, Field, Modal, TextInput } from './ui/AdminKit';

export default function AdminCampuses() {
  const { user } = useHolyGrill();
  const { reloadCampuses } = useCampus();
  const canManage = user?.role === 'super_admin';
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [editing, setEditing] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', slug: '', is_active: true });
  const [saving, setSaving] = useState(false);
  const intent = useCmsCreateIntent();
  const load = async () => {
    setLoading(true); setError(false);
    try { setRows(await liveApi.admin.getCampuses()); }
    catch { setError(true); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);
  const begin = row => {
    intent.clear(); setEditing(row);
    setForm(row ? { name: row.name, slug: row.slug, is_active: row.is_active } : { name: '', slug: '', is_active: true });
    setOpen(true);
  };
  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form, name: form.name.trim(), slug: form.slug.trim() };
      if (editing) await liveApi.admin.updateCampus(editing.id, { ...body, expected_updated_at: editing.updated_at });
      else await liveApi.admin.createCampus(intent.body(body));
      intent.clear(); setOpen(false); reloadCampuses(); await load();
      toast({ title: msg('FE_CAMPUS_SAVED', 'Campus saved') });
    } catch (e) { toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: e.message, variant: 'destructive' }); }
    setSaving(false);
  };
  if (loading) return <StaffPanelSkeleton />;
  if (error) return <Card className="p-5 space-y-3"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="font-bold text-primary">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></Card>;
  return <div className="space-y-4">
    {canManage ? <button onClick={() => begin(null)} className="px-4 py-2 rounded-full bg-gradient-cta text-white font-bold">{msg('FE_CAMPUS_ADD', 'Add campus')}</button> : <p>{msg('FE_CAMPUS_GLOBAL_ONLY', 'Campus names and availability are managed by super admins.')}</p>}
    {!rows.length && <p>{msg('FE_CAMPUS_EMPTY', 'No campuses found.')}</p>}
    {rows.map(row => <Card key={row.id} className="p-4 flex justify-between gap-3 items-center"><div><p className="font-bold">{row.name}</p><p className="text-sm text-muted-foreground">{row.slug}</p><input aria-label={msg('FE_CAMPUS_ACTIVE', 'Active')} type="checkbox" checked={row.is_active} readOnly disabled /></div>{canManage && <button onClick={() => begin(row)} className="text-primary font-bold">{msg('FE_CAMPUS_EDIT', 'Edit campus')}</button>}</Card>)}
    {open && <Modal open title={msg(editing ? 'FE_CAMPUS_EDIT' : 'FE_CAMPUS_ADD', editing ? 'Edit campus' : 'Add campus')} onClose={() => { if (!saving) setOpen(false); }}><div className="space-y-3">
      <Field label={msg('FE_CAMPUS_NAME', 'Campus name')}><TextInput value={form.name} maxLength={128} disabled={saving} onChange={e => setForm({ ...form, name: e.target.value })} /></Field>
      <Field label={msg('FE_CAMPUS_SLUG', 'Campus slug')}><TextInput value={form.slug} maxLength={80} disabled={saving} onChange={e => setForm({ ...form, slug: e.target.value })} /></Field>
      <label className="flex gap-2 items-center"><input type="checkbox" checked={form.is_active} disabled={saving || editing?.is_default} onChange={e => setForm({ ...form, is_active: e.target.checked })} />{msg('FE_CAMPUS_ACTIVE', 'Active')}</label>
      <button disabled={saving || !form.name.trim() || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(form.slug.trim())} onClick={save} className="w-full p-3 rounded-full bg-gradient-cta text-white font-bold disabled:opacity-50">{msg('FE_CAMPUS_SAVE', 'Save campus')}</button>
    </div></Modal>}
  </div>;
}
