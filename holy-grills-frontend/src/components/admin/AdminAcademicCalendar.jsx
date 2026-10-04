import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Pencil, CalendarDays, Globe } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { formatDate } from '@/lib/hgUtils';
import { toast } from '@/components/ui/use-toast';
import { Card, Skeleton, EmptyState, Modal, Field, TextInput, Pill, body } from './ui/AdminKit';

const PERIOD_TYPES = [
  { value: 'semester', label: 'Semester' },
  { value: 'exam', label: 'Exam' },
  { value: 'break', label: 'Break' },
  { value: 'holiday', label: 'Holiday' },
  { value: 'orientation', label: 'Orientation' },
];

const fmt = (d) => (d ? formatDate(d) : '—');
const sortEntry = (e) => (e.start_date || e.end_date || e.created_date || '');

export default function AdminAcademicCalendar() {
  const [periods, setPeriods] = useState(null);
  const [campuses, setCampuses] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    try {
      const list = await liveApi.admin.getAcademicCalendar();
      setPeriods([...(list || [])].sort((a, b) => new Date(sortEntry(b)) - new Date(sortEntry(a))));
    } catch (e) {
      toast({ title: "Couldn't load academic calendar", description: e.message, variant: 'destructive' });
      setPeriods([]);
    }
  };

  useEffect(() => {
    load();
    liveApi.admin.getCampuses().then(setCampuses).catch(() => setCampuses([]));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <CalendarDays className="w-4 h-4 text-primary" /> {periods ? `${periods.length} period${periods.length === 1 ? '' : 's'}` : 'Loading…'}
        </div>
        <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold shadow-glow active:scale-95 transition">
          <Plus className="w-4 h-4" /> Add Period
        </button>
      </div>

      {periods == null ? (
        <div className="space-y-2.5">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      ) : periods.length === 0 ? (
        <Card>
          <EmptyState
            icon={CalendarDays}
            title="No academic calendar periods yet"
            body="Add semesters, exam weeks, breaks and holidays so students know what's coming up."
            action={
              <button onClick={() => setShowCreate(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-primary text-white text-xs font-bold active:scale-95 transition">
                <Plus className="w-3.5 h-3.5" /> Add the first period
              </button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-2.5">
          {periods.map((p, i) => {
            const campusName = p.campus_id ? (campuses.find((c) => c.id === p.campus_id)?.name || 'Campus') : null;
            return (
              <motion.div key={p.id || i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.2), duration: 0.25 }}>
                <Card className="p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-heading font-extrabold text-sm text-foreground truncate">{p.name}</div>
                      <div className="text-[11px] text-muted-foreground font-semibold uppercase tracking-wide">
                        {PERIOD_TYPES.find((t) => t.value === p.period_type)?.label || p.period_type}
                        {p.academic_year ? ` · ${p.academic_year}` : ''}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {campusName ? (
                        <Pill tone="outline">{campusName}</Pill>
                      ) : (
                        <Pill tone="outline"><Globe className="w-3 h-3" /> All Campuses</Pill>
                      )}
                      {p.is_active === false
                        ? <Pill tone="red">Retired</Pill>
                        : <Pill tone="green"><span className="w-1.5 h-1.5 rounded-full bg-success" /> Active</Pill>}
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground font-semibold">
                    <span>{fmt(p.start_date)} → {fmt(p.end_date)}</span>
                    <button
                      onClick={() => setEditing(p)}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-secondary text-secondary-foreground text-xs font-bold hover:bg-primary/10 hover:text-primary active:scale-95 transition"
                    >
                      <Pencil className="w-3 h-3" /> Edit
                    </button>
                  </div>
                  {p.description && <p className="text-[11px] text-muted-foreground leading-relaxed">{p.description}</p>}
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}

      {showCreate && <CalendarModal campuses={campuses} onClose={() => setShowCreate(false)} onSaved={load} />}
      {editing && <CalendarModal campuses={campuses} period={editing} onClose={() => setEditing(null)} onSaved={load} />}
    </div>
  );
}

const BLANK = {
  period_type: 'semester', name: '', start_date: '', end_date: '', academic_year: '', campus_id: '', description: '',
};

function CalendarModal({ period, campuses, onClose, onSaved }) {
  const [form, setForm] = useState(period ? {
    period_type: period.period_type || 'semester',
    name: period.name || '',
    start_date: period.start_date ? String(period.start_date).slice(0, 10) : '',
    end_date: period.end_date ? String(period.end_date).slice(0, 10) : '',
    academic_year: period.academic_year || '',
    campus_id: period.campus_id || '',
    description: period.description || '',
    is_active: period.is_active !== false,
  } : { ...BLANK });
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!form.name.trim()) { toast({ title: 'Name required', variant: 'destructive' }); return; }
    if (!period && !form.academic_year.trim()) { toast({ title: 'Academic year required', variant: 'destructive' }); return; }
    if (!form.start_date || !form.end_date) { toast({ title: 'Start and end dates required', variant: 'destructive' }); return; }
    setSubmitting(true);
    try {
      const payload = {
        period_type: form.period_type,
        name: form.name.trim(),
        start_date: form.start_date,
        end_date: form.end_date,
        academic_year: form.academic_year.trim() || null,
        description: form.description.trim() || null,
        // All Campuses = omit campus_id entirely (platform-wide period).
        ...(form.campus_id ? { campus_id: form.campus_id } : {}),
      };
      if (period) {
        await liveApi.admin.updateAcademicCalendar(period.id, { ...payload, is_active: form.is_active });
        toast({ title: 'Period updated', description: payload.name });
      } else {
        await liveApi.admin.createAcademicCalendar(payload);
        toast({ title: 'Period created', description: payload.name });
      }
      onClose(); onSaved();
    } catch (e) {
      toast({ title: 'Failed to save', description: e.message, variant: 'destructive' });
    }
    setSubmitting(false);
  };

  return (
    <Modal open onClose={onClose} title={period ? `Edit — ${period.name}` : 'Add Academic Period'}>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Period type">
            <select value={form.period_type} onChange={(e) => setForm({ ...form, period_type: e.target.value })} className="w-full mt-1 px-3 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40">
              {PERIOD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
          <Field label="Campus">
            <select value={form.campus_id} onChange={(e) => setForm({ ...form, campus_id: e.target.value })} className="w-full mt-1 px-3 py-2.5 rounded-xl border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40">
              <option value="">All Campuses</option>
              {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Name"><TextInput value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. First Semester 2024/2025" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start date"><TextInput type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
          <Field label="End date"><TextInput type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
        </div>
        <Field label="Academic year" hint='e.g. "2024-2025"'><TextInput value={form.academic_year} onChange={(e) => setForm({ ...form, academic_year: e.target.value })} placeholder="2024-2025" /></Field>
        <Field label="Description (optional)"><textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} placeholder="Notes about this period…" className="w-full mt-1 p-3 rounded-xl border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40" /></Field>
        {period && (
          <div className="flex items-center gap-2">
            <input type="checkbox" id="ac-active" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} className="w-4 h-4 accent-primary" />
            <label htmlFor="ac-active" className="text-sm text-foreground font-semibold">Active (uncheck to retire without deleting history)</label>
          </div>
        )}
        <button onClick={submit} disabled={submitting} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold active:scale-95 transition disabled:opacity-50">
          {submitting ? 'Saving…' : (period ? 'Save Changes' : 'Create Period')}
        </button>
      </div>
    </Modal>
  );
}