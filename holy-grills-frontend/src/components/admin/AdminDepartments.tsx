import { useState, useEffect } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import LoadingSpinner from '@/components/LoadingSpinner';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Card, Toggle, Pill } from './AdminShared';

export default function AdminDepartments() {
  const [tab, setTab] = useState('depts');
  const [depts, setDepts] = useState([]);
  const [levels, setLevels] = useState([]);
  const [faculties, setFaculties] = useState([]);
  const [modal, setModal] = useState(null);

  // Faculties come from GET /departments/faculties (server-side, campus-aware
  // distinct list) instead of being guessed from the loaded department rows.
  const load = async () => {
    const [deptRows, levelRows, facultyRows] = await Promise.all([
      mockApi.admin.getDepartments().catch(() => []),
      mockApi.admin.getAcademicLevels().catch(() => []),
      mockApi.admin.getFaculties().catch(() => []),
    ]);
    setDepts(deptRows); setLevels(levelRows); setFaculties(facultyRows);
  };
  useEffect(() => { load(); }, []);

  const saveDept = async () => {
    if (!modal.item.name?.trim()) { toast({ title: 'Department name is required', variant: 'destructive' }); return; }
    try {
      if (modal.isNew) await mockApi.admin.createDepartment(modal.item);
      else await mockApi.admin.updateDepartment(modal.item.id, modal.item);
      setModal(null); await load();
    } catch (e) { toast({ title: 'Failed to save department', description: e.message, variant: 'destructive' }); }
  };
  const saveLevel = async () => {
    if (!modal.item.name?.trim() || !modal.item.value?.trim()) { toast({ title: 'Level name and value are required', variant: 'destructive' }); return; }
    const body = { ...modal.item, value: modal.item.value, sort_order: Number(modal.item.sort_order) || undefined };
    try {
      if (modal.isNew) await mockApi.admin.createAcademicLevel(body);
      else await mockApi.admin.updateAcademicLevel(modal.item.id, body);
      setModal(null); await load();
    } catch (e) { toast({ title: 'Failed to save level', description: e.message, variant: 'destructive' }); }
  };
  const delDept = async (id) => { try { await mockApi.admin.deleteDepartment(id); await load(); } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); } };
  const delLevel = async (id) => { try { const res = await mockApi.admin.deleteAcademicLevel(id); toast({ title: res?.message || 'Level deactivated' }); } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); } await load(); };
  // Same deactivate/restore pair as academic levels: DELETE soft-deletes and the
  // dedicated POST /admin/departments/<id>/restore brings the row back.
  const toggleDept = async (d) => {
    try {
      const res = await (d.is_active ? mockApi.admin.deleteDepartment(d.id) : mockApi.admin.restoreDepartment(d.id));
      toast({ title: res?.message || (d.is_active ? 'Department deactivated' : 'Department restored') });
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
    await load();
  };
  const toggleLevel = async (l) => {
    try {
      const res = await (l.is_active ? mockApi.admin.deleteAcademicLevel(l.id) : mockApi.admin.restoreAcademicLevel(l.id));
      toast({ title: res?.message || (l.is_active ? 'Level deactivated' : 'Level restored') });
    } catch (e) { toast({ title: 'Failed', description: e.message, variant: 'destructive' }); }
    await load();
  };

  if (!depts.length && !levels.length) return <LoadingSpinner label="Loading..." />;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 p-1 rounded-full bg-secondary">
        {[{ id: 'depts', label: 'Departments' }, { id: 'levels', label: 'Academic Levels' }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} className={`flex-1 py-2 rounded-full text-xs font-bold ${tab === t.id ? 'bg-white text-primary shadow-sm' : 'text-muted-foreground'}`}>{t.label}</button>
        ))}
      </div>
      {tab === 'depts' ? (
        <div className="space-y-2">
          <div className="flex justify-end"><button onClick={() => setModal({ item: { name: '', faculty: '' }, isNew: true, kind: 'dept' })} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add</button></div>
          {depts.map((d) => (
            <Card key={d.id} className="flex items-center gap-3 !p-3">
              <div className="flex-1"><div className="font-bold text-sm text-foreground">{d.name}</div><div className="text-xs text-muted-foreground">Faculty: {d.faculty}</div></div>
              <Pill tone={d.is_active ? 'green' : 'red'}>{d.is_active ? 'Active' : 'Hidden'}</Pill>
              <Toggle checked={d.is_active} onChange={() => toggleDept(d)} />
              <button onClick={() => delDept(d.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex justify-end"><button onClick={() => setModal({ item: { name: '', value: '', sort_order: 1 }, isNew: true, kind: 'level' })} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold"><Plus className="w-4 h-4" /> Add</button></div>
          {levels.map((l) => (
            <Card key={l.id} className="flex items-center gap-3 !p-3">
              <div className="flex-1"><div className="font-bold text-sm text-foreground">{l.name}</div><div className="text-xs text-muted-foreground">Value: {l.value}</div></div>
              <Pill tone={l.is_active ? 'green' : 'red'}>{l.is_active ? 'Active' : 'Hidden'}</Pill>
              <Toggle checked={l.is_active} onChange={() => toggleLevel(l)} />
              <button onClick={() => delLevel(l.id)} className="p-2 rounded-lg hover:bg-red-50"><Trash2 className="w-4 h-4 text-red-500" /></button>
            </Card>
          ))}
        </div>
      )}
      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.isNew ? 'Add New' : 'Edit'}>
        {modal && modal.kind === 'dept' ? (
          <div className="space-y-3">
            <Field label="Department name"><TextInput value={modal.item.name} onChange={(e) => setModal({ item: { ...modal.item, name: e.target.value }, kind: modal.kind, isNew: modal.isNew })} /></Field>
            <Field label="Faculty" hint="Type any faculty name — existing faculties appear as suggestions.">
              <input list="faculties-list" value={modal.item.faculty} onChange={(e) => setModal({ item: { ...modal.item, faculty: e.target.value }, kind: modal.kind, isNew: modal.isNew })} placeholder="e.g. Engineering, Sciences…" className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card" />
              <datalist id="faculties-list">{(faculties.length ? faculties : [...new Set(depts.map((d) => d.faculty).filter(Boolean))]).map((f) => <option key={f} value={f} />)}</datalist>
            </Field>
            <button onClick={saveDept} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Save</button>
          </div>
        ) : modal && (
          <div className="space-y-3">
            <Field label="Level name"><TextInput value={modal.item.name} onChange={(e) => setModal({ item: { ...modal.item, name: e.target.value }, kind: modal.kind, isNew: modal.isNew })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Value (e.g. 100L, PG)"><TextInput value={modal.item.value} onChange={(e) => setModal({ item: { ...modal.item, value: e.target.value }, kind: modal.kind, isNew: modal.isNew })} placeholder="100L" /></Field>
              <Field label="Sort order"><TextInput type="number" value={modal.item.sort_order} onChange={(e) => setModal({ item: { ...modal.item, sort_order: e.target.value }, kind: modal.kind, isNew: modal.isNew })} /></Field>
            </div>
            <button onClick={saveLevel} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Save</button>
          </div>
        )}
      </Modal>
    </div>
  );
}