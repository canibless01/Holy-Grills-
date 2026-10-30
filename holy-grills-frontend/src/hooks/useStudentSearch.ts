import { useEffect, useState } from 'react';
import { liveApi } from '@/lib/liveApi';

/** Campus-scoped suggestions. Ignore responses for queries that have changed. */
export function useStudentSearch(query: string, enabled = true) {
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [revision, setRevision] = useState(0);
  const [settledQuery, setSettledQuery] = useState('');
  const term = query.trim();
  useEffect(() => {
    let active = true;
    setResults([]); setSearchError(''); setSettledQuery('');
    if (!enabled || !term) { setSearching(false); return; }
    setSearching(true);
    const timer = setTimeout(async () => {
      try {
        const rows = await liveApi.users.search({ q: term });
        if (active) setResults(Array.isArray(rows) ? rows : []);
      } catch (failure) {
        if (active) setSearchError(failure.message || 'Student search is unavailable. Please retry.');
      } finally { if (active) { setSearching(false); setSettledQuery(term); } }
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [query, enabled, revision]);
  return { results: settledQuery === term ? results : [], searching: enabled && !!term && (searching || settledQuery !== term), searchError, hasSearched: !!term && settledQuery === term, retry: () => setRevision((value) => value + 1) };
}
