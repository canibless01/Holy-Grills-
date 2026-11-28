import { useEffect, useRef, useState } from 'react';
import { liveApi } from '@/lib/liveApi';
import { msg } from '@/lib/messages';

type Account = { id: string; full_name?: string; email?: string; phone?: string };
type Props = { users: Account[]; value: string; onChange: (id: string) => void; campusId?: string; label: string; searchLabel: string; disabled?: boolean; allLabel?: string };

/** Search the scoped directory rather than limiting recipients to its first page. */
export default function AdminUserPicker({ users, value, onChange, campusId, label, searchLabel, disabled = false, allLabel }: Props) {
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<Account[]>(users);
  const [selected, setSelected] = useState<Account | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const change = useRef(onChange);
  change.current = onChange;
  const term = query.trim();

  useEffect(() => {
    let active = true;
    setError('');
    if (!term) { setRows(users); setSearching(false); return; }
    setRows([]); setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const result = await liveApi.admin.getUsers({ q: term, limit: 20, ...(campusId ? { campus_id: campusId } : {}) });
        if (active) setRows(Array.isArray(result) ? result : []);
      } catch (failure) {
        if (active) setError(failure.message || msg('FE_USER_PICKER_FAILED', 'User search could not be loaded. Please retry.'));
      } finally { if (active) setSearching(false); }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [term, campusId, users, revision]);

  useEffect(() => {
    let active = true;
    if (!value || value === 'all') { setSelected(null); return; }
    const found = rows.find(row => row.id === value) || users.find(row => row.id === value);
    if (found) { setSelected(found); return; }
    liveApi.admin.getUser(value).then(result => {
      if (!active) return;
      const profile = result?.profile || result?.user || result;
      if (profile?.id === value) setSelected(profile);
      else { change.current(''); setError(msg('FE_USER_PICKER_FAILED', 'User search could not be loaded. Please retry.')); }
    }).catch(() => { if (active) { change.current(''); setError(msg('FE_USER_PICKER_FAILED', 'User search could not be loaded. Please retry.')); } });
    return () => { active = false; };
  }, [value, campusId, users, rows]);

  const options = selected?.id === value && !rows.some(row => row.id === value) ? [selected, ...rows] : rows;
  return <div className="space-y-2">
    <input aria-label={searchLabel} placeholder={msg('FE_USER_SEARCH', 'Search by name, phone or email…')} disabled={disabled} value={query} onChange={event => { setQuery(event.target.value); change.current(''); }} className="w-full p-2.5 rounded-xl border border-border text-sm" />
    <select aria-label={label} value={value} disabled={disabled || searching || !!error} onChange={event => change.current(event.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm">
      <option value="">{msg('FE_USER_PICKER_SELECT', 'Select user…')}</option>
      {allLabel && <option value="all">{allLabel}</option>}
      {options.map(row => <option key={row.id} value={row.id}>{row.full_name || row.email || msg('FE_USER_PROFILE', 'User profile')}{row.email ? ` · ${row.email}` : row.phone ? ` · ${row.phone}` : ''}</option>)}
    </select>
    {searching && <p role="status" className="text-xs text-muted-foreground">{msg('FE_USER_PICKER_SEARCHING', 'Searching users…')}</p>}
    {error && <div role="alert" className="text-sm text-destructive"><p>{error}</p><button onClick={() => setRevision(value => value + 1)}>{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div>}
    {!searching && !error && term && !rows.length && <p className="text-xs text-muted-foreground">{msg('FE_USER_PICKER_EMPTY', 'No matching users in this scope. Try a full name or email.')}</p>}
  </div>;
}
