import { useState, useEffect } from 'react';
import AdminHp from './AdminHp';
import { useIsSuperAdmin, SuperAdminBadge } from './SuperAdminGate';
import { liveApi as mockApi } from '@/lib/liveApi';
import { Card, Pill, SectionHeader } from './AdminShared';
import { toast } from '@/components/ui/use-toast';
import LoadingSpinner from '@/components/LoadingSpinner';
import { msg } from '@/lib/messages';

// Unified "HP & Multipliers" page — everything HP-multiplier related in one
// place instead of spread across the HP panel and the Menu page:
//   1. The HP report + bulk/manual grants (reused from AdminHp).
//   2. Per-item HP multiplier controls (per-item, with ½× / 1× / 2× toggles).
//   3. The global HP multiplier system setting.
// "Rewards multiplier" and "flash-order multiplier" are intentionally absent —
// they don't exist on the backend, so we don't surface them.
export default function AdminHpMultipliers() {
  return (
    <div className="space-y-6">
      <AdminHp />
      <PerItemMultipliers />
      <GlobalMultiplier />
    </div>
  );
}

function PerItemMultipliers() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setLoading(true);
    try { setItems(await mockApi.admin.getMenuItems()); } catch { setItems([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const setMultiplier = async (id, multiplier, name) => {
    setBusy(id);
    try {
      await mockApi.admin.updateMenuItemHpMultiplier(id, { multiplier });
      toast({ title: msg('FE_ADMIN_HP_MULTIPLIERS_HP_MULTIPLIER_UPDATED', '✅ HP multiplier updated'), description: `${multiplier === 2 ? 'Double' : multiplier === 0.5 ? 'Half' : 'Normal'} HP earning for "${name}".` });
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_HP_MULTIPLIERS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (loading) return <LoadingSpinner label="Loading menu items..." />;

  const OPTS = [{ m: 0.5, l: '½×' }, { m: 1, l: '1×' }, { m: 2, l: '2×' }];

  return (
    <Card>
      <SectionHeader title="Per-Item HP Multipliers" action={<Pill tone="flame">menu</Pill>} />
      <p className="text-[11px] text-muted-foreground mb-3">Set how much HP each menu item earns. 2× doubles, ½ halves, 1× is normal.</p>
      <div className="space-y-2">
        {items.map((it) => (
          <div key={it.id} className="flex items-center gap-2 p-2.5 rounded-xl bg-muted">
            <div className="flex-1 min-w-0">
              <div className="font-bold text-sm text-foreground truncate">{it.name}</div>
              <div className="text-[11px] text-muted-foreground">{it.hp_earn_value} HP base · {it.menu_categories?.name || ''}</div>
            </div>
            <div className="flex gap-1">
              {OPTS.map((opt) => (
                <button
                  key={opt.m}
                  onClick={() => setMultiplier(it.id, opt.m, it.name)}
                  disabled={busy === it.id}
                  className={`px-2.5 py-1 rounded-full text-xs font-bold disabled:opacity-50 ${it.hp_multiplier === opt.m ? 'bg-primary text-white' : 'bg-white border border-border text-foreground'}`}
                >
                  {opt.l}
                </button>
              ))}
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No menu items yet.</p>}
      </div>
    </Card>
  );
}

function GlobalMultiplier() {
  const isSuperAdmin = useIsSuperAdmin();
  const [settings, setSettings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editKey, setEditKey] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [busy, setBusy] = useState(null);

  const load = async () => {
    setLoading(true);
    try { setSettings(await mockApi.admin.getSystemSettings()); } catch { setSettings([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const multiplierSettings = settings.filter((s) => /hp[_-]?multiplier/i.test(s.key || ''));

  const save = async (key, chosen) => {
    setBusy(key);
    let val = chosen != null ? chosen : editValue;
    if (typeof val !== 'number' && !isNaN(val) && val !== '') val = Number(val);
    try {
      await mockApi.admin.updateSystemSetting(key, { value: val });
      toast({ title: msg('FE_ADMIN_HP_MULTIPLIERS_GLOBAL_MULTIPLIER_SAVED', 'Global multiplier saved') });
      setEditKey(null);
      await load();
    } catch (e) { toast({ title: msg('FE_ADMIN_HP_MULTIPLIERS_FAILED', 'Failed'), description: e.message, variant: 'destructive' }); }
    setBusy(null);
  };

  if (loading) return <LoadingSpinner label="Loading settings..." />;

  return (
    <Card>
      <SectionHeader title="Global HP Multiplier" action={<Pill tone="cocoa">system</Pill>} />
      <p className="text-[11px] text-muted-foreground mb-3">Site-wide HP earn multiplier (system setting). Setting it above 1.0 immediately notifies all active users — the backend sends that announcement automatically.</p>
      {multiplierSettings.length === 0 ? (
        <div className="text-xs text-muted-foreground">No global HP multiplier setting found on the backend yet. Manage all settings under Settings → System Settings.</div>
      ) : multiplierSettings.map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-muted">
          <div className="min-w-0">
            <div className="font-mono text-xs font-bold text-foreground">{s.key}</div>
            <div className="text-[11px] text-muted-foreground truncate">{s.description || ''}</div>
          </div>
          {editKey === s.key ? (
            // Backend accepts only 0.5, 1.0 or 2.0 — fixed choices, no free number.
            <div className="flex gap-1.5 shrink-0">
              {[0.5, 1, 2].map((m) => (
                <button key={m} onClick={() => save(s.key, m)} disabled={busy === s.key} className={`px-2.5 py-1 rounded-lg text-xs font-bold disabled:opacity-50 ${Number(s.value) === m ? 'bg-primary text-white' : 'bg-secondary text-secondary-foreground'}`}>{m}×</button>
              ))}
              <button onClick={() => setEditKey(null)} className="px-3 py-1 rounded-lg bg-secondary text-muted-foreground text-xs font-bold">Cancel</button>
            </div>
          ) : (
            <div className="flex items-center gap-2 shrink-0">
              <span className="font-bold text-sm text-foreground">{String(s.value)}</span>
              {isSuperAdmin ? (
                <button onClick={() => { setEditKey(s.key); setEditValue(String(s.value)); }} className="px-3 py-1 rounded-lg bg-secondary text-muted-foreground text-xs font-bold">Edit</button>
              ) : (
                <SuperAdminBadge />
              )}
            </div>
          )}
        </div>
      ))}
    </Card>
  );
}