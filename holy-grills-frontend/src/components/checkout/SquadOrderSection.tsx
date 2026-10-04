import React, { useState, useEffect } from 'react';
import { Users, ChevronDown, X, Plus, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';

/**
 * SquadOrderSection — checkout squad tagging.
 *
 * Lets the shopper tag this order to one of their squads regardless of item
 * count, exclude specific roster members from this one order (the roster
 * itself is untouched), and add extra one-off emails for this order only.
 *
 * Reports the selection up via onChange:
 *   { squad_id, excluded_member_ids: [...], extra_members: [...] }
 * or null when no squad is selected.
 */
export default function SquadOrderSection({ value, onChange }) {
  const [squads, setSquads] = useState([]);
  const [roster, setRoster] = useState([]);
  const [loadingRoster, setLoadingRoster] = useState(false);
  const [extraInput, setExtraInput] = useState('');

  useEffect(() => {
    liveApi.squads.list()
      .then((list) => setSquads(Array.isArray(list) ? list : []))
      .catch(() => {});
  }, []);

  // If a squad was already tagged in the cart, pre-load its roster so the
  // exclude/extra controls show immediately without re-tapping the select.
  useEffect(() => {
    if (!value?.squad_id) return;
    setLoadingRoster(true);
    liveApi.squads.get(value.squad_id)
      .then((detail) => setRoster((detail?.roster || []).filter((m) => m.is_active !== false)))
      .catch(() => {})
      .finally(() => setLoadingRoster(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelect = async (id) => {
    setRoster([]);
    if (!id) { onChange(null); return; }
    onChange({ squad_id: id, excluded_member_ids: [], extra_members: [] });
    setLoadingRoster(true);
    try {
      const detail = await liveApi.squads.get(id);
      setRoster((detail?.roster || []).filter((m) => m.is_active !== false));
    } catch { /* roster optional — the order can still be tagged */ }
    setLoadingRoster(false);
  };

  const toggleExcluded = (rowId) => {
    if (!value) return;
    const ex = value.excluded_member_ids || [];
    onChange({
      ...value,
      excluded_member_ids: ex.includes(rowId) ? ex.filter((x) => x !== rowId) : [...ex, rowId],
    });
  };

  const addExtra = () => {
    const email = extraInput.trim().toLowerCase();
    if (!value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return;
    if (!(value.extra_members || []).includes(email)) {
      onChange({ ...value, extra_members: [...(value.extra_members || []), email] });
    }
    setExtraInput('');
  };

  const removeExtra = (email) => {
    if (!value) return;
    onChange({ ...value, extra_members: (value.extra_members || []).filter((e) => e !== email) });
  };

  if (!squads.length) return null;

  return (
    <div className="hg-card">
      <h3 className="hg-section-title mb-1 flex items-center gap-2"><Users className="w-4 h-4 text-primary" /> Squad order</h3>
      <p className="text-[11px] text-muted-foreground mb-3">Tag this order to a squad — HP splits across the crew. You can also do this without tagging from the squads page.</p>

      <div className="relative">
        <select
          value={value?.squad_id || ''}
          onChange={(e) => handleSelect(e.target.value)}
          className="w-full px-3.5 py-3 rounded-xl bg-card border border-border text-sm text-foreground focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition appearance-none"
        >
          <option value="">No squad — regular order</option>
          {squads.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
      </div>

      {value?.squad_id && (
        <div className="mt-3 space-y-3 animate-fade-in">
          {loadingRoster ? (
            <div className="flex items-center justify-center py-3">
              <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />
            </div>
          ) : roster.length > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">
                Tap a member to leave them out of this order
              </div>
              <div className="flex flex-wrap gap-1.5">
                {roster.map((m) => {
                  const excluded = (value.excluded_member_ids || []).includes(m.id);
                  return (
                    <button
                      key={m.id}
                      onClick={() => toggleExcluded(m.id)}
                      className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all ${excluded ? 'bg-muted text-muted-foreground border-border line-through opacity-60' : 'bg-primary/10 text-primary border-primary/30'}`}
                    >
                      {m.display_name || m.email}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <div className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-1.5">
              Extra members for this order only
            </div>
            <div className="flex gap-2">
              <input
                value={extraInput}
                onChange={(e) => setExtraInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addExtra(); } }}
                placeholder="walkon@campus.edu.ng"
                className="flex-1 px-3 py-2.5 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
              />
              <button onClick={addExtra} className="px-3 py-2.5 rounded-xl bg-card border border-border text-primary hover:border-primary/40 transition-colors shrink-0" aria-label="Add extra member">
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {(value.extra_members || []).length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {(value.extra_members || []).map((e) => (
                  <span key={e} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full bg-primary/10 text-primary border border-primary/30 text-xs font-semibold">
                    {e}
                    <button onClick={() => removeExtra(e)} aria-label={`Remove ${e}`}><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}