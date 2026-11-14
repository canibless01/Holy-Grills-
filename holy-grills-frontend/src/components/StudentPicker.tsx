import { useId } from 'react';
import { useStudentSearch } from '@/hooks/useStudentSearch';
import { displayName } from '@/lib/displayName';
import { msg } from '@/lib/messages';

export default function StudentPicker({ value, onChange, onSelect, onInvite, disabled = false }) {
  const id = useId();
  const { results, searching, searchError, hasSearched, retry } = useStudentSearch(value, !disabled);
  const email = value.trim().toLowerCase();
  const canInvite = onInvite && hasSearched && !searching && !searchError && !results.length && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  return <div className="space-y-2">
    <input role="combobox" aria-label={msg('FE_LOOKUP_STUDENT_LABEL', 'Find a campus student')} aria-expanded={results.length > 0} aria-controls={id} aria-autocomplete="list"
      value={value} disabled={disabled} onChange={e => onChange(e.target.value)}
      placeholder={msg('FE_LOOKUP_STUDENT_HINT', 'Search by name, nickname or email')}
      className="w-full px-3 py-2.5 rounded-xl border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/20" />
    {searching && <p role="status" className="text-xs text-muted-foreground">{msg('FE_LOOKUP_SEARCHING', 'Searching…')}</p>}
    {searchError && <button type="button" onClick={retry} className="text-xs text-destructive">{searchError} · {msg('FE_LOOKUP_RETRY', 'Retry')}</button>}
    {results.length > 0 && <div id={id} role="listbox" className="max-h-40 overflow-y-auto border border-border rounded-xl">
      {results.map(student => <button type="button" role="option" aria-selected="false" key={student.id} disabled={disabled} onClick={() => onSelect(student)} className="block w-full px-3 py-2.5 text-left text-sm hover:bg-muted">
        <span className="font-semibold">{displayName(student)}</span>{student.nickname && student.full_name && <span className="block text-xs text-muted-foreground">{student.full_name}</span>}
      </button>)}
    </div>}
    {hasSearched && !searching && !searchError && !results.length && <p className="text-xs text-muted-foreground">{msg('FE_LOOKUP_NO_STUDENTS', 'No matching campus students.')}</p>}
    {canInvite && <button type="button" disabled={disabled} onClick={() => onInvite(email)} className="px-3 py-2 rounded-full bg-primary text-primary-foreground text-xs font-bold">{msg('FE_LOOKUP_INVITE_EMAIL', 'Invite this email')}</button>}
  </div>;
}
