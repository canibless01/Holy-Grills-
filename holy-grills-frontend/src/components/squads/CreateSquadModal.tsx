import React, { useState } from 'react';
import { X, Users, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import ModalBackdrop from '@/components/ModalBackdrop';
import type { CreateSquadPayload } from '@/types/squads';

// Parse the free-form emails field into a clean list — accepts newlines,
// commas, and semicolons as separators.
const parseEmails = (raw = '') =>
  Array.from(new Set(
    raw.split(/[\n,;]+/).map((e) => e.trim().toLowerCase()).filter((e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e))
  ));

export default function CreateSquadModal({ open, onClose, onCreated }) {
  const [name, setName] = useState('');
  const [emails, setEmails] = useState('');
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!name.trim()) { setError('Give your squad a name.'); return; }
    const list = parseEmails(emails);
    setCreating(true);
    try {
      const body: CreateSquadPayload = { name: name.trim() };
      if (list.length) body.emails = list;
      await liveApi.squads.create(body);
      toast({ title: '🔥 Squad created', description: list.length ? `Invites are on their way to ${list.length} friend${list.length !== 1 ? 's' : ''}.` : 'Add members from the squad page anytime.' });
      setName(''); setEmails('');
      onCreated();
    } catch (err) {
      setError(err.message || 'Could not create the squad — try again.');
    }
    setCreating(false);
  };

  return (
    <ModalBackdrop onClose={() => !creating && onClose()}>
      <form onSubmit={handleSubmit} className="bg-card rounded-3xl p-6 w-full max-w-sm space-y-4 animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-dark flex items-center justify-center">
              <Users className="w-4 h-4 text-white" />
            </div>
            <h3 className="font-heading font-bold text-lg text-foreground">Create a squad</h3>
          </div>
          <button type="button" onClick={onClose} disabled={creating}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>

        <div>
          <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Squad name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Late Night Crew"
            maxLength={60}
            className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
          />
        </div>

        <div>
          <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Invite friends (optional)</label>
          <textarea
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
            placeholder={'friend1@campus.edu.ng\nfriend2@campus.edu.ng'}
            rows={3}
            className="w-full mt-1.5 p-3 rounded-xl border border-border text-sm resize-none focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all"
          />
          <p className="text-[11px] text-muted-foreground mt-1">
            {parseEmails(emails).length} email{parseEmails(emails).length !== 1 ? 's' : ''} — one per line, or separated by commas. Friends must be on the same campus.
          </p>
        </div>

        {error && (
          <div className="p-2.5 rounded-xl bg-destructive/10 border border-destructive/20">
            <span className="text-xs text-destructive font-semibold">{error}</span>
          </div>
        )}

        <button type="submit" disabled={creating} className="w-full py-3.5 rounded-xl bg-gradient-cta text-white font-bold shadow-glow disabled:opacity-60 flex items-center justify-center gap-2">
          {creating ? <><Loader2 className="w-4 h-4 animate-spin" /> Creating…</> : 'Create squad'}
        </button>
      </form>
    </ModalBackdrop>
  );
}