import React, { useState, useEffect } from 'react';
import { Send, Bell, Calendar, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { timeAgo } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Field, TextInput, Card, Toggle, Modal } from './AdminShared';
import { Pill } from './ui/AdminKit';
import { toast } from '@/components/ui/use-toast';
import type { NotificationBlastPayload } from '@/types/notifications';

const ROLES = [
  { id: 'all', label: 'All roles' },
  { id: 'student', label: 'Students' },
  { id: 'admin', label: 'Admins' },
  { id: 'kitchen', label: 'Kitchen staff' },
  { id: 'rider', label: 'Riders' },
];

const TIERS = [
  { id: 'all', label: 'All tiers' },
  { id: 'ember', label: 'Ember' },
  { id: 'flame', label: 'Flame' },
  { id: 'blaze', label: 'Blaze' },
  { id: 'holy', label: 'Holy' },
];

const CHANNELS = [
  { id: 'in_app', label: 'In-App' },
  { id: 'push', label: 'Push' },
  { id: 'email', label: 'Email' },
];

const STATUS_STYLE = {
  sent: { tone: 'green', icon: CheckCircle2, label: 'Sent' },
  scheduled: { tone: 'amber', icon: Clock, label: 'Scheduled' },
  pending: { tone: 'cocoa', icon: AlertCircle, label: 'Pending' },
};

export default function AdminNotifications() {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [channels, setChannels] = useState(['push', 'in_app']);
  const [role, setRole] = useState('all');
  const [tier, setTier] = useState('all');
  const [sendAt, setSendAt] = useState(''); // datetime-local string, '' = immediate
  const [emailProvider, setEmailProvider] = useState('default');
  const [notifyNewMatchesOnly, setNotifyNewMatchesOnly] = useState(false);
  const [sending, setSending] = useState(false);
  const [blasts, setBlasts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setBlasts(await mockApi.admin.getNotificationBlasts()); }
    catch { setBlasts([]); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const toggleChannel = (id, checked) => setChannels(checked ? [...channels, id] : channels.filter((x) => x !== id));
  const valid = title.trim() && body.trim() && channels.length > 0;
  const isScheduled = !!sendAt;

  const buildPayload = () => {
    const payload: NotificationBlastPayload = { title: title.trim(), body: body.trim(), channels };
    // Segment builder — always send target_segment; "all" means no filtering.
    const segment = { role, tier, campus_id: 'all' };
    payload.target_segment = segment;
    // Keep legacy `segment` key for backward compat with the existing backend.
    if (role !== 'all' || tier !== 'all') payload.segment = segment;
    if (emailProvider !== 'default') payload.email_provider = emailProvider;
    payload.notify_new_matches_only = notifyNewMatchesOnly;
    // Only include send_at when a date/time is set — omitting it means "now".
    if (sendAt) {
      const d = new Date(sendAt);
      payload.send_at = d.toISOString();
    }
    return payload;
  };

  const doSend = async () => {
    setSending(true);
    try {
      const res = await mockApi.admin.sendNotificationBlast(buildPayload());
      if (isScheduled) {
        toast({ title: '📅 Campaign scheduled', description: `Will send on ${new Date(sendAt).toLocaleString()}` });
      } else {
        const sentTo = res?.sent_to ?? res?.recipients ?? res?.recipient_count;
        toast({ title: '🔔 Campaign sent', description: sentTo != null ? `Delivered to ${sentTo} recipients` : 'Blast sent successfully' });
      }
      setTitle(''); setBody(''); setSendAt(''); setRole('all'); setTier('all');
      setConfirmOpen(false);
      await load();
    } catch (e) {
      toast({ title: 'Failed to send', description: e.message, variant: 'destructive' });
      setConfirmOpen(false);
    }
    setSending(false);
  };

  const handleSubmit = () => {
    if (!valid) { toast({ title: 'Missing fields', description: 'Title, body and at least one channel are required.', variant: 'destructive' }); return; }
    // Immediate sends get a confirm dialog so an admin doesn't fire a blast
    // by accident while previewing. Scheduled sends don't need one — the
    // date picker is the explicit intent.
    if (!isScheduled) setConfirmOpen(true);
    else doSend();
  };

  return (
    <div className="space-y-4">
      {/* New Campaign */}
      <Card>
        <h3 className="font-bold text-sm text-foreground mb-3 flex items-center gap-2">
          <Bell className="w-4 h-4 text-primary" /> New Campaign
        </h3>
        <div className="space-y-3">
          <Field label="Title (required)">
            <TextInput value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. New menu drop is live 🔥" />
          </Field>
          <Field label="Body (required)">
            <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40" placeholder="Write the notification message..." />
          </Field>

          {/* Segment builder — role + tier */}
          <Field label="Target Segment" hint="Filter who receives this campaign. Defaults to everyone.">
            <div className="grid grid-cols-2 gap-2 mt-1">
              <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm bg-card">
                {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
              <select value={tier} onChange={(e) => setTier(e.target.value)} className="w-full p-2.5 rounded-xl border border-border text-sm bg-card">
                {TIERS.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
              </select>
            </div>
          </Field>

          <Field label="Channels (at least one required)" hint="Push = mobile notification, In-App = the notifications inbox, Email = email to registered users.">
            <div className="flex gap-4 mt-1 flex-wrap">
              {CHANNELS.map((c) => (
                <label key={c.id} className="flex items-center gap-1.5 text-sm text-foreground font-semibold">
                  <input type="checkbox" checked={channels.includes(c.id)} onChange={(e) => toggleChannel(c.id, e.target.checked)} />
                  {c.label}
                </label>
              ))}
            </div>
          </Field>

          {/* Schedule — optional. Empty = send now. */}
          <Field label="Schedule (optional)" hint="Leave empty to send immediately. Pick a date & time to schedule for later.">
            <div className="flex items-center gap-2 mt-1">
              <Calendar className="w-4 h-4 text-muted-foreground shrink-0" />
              <input
                type="datetime-local"
                value={sendAt}
                onChange={(e) => setSendAt(e.target.value)}
                className="flex-1 p-2.5 rounded-xl border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              {sendAt && (
                <button onClick={() => setSendAt('')} className="text-xs font-bold text-destructive hover:underline shrink-0">
                  Clear
                </button>
              )}
            </div>
          </Field>

          <Field label="Email provider (optional)" hint="Most admins never touch this — the default follows your admin settings.">
            <select value={emailProvider} onChange={(e) => setEmailProvider(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
              <option value="default">Use default</option>
              <option value="resend">Resend</option>
              <option value="onesignal">OneSignal</option>
            </select>
          </Field>

          {(role !== 'all' || tier !== 'all') && (
            <div className="rounded-2xl border border-border p-3 bg-muted/50 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <span className="text-sm font-bold text-foreground">Only notify new matches</span>
                <p className="text-[11px] text-muted-foreground mt-1">Won't re-notify someone who already got this campaign — ideal for recurring segment sends.</p>
              </div>
              <Toggle checked={notifyNewMatchesOnly} onChange={setNotifyNewMatchesOnly} />
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={sending || !valid}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
            {sending ? 'Sending...' : isScheduled ? 'Schedule Campaign' : 'Send Blast Now'}
          </button>
        </div>
      </Card>

      {/* Recent blasts */}
      <div>
        <h3 className="font-bold text-sm text-foreground mb-2">Recent Campaigns</h3>
        {loading ? <LoadingSpinner label="Loading..." /> : blasts.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No campaigns sent yet.</p>
        ) : (
          <div className="space-y-2">
            {blasts.map((b) => {
              const status = b.status || (b.send_at && new Date(b.send_at) > new Date() ? 'scheduled' : 'sent');
              const st = STATUS_STYLE[status] || STATUS_STYLE.pending;
              const StIcon = st.icon;
              return (
                <div key={b.id} className="rounded-2xl bg-white border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-foreground truncate">{b.title}</span>
                    <Pill tone={st.tone}><StIcon className="w-2.5 h-2.5" /> {st.label}</Pill>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{b.body}</p>
                  <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground font-bold flex-wrap">
                    {(b.scheduled_at || b.send_at) && <span className="flex items-center gap-0.5"><Clock className="w-2.5 h-2.5" /> {new Date(b.scheduled_at || b.send_at).toLocaleString()}</span>}
                    <span>{Array.isArray(b.channels) ? b.channels.join(', ') : '—'}</span>
                    {b.recipients != null && <span>· {b.recipients} recipients</span>}
                    {!(b.scheduled_at || b.send_at) && <span>· {timeAgo(b.sent_at || b.created_at)}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Immediate-send confirm dialog */}
      <Modal open={confirmOpen} onClose={() => !sending && setConfirmOpen(false)} title="Send to everyone now?">
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This campaign will go out <strong className="text-foreground">immediately</strong> to
            {' '}{role === 'all' && tier === 'all' ? 'all users' : 'the selected segment'}.
            {channels.includes('push') && ' A push notification will be sent.'}
            {channels.includes('email') && ' An email will be sent.'}
          </p>
          <div className="rounded-xl bg-secondary/50 border border-border p-3">
            <div className="text-xs font-bold text-foreground">{title}</div>
            <div className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">{body}</div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setConfirmOpen(false)}
              disabled={sending}
              className="flex-1 py-2.5 rounded-full border border-border text-sm font-bold text-foreground hover:bg-secondary transition disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={doSend}
              disabled={sending}
              className="flex-1 py-2.5 rounded-full bg-gradient-cta text-white text-sm font-bold disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Confirm & Send'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}