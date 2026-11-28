import AdminStoreReport from './AdminStoreReport';
import { useEffect, useRef, useState } from 'react';
import { Building2, MapPin, Plus, Store, Users } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { useCampus } from '@/lib/campusContext';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { msg } from '@/lib/messages';
import { toast } from '@/components/ui/use-toast';
import { Card, Field, Modal, TextInput } from './ui/AdminKit';

const emptyStore = { name: '', slug: '', address: '', instructions: '', lat: '', lon: '', is_active: true, pickup_enabled: true, delivery_enabled: true };
const emptyUniversity = { name: '', slug: '', is_active: true };
const button = 'min-h-11 rounded-full bg-primary px-5 py-2 text-sm font-bold text-white disabled:opacity-50';
const outline = 'min-h-11 rounded-full border border-border px-4 py-2 text-sm font-bold disabled:opacity-50';
const control = 'w-full min-h-11 rounded-xl border border-border bg-background px-3 py-2 text-sm';

export default function AdminStores() {
  const { user } = useHolyGrill();
  const { adminCampusId, campusId } = useCampus();
  const superAdmin = user?.role === 'super_admin';
  const [selected, setSelected] = useState(superAdmin ? adminCampusId || '' : campusId || '');
  const [orderingEnabled,setOrderingEnabled]=useState<boolean | null>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [campuses, setCampuses] = useState<any[]>([]);
  const [universities, setUniversities] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<any>(null);
  const [form, setForm] = useState<any>(emptyStore);
  const [team, setTeam] = useState<any>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [universityEditor, setUniversityEditor] = useState<any>(null);
  const [universityForm, setUniversityForm] = useState(emptyUniversity);
  const [link, setLink] = useState('');
  const intent = useCmsCreateIntent();
  const lock = useRef(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; generation.current++; }; }, []);
  useEffect(() => { setSelected(superAdmin ? adminCampusId || '' : campusId || ''); }, [adminCampusId, campusId, superAdmin]);
  const load = async () => {
    const epoch = ++generation.current; setLoading(true); setError('');
    try {
      const [stores, allCampuses, allUniversities] = await Promise.all([
        apiClient.get(`/admin/stores${selected ? `?campus_id=${selected}` : ''}`), liveApi.admin.getCampuses(), apiClient.get('/admin/universities'),
      ]);
      if (!mounted.current || epoch !== generation.current) return;
      setOrderingEnabled(stores.ordering_enabled);setRows(stores.stores); setCampuses(allCampuses); setUniversities(allUniversities.universities);
      setLink(allCampuses.find(row => row.id === selected)?.university_id || '');
    } catch (failure) { if (mounted.current && epoch === generation.current) setError(failure.message); }
    finally { if (mounted.current && epoch === generation.current) setLoading(false); }
  };
  useEffect(() => { setEditor(null); setTeam(null); setUniversityEditor(null); intent.clear(); load(); }, [selected, user?.id]);
  const act = async (operation, title, close) => {
    if (lock.current) return;
    lock.current = true; setBusy(true); const epoch = generation.current;
    try {
      await operation();
      if (mounted.current && epoch === generation.current) { close(); intent.clear(); toast({ title }); await load(); }
    } catch (failure) { if (mounted.current && epoch === generation.current) toast({ title: failure.message, variant: 'destructive' }); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  };
  const begin = row => { intent.clear(); setEditor(row || {}); setForm(row ? { ...row, lat: row.lat ?? '', lon: row.lon ?? '' } : emptyStore); };
  const save = event => {
    event.preventDefault();
    if (['lat','lon'].some(key=>String(form[key]).trim()!=='' && !Number.isFinite(Number(form[key])))) { toast({title:msg('STORE_COORDINATES_INVALID','Enter a valid latitude and longitude together, or leave both empty.'),variant:'destructive'});return; }
    const payload = Object.fromEntries(Object.keys(emptyStore).map(key => [key, ['lat', 'lon'].includes(key) ? String(form[key]).trim() === '' ? null : Number(form[key]) : form[key]]));
    act(() => editor.id ? apiClient.patch(`/admin/stores/${editor.id}`, { ...payload, expected_updated_at: editor.updated_at }) : apiClient.post('/admin/stores', intent.body({ ...payload, campus_id: selected })), msg('FE_STORE_SAVED', 'Store saved'), () => setEditor(null));
  };
  const openTeam = async row => {
    if (lock.current) return;
    lock.current = true; setBusy(true); const epoch = generation.current;
    try { const result = await apiClient.get(`/admin/stores/${row.id}/staff`); if (mounted.current && epoch === generation.current) { setTeam(result); setPicked(result.assigned.map(person => person.id)); setSearch(''); } }
    catch (failure) { if (mounted.current && epoch === generation.current) toast({ title: failure.message, variant: 'destructive' }); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  };
  const selectedCampus = campuses.find(row => row.id === selected);
  const candidates = team ? [...team.eligible, ...team.assigned.filter(person => !team.eligible.some(candidate => candidate.id === person.id))] : [];
  return <div className="space-y-5">
    <header className="rounded-3xl bg-gradient-dark p-5 sm:p-7 text-white"><Store className="mb-3 h-8 w-8 text-accent" /><h2 className="font-heading text-2xl font-bold">{msg('FE_STORE_SETUP_TITLE', 'Your stores, one campus')}</h2><p className="mt-2 text-sm text-white/80">{msg('FE_STORE_SETUP_HELP', 'Configure each store’s address and team.')}</p></header>
    <Card className="p-4 text-sm">{!selected || loading ? msg('FE_STORE_SCOPE_STATUS','Select a campus to check store-ordering availability.') : orderingEnabled ? msg('FE_STORE_ORDERING_ACTIVE','Store ordering is active for this campus. Menu, stock, capacity and windows remain campus-wide.') : msg('FE_STORE_CUTOVER_PENDING', 'Store ordering is not active yet. Current orders continue through the existing campus setup.')}</Card>
    <div className="flex flex-col sm:flex-row gap-3 sm:items-end sm:justify-between"><label className="block space-y-1 text-sm font-bold">{msg('FE_STORE_CAMPUS', 'Campus')}<select disabled={busy || !superAdmin} value={selected} onChange={event => setSelected(event.target.value)} className={control}><option value="">{msg('FE_STORE_ALL', 'All campuses')}</option>{campuses.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><button className={button} disabled={!selected || busy} onClick={() => begin(null)}><Plus className="mr-2 inline h-4 w-4" />{msg('FE_STORE_ADD', 'Add store')}</button></div>
    {!loading && !error && <AdminStoreReport key={`${user?.id}:${selected}`} campusId={selected} stores={rows} universities={universities} />}
    {loading ? <p role="status">{msg('FE_LOOKUP_LOADING', 'Loading…')}</p> : error ? <Card className="space-y-3 p-5"><p role="alert">{error}</p><button className={button} onClick={load}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></Card> : !rows.length ? <Card className="p-6 text-sm">{msg('FE_STORE_EMPTY', 'No stores configured for this selection.')}</Card> : <div className="grid gap-4 lg:grid-cols-2">{rows.map(row => <Card key={row.id} className="min-w-0 p-5"><div className="flex items-start gap-3"><div className="rounded-xl bg-primary/10 p-3 text-primary"><Store className="h-5 w-5" /></div><div className="min-w-0 flex-1"><h3 className="font-heading text-lg font-bold break-words">{row.name}</h3><p className="text-xs text-muted-foreground">{campuses.find(c => c.id === row.campus_id)?.name}</p></div><span className="rounded-full bg-secondary px-3 py-1 text-xs">{row.is_active ? msg('FE_STORE_ACTIVE', 'Active') : msg('FE_STORE_INACTIVE', 'Inactive')}</span></div><p className="my-4 flex gap-2 text-sm"><MapPin className="h-4 w-4 shrink-0" /><span className="whitespace-pre-wrap break-words">{row.address}</span></p><div className="flex flex-wrap gap-2 text-xs">{row.pickup_enabled && <span className="rounded-lg bg-secondary p-2">{msg('FE_STORE_PICKUP', 'Store pickup')}</span>}{row.delivery_enabled && <span className="rounded-lg bg-secondary p-2">{msg('FE_STORE_DELIVERY', 'Delivery')}</span>}</div><div className="mt-5 grid grid-cols-2 gap-2"><button disabled={busy} className={outline} onClick={() => begin(row)}>{msg('FE_STORE_EDIT', 'Edit store')}</button><button disabled={busy} className={outline} onClick={() => openTeam(row)}><Users className="mr-1 inline h-4 w-4" />{msg('FE_STORE_STAFF', 'Manage team')}</button></div></Card>)}</div>}
    {superAdmin && <Card className="space-y-4 p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="flex items-center gap-2 font-bold"><Building2 className="h-5 w-5" />{msg('FE_UNIVERSITY_TITLE', 'Universities')}</h3><button disabled={busy} className={outline} onClick={() => { intent.clear(); setUniversityEditor({}); setUniversityForm(emptyUniversity); }}>{msg('FE_UNIVERSITY_ADD', 'Add university')}</button></div>{universities.map(row => <div key={row.id} className="flex items-center justify-between gap-3 border-t border-border pt-3"><p className="break-words">{row.name}</p><button className={outline} disabled={busy} onClick={() => { intent.clear(); setUniversityEditor(row); setUniversityForm({ name: row.name, slug: row.slug, is_active: row.is_active }); }}>{msg('FE_UNIVERSITY_EDIT', 'Edit university')}</button></div>)}{selectedCampus && <div className="border-t border-border pt-4 space-y-3"><label className="block space-y-1 text-sm">{msg('FE_UNIVERSITY_LINK', 'Link campus to university')}<select value={link} onChange={event => setLink(event.target.value)} className={control}><option value="">{msg('FE_UNIVERSITY_UNLINKED', 'Not linked')}</option>{universities.filter(row => row.is_active || row.id === link).map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select></label><button disabled={busy || link === (selectedCampus.university_id || '')} className={button} onClick={() => act(() => apiClient.patch(`/admin/campuses/${selected}/university`, { university_id: link || null, expected_updated_at: selectedCampus.updated_at }), msg('FE_UNIVERSITY_LINKED', 'Campus link saved'), () => {})}>{msg('FE_UNIVERSITY_LINK_SAVE', 'Save campus link')}</button></div>}</Card>}
    {editor && <Modal open title={msg(editor.id ? 'FE_STORE_EDIT' : 'FE_STORE_ADD', editor.id ? 'Edit store' : 'Add store')} onClose={() => { if (!busy) setEditor(null); }}><form onSubmit={save} className="space-y-4">{[['name', 'FE_STORE_NAME', 'Store name', 120], ['slug', 'FE_STORE_SLUG', 'Identifier', 80], ['address', 'FE_STORE_ADDRESS', 'Store address', 500], ['instructions', 'FE_STORE_INSTRUCTIONS', 'Pickup instructions (optional)', 500], ['lat', 'FE_STORE_LAT', 'Latitude (optional)', 32], ['lon', 'FE_STORE_LON', 'Longitude (optional)', 32]].map(([key, label, fallback, max]) => <Field key={key} label={msg(label as string, fallback as string)}><TextInput required={['name', 'slug', 'address'].includes(key as string)} maxLength={max as number} disabled={busy} value={form[key]} onChange={event => setForm({ ...form, [key]: event.target.value })} /></Field>)}<div className="flex flex-wrap gap-4">{[['is_active', 'FE_STORE_ACTIVE', 'Active'], ['pickup_enabled', 'FE_STORE_PICKUP', 'Pickup'], ['delivery_enabled', 'FE_STORE_DELIVERY', 'Delivery']].map(([key, label, fallback]) => <label key={key} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" disabled={busy} checked={form[key]} onChange={event => setForm({ ...form, [key]: event.target.checked })} />{msg(label, fallback)}</label>)}</div><button className={`${button} w-full`} disabled={busy}>{msg('FE_STORE_SAVE', 'Save store')}</button></form></Modal>}
    {team && <Modal open title={msg('FE_STORE_STAFF', 'Manage team')} onClose={() => { if (!busy) setTeam(null); }}><div className="space-y-4"><p className="font-bold">{team.store.name}</p><p className="text-sm text-muted-foreground">{msg('FE_STORE_TEAM_SCOPE', 'Kitchen and rider assignments belong to this store’s campus.')}</p><input aria-label={msg('FE_STORE_TEAM_SEARCH', 'Search team by name or email')} placeholder={msg('FE_STORE_TEAM_SEARCH', 'Search team by name or email')} value={search} onChange={event => setSearch(event.target.value)} className={control} /><div className="max-h-72 overflow-y-auto space-y-2">{candidates.filter(person => `${person.full_name || person.name || ''} ${person.email}`.toLowerCase().includes(search.toLowerCase())).map(person => <label key={person.id} className="flex items-start gap-3 rounded-xl border border-border p-3 text-sm"><input type="checkbox" disabled={busy || person.eligible === false && !picked.includes(person.id)} checked={picked.includes(person.id)} onChange={event => setPicked(value => event.target.checked ? [...value, person.id] : value.filter(id => id !== person.id))} /><span className="min-w-0 break-words"><strong>{person.full_name || person.name || person.email}</strong><span className="block text-xs">{person.email} · {person.role}</span>{person.eligible === false && <span className="text-xs text-destructive">{msg('FE_STORE_TEAM_STALE', 'This assignment is no longer eligible. Remove it before saving.')}</span>}</span></label>)}</div><button disabled={busy} className={`${button} w-full`} onClick={() => act(() => apiClient.patch(`/admin/stores/${team.store.id}/staff`, { user_ids: picked, expected_updated_at: team.store.updated_at }), msg('FE_STORE_TEAM_SAVED', 'Store team saved'), () => setTeam(null))}>{msg('FE_STORE_TEAM_SAVE', 'Save team')}</button></div></Modal>}
    {universityEditor && <Modal open title={msg(universityEditor.id ? 'FE_UNIVERSITY_EDIT' : 'FE_UNIVERSITY_ADD', universityEditor.id ? 'Edit university' : 'Add university')} onClose={() => { if (!busy) setUniversityEditor(null); }}><form className="space-y-4" onSubmit={event => { event.preventDefault(); act(() => universityEditor.id ? apiClient.patch(`/admin/universities/${universityEditor.id}`, { ...universityForm, expected_updated_at: universityEditor.updated_at }) : apiClient.post('/admin/universities', intent.body(universityForm)), msg('FE_UNIVERSITY_SAVED', 'University saved'), () => setUniversityEditor(null)); }}><Field label={msg('FE_UNIVERSITY_NAME', 'University name')}><TextInput required maxLength={160} value={universityForm.name} disabled={busy} onChange={event => setUniversityForm({ ...universityForm, name: event.target.value })} /></Field><Field label={msg('FE_STORE_SLUG', 'Identifier')}><TextInput required maxLength={80} value={universityForm.slug} disabled={busy} onChange={event => setUniversityForm({ ...universityForm, slug: event.target.value })} /></Field><label className="flex gap-2"><input type="checkbox" checked={universityForm.is_active} disabled={busy} onChange={event => setUniversityForm({ ...universityForm, is_active: event.target.checked })} />{msg('FE_STORE_ACTIVE', 'Active')}</label><button disabled={busy} className={`${button} w-full`}>{msg('FE_UNIVERSITY_SAVE', 'Save university')}</button></form></Modal>}
  </div>;
}
