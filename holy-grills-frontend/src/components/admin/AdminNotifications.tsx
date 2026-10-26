import { useState, useEffect } from 'react';
import { Send, Bell, Calendar, Clock, CheckCircle2, AlertCircle, Eye, Mail, Image as ImageIcon, TrendingUp } from 'lucide-react';
import { liveApi as mockApi } from '@/lib/liveApi';
import { timeAgo } from '@/lib/hgUtils';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Field, TextInput, Card, Modal } from './AdminShared';
import { Pill } from './ui/AdminKit';
import { toast } from '@/components/ui/use-toast';
import type { NotificationBlastPayload } from '@/types/notifications';
import { msg } from '@/lib/messages';
import { useCmsCreateIntent } from '@/lib/useCmsCreateIntent';
import { apiClient } from '@/lib/apiClient';
import RichTextEditor from './RichTextEditor';
import CTABlockEditor, { type CTABlock } from './CTABlockEditor';
import ImageStackEditor, { type ImageBlock } from './ImageStackEditor';
import EmailPreviewModal from './EmailPreviewModal';
import BlastAnalyticsModal from './BlastAnalyticsModal';
import { useHolyGrill } from '@/lib/HolyGrillContext';

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
  sent: { tone: 'green', icon: CheckCircle2, label: msg('FE_BLAST_PROCESSED', 'Processed') },
  scheduled: { tone: 'amber', icon: Clock, label: 'Scheduled' },
  pending: { tone: 'cocoa', icon: AlertCircle, label: 'Pending' },
};

export default function AdminNotifications() {
  const { user } = useHolyGrill();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [images, setImages] = useState<ImageBlock[]>([]);
  const [ctaBlocks, setCtaBlocks] = useState<CTABlock[]>([]);
  const [channels, setChannels] = useState(['push', 'in_app']);
  const [role, setRole] = useState('all');
  const [tier, setTier] = useState('all');
  const [sendAt, setSendAt] = useState(''); // datetime-local string, '' = immediate
  const [actionUrl, setActionUrl] = useState('');
  const [emailProvider, setEmailProvider] = useState('default');
  const [sending, setSending] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);
  const [blasts, setBlasts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const intent = useCmsCreateIntent();
  const [previewCount, setPreviewCount] = useState(null);
  const [pushImage, setPushImage] = useState(''); // Image for push/in-app notifications
  const [trackingEnabled, setTrackingEnabled] = useState(false); // Enable open/click tracking
  const [selectedBlastAnalytics, setSelectedBlastAnalytics] = useState(null); // Analytics data for selected blast
  const [analyticsBlastId, setAnalyticsBlastId] = useState<string | null>(null); // Blast ID for analytics modal
  const [analyticsBlastTitle, setAnalyticsBlastTitle] = useState<string>(''); // Blast title for analytics modal
  const preview = async () => {
    try { const result = await apiClient.post('/notifications/blasts/preview', buildPayload()); setPreviewCount(result.recipient_count); }
    catch { toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), variant: 'destructive' }); }
  };
  const cancelCampaign = async (id) => {
    try { await apiClient.post(`/notifications/blasts/${id}/cancel`, {}); await load(); }
    catch (e) { toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: e.message, variant: 'destructive' }); }
  };
  const retryCampaign = async (id) => {
    try { await apiClient.post(`/notifications/blasts/${id}/retry`, {}); await load(); }
    catch (e) { toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: e.message, variant: 'destructive' }); }
  };
  useEffect(() => { setPreviewCount(null); }, [role, tier]);

  const load = async () => {
    setLoading(true);
    setLoadError(false);
    try { setBlasts(await mockApi.admin.getNotificationBlasts()); }
    catch { setLoadError(true); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const toggleChannel = (id, checked) => setChannels(checked ? [...channels, id] : channels.filter((x) => x !== id));
  const valid = title.trim() && (body.trim() || bodyHtml.trim()) && channels.length > 0;
  const isScheduled = !!sendAt;

  const buildPayload = () => {
    const payload: NotificationBlastPayload = { title: title.trim(), body: body.trim(), channels };
    if (actionUrl.trim()) payload.action_url = actionUrl.trim();
    // Segment builder — always send target_segment; "all" means no filtering.
    const segment = { role, tier };
    payload.target_segment = segment;
    if (emailProvider !== 'default') payload.email_provider = emailProvider;
    // Keep legacy `segment` key for backward compat with the existing backend.
    if (role !== 'all' || tier !== 'all') payload.segment = segment;
    // Only include send_at when a date/time is set — omitting it means "now".
    if (sendAt) {
      const d = new Date(sendAt);
      payload.send_at = d.toISOString();
    }
    // Add rich content fields
    if (bodyHtml.trim()) payload.body_html = bodyHtml.trim();
    if (images.length > 0) payload.images = images;
    if (ctaBlocks.length > 0) payload.cta_blocks = ctaBlocks;
    if (pushImage.trim()) payload.push_image = pushImage.trim();
    if (trackingEnabled) payload.tracking_enabled = trackingEnabled;
    return payload;
  };

  const doSend = async () => {
    setSending(true);
    try {
      const res = await mockApi.admin.sendNotificationBlast(intent.body(buildPayload()));
      if (res?.already_created && ['pending', 'sending', 'failed'].includes(res?.blast?.status)) {
        toast({ title: msg('FE_BLAST_EXISTS_PENDING', 'This campaign is already saved. Check its history entry to review progress or retry.') });
        setConfirmOpen(false);
        await load();
        setSending(false);
        return;
      }
      intent.clear();
      if (isScheduled) {
        toast({ title: msg('FE_ADMIN_NOTIFICATIONS_CAMPAIGN_SCHEDULED', '📅 Campaign scheduled'), description: msg('FE_ADMIN_NOTIFICATIONS_WILL_SEND_ON_DATE', 'Will send on {date}', { date: new Date(sendAt).toLocaleString() }) });
      } else {
        const sentTo = res?.sent_to ?? res?.recipients ?? res?.recipient_count;
        toast({ title: msg('FE_BLAST_PROCESSED', 'Processed'), description: sentTo != null ? msg('FE_BLAST_PROCESSED_RECIPIENTS', 'Campaign processed for {count} recipients.', { count: sentTo }) : undefined });
      }
      // Reset form
      setTitle(''); setBody(''); setBodyHtml(''); setImages([]); setCtaBlocks([]); setSendAt(''); setRole('all'); setTier('all'); setActionUrl(''); setPushImage('');
      setConfirmOpen(false);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_NOTIFICATIONS_FAILED_TO_SEND', 'Failed to send'), description: e.message, variant: 'destructive' });
      setConfirmOpen(false);
      await load();
    }
    setSending(false);
  };

  const sendTest = async () => {
    if (!user?.email) {
      toast({ title: 'Cannot send test', description: 'Your email address is not available.', variant: 'destructive' });
      return;
    }
    setSendingTest(true);
    try {
      await apiClient.post('/notifications/blasts/test', {
        ...buildPayload(),
        test_email: user.email,
      });
      toast({ title: '✅ Test sent', description: `Test notification sent to ${user.email}` });
    } catch (e) {
      toast({ title: 'Failed to send test', description: e.message, variant: 'destructive' });
    }
    setSendingTest(false);
  };

  const testDeliverability = async () => {
    // Prompt user for spam testing service email (e.g., mail-tester.com)
    const testEmail = prompt(
      'Enter the email address from your spam testing service:\n\n' +
      'Popular options:\n' +
      '• Mail-Tester.com (get unique email from their site)\n' +
      '• GlockApps.com\n' +
      '• Litmus.com\n\n' +
      'The test email will be sent to this address for spam scoring.'
    );
    
    if (!testEmail) return;
    
    setSendingTest(true);
    try {
      const result = await apiClient.post('/notifications/blasts/test-deliverability', {
        test_email: testEmail,
        title: title.trim(),
        body: body.trim() || bodyHtml.trim(),
      });
      
      toast({
        title: '✅ Deliverability test sent',
        description: result.message,
      });
      
      // Show recommendations
      if (result.recommendations && result.recommendations.length > 0) {
        alert(
          'Email sent! Check your spam testing service for results.\n\n' +
          'Deliverability Best Practices:\n\n' +
          result.recommendations.map((r, i) => `${i + 1}. ${r}`).join('\n')
        );
      }
    } catch (e) {
      toast({ title: 'Failed to send test', description: e.message, variant: 'destructive' });
    }
    setSendingTest(false);
  };

  const handleSubmit = () => {
    if (!valid) { toast({ title: msg('FE_ADMIN_NOTIFICATIONS_MISSING_FIELDS', 'Missing fields'), description: msg('FE_ADMIN_NOTIFICATIONS_TITLE_BODY_AND_AT_LEAST_ONE_CHANNEL_ARE', 'Title, body and at least one channel are required.'), variant: 'destructive' }); return; }
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
            <RichTextEditor
              value={bodyHtml}
              onChange={setBodyHtml}
              placeholder="Write your notification message with rich formatting..."
            />
            {/* Keep plain text body for backward compatibility */}
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={2}
              className="w-full mt-2 p-2.5 rounded-xl border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
              placeholder="Plain text fallback (auto-generated from rich text if empty)"
            />
          </Field>

          {/* Image Stack */}
          <ImageStackEditor value={images} onChange={setImages} />

          {/* CTA Blocks */}
          <CTABlockEditor value={ctaBlocks} onChange={setCtaBlocks} />

          {/* Push/In-App Image */}
          <Field label="Push/In-App Image (optional)" hint="Image to show in push notifications and in-app notifications">
            <div className="flex items-center gap-2 mt-1">
              <ImageIcon className="w-4 h-4 text-muted-foreground" />
              <input
                type="url"
                value={pushImage}
                onChange={(e) => setPushImage(e.target.value)}
                placeholder="https://example.com/push-image.jpg"
                className="flex-1 p-2.5 rounded-xl border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
            {pushImage && (
              <div className="mt-2 rounded-lg overflow-hidden border border-border">
                <img src={pushImage} alt="Push preview" className="w-full h-auto max-h-32 object-cover" />
              </div>
            )}
          </Field>

          {/* Email Tracking Toggle */}
          {channels.includes('email') && (
            <Field label="Email Analytics" hint="Track opens and clicks for this email blast">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={trackingEnabled}
                  onChange={(e) => setTrackingEnabled(e.target.checked)}
                  className="w-5 h-5 rounded border-border text-primary focus:ring-primary/40"
                />
                <div>
                  <div className="text-sm font-medium text-foreground">Enable open & click tracking</div>
                  <div className="text-xs text-muted-foreground">Track how many recipients open the email and click links</div>
                </div>
              </label>
            </Field>
          )}

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

          <Field label={msg('FE_BLAST_LINK', 'Destination path (optional)')}><TextInput value={actionUrl} onChange={e => setActionUrl(e.target.value)} placeholder="/events" /></Field>
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

          <Field label={msg('FE_BLAST_EMAIL_PROVIDER', 'Email provider')}>
            <select value={emailProvider} onChange={e => setEmailProvider(e.target.value)} className="w-full mt-1 p-2.5 rounded-xl border border-border text-sm bg-card">
              <option value="default">{msg('FE_BLAST_USE_DEFAULT', 'Use default')}</option><option value="resend">Resend</option><option value="onesignal">OneSignal</option>
            </select>
          </Field>

          <div className="flex gap-2">
            <button
              onClick={() => setPreviewOpen(true)}
              disabled={!title.trim() && !bodyHtml.trim()}
              className="flex-1 py-3 rounded-full border border-border text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 hover:bg-secondary transition"
            >
              <Eye className="w-4 h-4" />
              Preview
            </button>
            <button
              onClick={sendTest}
              disabled={sendingTest || (!title.trim() && !bodyHtml.trim())}
              className="flex-1 py-3 rounded-full border border-primary text-primary font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 hover:bg-primary/10 transition"
            >
              <Mail className="w-4 h-4" />
              {sendingTest ? 'Sending...' : 'Test to Me'}
            </button>
            <button
              onClick={testDeliverability}
              disabled={sendingTest || (!title.trim() && !bodyHtml.trim())}
              className="flex-1 py-3 rounded-full border border-amber-500 text-amber-500 font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 hover:bg-amber-500/10 transition"
              title="Test email deliverability (send to spam testing service)"
            >
              <AlertCircle className="w-4 h-4" />
              Spam Test
            </button>
          </div>

          <button
            onClick={handleSubmit}
            disabled={sending || !valid}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
            {sending ? 'Sending...' : isScheduled ? 'Schedule Campaign' : 'Send Blast Now'}
          </button>
          <button onClick={preview} className="text-primary font-bold text-sm">{msg('FE_BLAST_PREVIEW', 'Preview recipients')}</button>
          {previewCount !== null && <p className="text-sm">{msg('FE_BLAST_AUDIENCE_COUNT', '{count} recipients in this audience.', { count: previewCount })}</p>}
        </div>
      </Card>

      {/* Recent blasts */}
      <div>
        <h3 className="font-bold text-sm text-foreground mb-2">Recent Campaigns</h3>
        {loading ? <LoadingSpinner label="Loading..." /> : loadError ? <div className="space-y-2"><p>{msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again.")}</p><button onClick={load} className="text-primary font-bold">{msg('FE_PLATFORM_RETRY', 'Retry')}</button></div> : blasts.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">No campaigns sent yet.</p>
        ) : (
          <div className="space-y-2">
            {blasts.map((b) => {
              const status = b.status || (b.send_at && new Date(b.send_at) > new Date() ? 'scheduled' : 'sent');
              const st = STATUS_STYLE[status] || STATUS_STYLE.pending;
              const StIcon = st.icon;
              const hasTracking = b.tracking_enabled && b.channels?.includes('email') && status === 'sent';
              return (
                <div key={b.id} className="rounded-2xl bg-card border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-sm text-foreground truncate">{b.title}</span>
                    <div className="flex items-center gap-2">
                      {hasTracking && (
                        <button
                          onClick={() => {
                            setAnalyticsBlastId(b.id);
                            setAnalyticsBlastTitle(b.title);
                          }}
                          className="px-2 py-1 rounded-lg bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 transition flex items-center gap-1"
                          title="View analytics"
                        >
                          <TrendingUp className="w-3 h-3" />
                          Analytics
                        </button>
                      )}
                      <Pill tone={st.tone}><StIcon className="w-2.5 h-2.5" /> {st.label}</Pill>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{b.body}</p>
                  {['pending', 'scheduled'].includes(b.status) && <button onClick={() => cancelCampaign(b.id)} className="text-destructive font-bold text-xs">{msg('FE_BLAST_CANCEL', 'Cancel campaign')}</button>}
                  {['failed', 'sending'].includes(b.status) && <button onClick={() => retryCampaign(b.id)} className="text-primary font-bold text-xs">{msg('FE_BLAST_RETRY', 'Retry campaign')}</button>}
                  {b.metadata?.processed_count != null && <p className="text-xs">{msg('FE_BLAST_PROCESSED_RECIPIENTS', 'Campaign processed for {count} recipients.', { count: b.metadata.processed_count })}</p>}
                  {b.metadata?.notification_records != null && <p className="text-xs">{msg('FE_BLAST_STORED_RECORDS', '{count} notification records stored', { count: b.metadata.notification_records })}</p>}
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

      {/* Email Preview Modal */}
      <EmailPreviewModal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title={title}
        bodyHtml={bodyHtml}
        images={images}
        ctaBlocks={ctaBlocks}
      />

      {/* Blast Analytics Modal */}
      <BlastAnalyticsModal
        open={!!analyticsBlastId}
        onClose={() => {
          setAnalyticsBlastId(null);
          setAnalyticsBlastTitle('');
        }}
        blastId={analyticsBlastId || ''}
        blastTitle={analyticsBlastTitle}
      />

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
