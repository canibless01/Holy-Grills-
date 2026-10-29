import { useState, useEffect, useCallback, useRef } from 'react';
import { Plus, Pencil, Search } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import StaffPanelSkeleton from '@/components/skeletons/StaffPanelSkeleton';
import { toast } from '@/components/ui/use-toast';
import { Modal, Field, TextInput, Card, Toggle, Pill } from './AdminShared';
import { msg } from '@/lib/messages';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';

export default function AdminDepartments() {
  const { user } = useHolyGrill();
  const { campuses } = useCampus();
  const [tab, setTab] = useState('depts');
  const [depts, setDepts] = useState([]);
  const [levels, setLevels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState(null);
  const writing = useRef(false);
  const generation = useRef(0);
  const ownCampus = user?.campus_id || user?.profile?.campus_id;
  const canEdit = (row) => user?.role === 'super_admin' || (!!row.campus_id && row.campus_id === ownCampus);
  const load = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true); setError(false);
    try {
      const [departmentRows, levelRows] = await Promise.all([liveApi.admin.getDepartments(), liveApi.admin.getAcademicLevels()]);
      if (request !== generation.current) return;
      setDepts(departmentRows); setLevels(levelRows);
    } catch (e) {
      if (request === generation.current) {
        setError(true);
        toast({ title: msg('FE_ACADEMIC_LOAD_FAILED', 'Academic settings could not be loaded.'), description: e.message, variant: 'destructive' });
      }
    } finally { if (request === generation.current) setLoading(false); }
  }, []);
  useEffect(() => { load(); return () => { generation.current++; }; }, [load]);
  const edit = (item, kind, isNew = false) => setModal({ item: { sort_order: 0, rank: 0, ...item }, kind, isNew });
  const save = async () => {
    if (writing.current || !modal) return;
    const item = modal.item;
    if (!item.name?.trim() || (modal.kind === 'dept' ? !item.faculty?.trim() : !item.value?.trim())) {
      toast({ title: modal.kind === 'dept' ? msg('FE_ACADEMIC_DEPT_REQUIRED', 'Enter both the department name and faculty.') : msg('FE_ADMIN_DEPARTMENTS_LEVEL_NAME_AND_VALUE_ARE_REQUIRED', 'Level name and value are required'), variant: 'destructive' }); return;
    }
    const sortOrder = Number(item.sort_order), rank = Number(item.rank ?? 0);
    if (!Number.isInteger(sortOrder) || sortOrder < 0 || sortOrder > 100000 || (modal.kind === 'level' && (!Number.isInteger(rank) || rank < 0 || rank > 100000))) {
      toast({ title: msg('FE_ACADEMIC_ORDER_INVALID', 'Sort order and rank must be whole numbers from 0 to 100000.'), variant: 'destructive' }); return;
    }
    const body = modal.kind === 'dept'
      ? { name: item.name.trim(), faculty: item.faculty.trim(), sort_order: sortOrder, ...(item.slug?.trim() ? { slug: item.slug.trim() } : {}) }
      : { name: item.name.trim(), value: item.value.trim(), rank, sort_order: sortOrder };
    writing.current = true; setBusy('save');
    try {
      if (modal.kind === 'dept') {
        if (modal.isNew) await liveApi.admin.createDepartment(body); else await liveApi.admin.updateDepartment(item.id, body);
      } else {
        if (modal.isNew) await liveApi.admin.createAcademicLevel(body); else await liveApi.admin.updateAcademicLevel(item.id, body);
      }
      setModal(null); await load(); toast({ title: msg('FE_ACADEMIC_SAVED', 'Academic settings saved.') });
    } catch (e) { toast({ title: msg('FE_ACADEMIC_SAVE_FAILED', 'Academic settings could not be saved.'), description: e.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(null); }
  };
  const toggle = async (row, kind) => {
    if (writing.current || !canEdit(row)) return;
    writing.current = true; setBusy(row.id);
    try {
      const result = kind === 'dept'
        ? await (row.is_active ? liveApi.admin.deleteDepartment(row.id) : liveApi.admin.restoreDepartment(row.id))
        : await (row.is_active ? liveApi.admin.deleteAcademicLevel(row.id) : liveApi.admin.restoreAcademicLevel(row.id));
      toast({ title: result?.message || msg('FE_ACADEMIC_SAVED', 'Academic settings saved.') }); await load();
    } catch (e) { toast({ title: msg('FE_ACADEMIC_SAVE_FAILED', 'Academic settings could not be saved.'), description: e.message, variant: 'destructive' }); }
    finally { writing.current = false; setBusy(null); }
  };
  const isDept = tab === 'depts';
  const rows = (isDept ? depts : levels).filter((row) => `${row.name} ${row.faculty || row.value || ''}`.toLowerCase().includes(search.trim().toLowerCase()));
  const faculties = [...new Set(depts.map((row) => row.faculty).filter(Boolean))].sort();
  const close = () => { if (!writing.current) setModal(null); };
  const update = (key, value) => setModal({ ...modal, item: { ...modal.item, [key]: value } });
  return <div className="space-y-4">
    <div className="flex gap-1 p-1 rounded-full bg-secondary">
      {[['depts', msg('FE_ACADEMIC_DEPARTMENTS', 'Departments')], ['levels', msg('FE_ACADEMIC_LEVELS', 'Academic Levels')]].map(([id, label]) =>
        <button key={id} onClick={() => { setTab(id); setSearch(''); }} className={`flex-1 py-2 rounded-full text-xs font-bold ${tab === id ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground'}`}>{label}</button>)}
    </div>
    <div className="flex gap-2 items-center">
      <div className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} aria-label={msg('FE_ACADEMIC_SEARCH', 'Search academic settings')} placeholder={msg('FE_ACADEMIC_SEARCH', 'Search academic settings')} className="w-full py-2 pl-9 pr-3 rounded-xl border border-border bg-card text-sm" /></div>
      <button disabled={loading || error || !!busy} onClick={() => edit(isDept ? { name: '', faculty: '', slug: '' } : { name: '', value: '' }, isDept ? 'dept' : 'level', true)} className="flex items-center gap-1 px-3 py-2 rounded-full bg-primary text-white text-xs font-bold disabled:opacity-50"><Plus className="w-4 h-4" />{msg('FE_ACADEMIC_ADD', 'Add')}</button>
    </div>
    {loading ? <StaffPanelSkeleton /> : error ? <Card><p>{msg('FE_ACADEMIC_LOAD_FAILED', 'Academic settings could not be loaded.')}</p><button onClick={load} className="mt-2 text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></Card> : rows.length === 0 ?
      <Card><p className="text-sm text-muted-foreground">{search ? msg('FE_ACADEMIC_NO_MATCHES', 'No matching academic settings.') : msg('FE_ACADEMIC_EMPTY', 'No entries yet. Add the first one above.')}</p></Card> :
      <div className="space-y-2">{rows.map((row) => <Card key={row.id} className="flex items-center gap-3 !p-3">
        <div className="flex-1 min-w-0"><div className="font-bold text-sm text-foreground">{row.name}</div><div className="text-xs text-muted-foreground">{isDept ? row.faculty : row.value}</div>
          <span className="text-[11px] text-muted-foreground">{row.campus_id ? (campuses.find((campus) => campus.id === row.campus_id)?.name || msg('FE_ACADEMIC_CAMPUS', 'Campus')) : msg('FE_ACADEMIC_GLOBAL', 'Global · super admin manages this entry')}</span></div>
        <Pill tone={row.is_active ? 'green' : 'red'}>{row.is_active ? msg('FE_ACADEMIC_ACTIVE', 'Active') : msg('FE_ACADEMIC_HIDDEN', 'Hidden')}</Pill>
        {canEdit(row) && <><button disabled={!!busy} aria-label={`${msg('FE_ACADEMIC_EDIT', 'Edit')} ${row.name}`} onClick={() => edit(row, isDept ? 'dept' : 'level')} className="p-2 rounded-lg hover:bg-secondary disabled:opacity-50"><Pencil className="w-4 h-4" /></button>
          <Toggle checked={row.is_active} disabled={!!busy} label={`${msg('FE_ACADEMIC_VISIBILITY', 'Visibility')} ${row.name}`} onChange={() => toggle(row, isDept ? 'dept' : 'level')} /></>}
      </Card>)}</div>}
    <Modal open={!!modal} onClose={close} title={modal?.isNew ? msg('FE_ACADEMIC_ADD', 'Add') : msg('FE_ACADEMIC_EDIT', 'Edit')}>
      {modal && <fieldset disabled={!!busy} className="space-y-3">
        <Field label={msg('FE_ACADEMIC_NAME', 'Name')}><TextInput value={modal.item.name} onChange={(event) => update('name',event.target.value)} /></Field>
        {modal.kind === 'dept' ? <>
          <Field label={msg('FE_ACADEMIC_FACULTY', 'Faculty')} hint={msg('FE_ACADEMIC_FACULTY_HINT', 'Choose an existing faculty or enter a new one.')}><input list="faculties-list" value={modal.item.faculty} onChange={(event) => update('faculty',event.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card" /></Field>
          <datalist id="faculties-list">{faculties.map((faculty) => <option key={faculty} value={faculty} />)}</datalist>
          <Field label={msg('FE_ACADEMIC_SLUG', 'Slug (optional)')}><TextInput value={modal.item.slug || ''} onChange={(event) => update('slug',event.target.value)} /></Field>
        </> : <>
          <Field label={msg('FE_ACADEMIC_VALUE', 'Stored value')}><TextInput value={modal.item.value} onChange={(event) => update('value',event.target.value)} /></Field>
          <Field label={msg('FE_ACADEMIC_RANK', 'Level rank')} hint={msg('FE_ACADEMIC_RANK_HINT', 'Undergraduate year rank, for example 100 or 400. Use 0 for a non-year option such as Postgraduate.')}><TextInput type="number" min="0" max="100000" value={modal.item.rank ?? 0} onChange={(event) => update('rank',event.target.value)} /></Field>
        </>}
        <Field label={msg('FE_ACADEMIC_SORT', 'Sort order')}><TextInput type="number" min="0" max="100000" value={modal.item.sort_order} onChange={(event) => update('sort_order',event.target.value)} /></Field>
        <button disabled={!!busy} onClick={save} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50">{busy === 'save' ? msg('FE_ACADEMIC_SAVING', 'Saving…') : msg('FE_ACADEMIC_SAVE', 'Save')}</button>
      </fieldset>}
    </Modal>
  </div>;
}
