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
  const [audience, setAudience] = useState({ has_active_order: 'any', has_cart: 'any', last_order_days: 'any', last_login_days: 'any', hp_balance: 'all', total_orders: 'any', has_pending_hp: 'any', has_referral: 'any', has_reviewed: 'any', has_shared: 'any', has_squad_order: 'any', has_graduated: 'any', event_attendance: 'any', department: '', faculty: '', level: '' });
  const [recipientQuery, setRecipientQuery] = useState('');
  const [recipientResults, setRecipientResults] = useState<any[]>([]);
  const [selectedRecipients, setSelectedRecipients] = useState<any[]>([]);
  const [recipientError, setRecipientError] = useState(false);
  useEffect(() => {
    let active = true;
    setRecipientResults([]); setRecipientError(false);
    if (recipientQuery.trim().length < 2) return;
    const timer = setTimeout(() => {
      mockApi.admin.getUsers({ q: recipientQuery.trim(), limit: 10 })
        .then(rows => { if (active) setRecipientResults((rows || []).filter(person => person.is_active !== false)); })
        .catch(() => { if (active) setRecipientError(true); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [recipientQuery]);

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
  useEffect(() => { setPreviewCount(null); }, [role, tier, audience, selectedRecipients]);

  const load = async () => {
    setLoading(true);
    setLoadError(false);
    try { setBlasts(await mockApi.admin.getNotificationBlasts()); }
    catch { setLoadError(true); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const toggleChannel = (id, checked) => setChannels(checked ? [...channels, id] : channels.filter((x) => x !== id));
  const valid = title.trim() && (body.trim() || bodyHtml.replace(/<[^>]*>/g, ' ').trim()) && channels.length > 0 && (!recipientQuery.trim() || selectedRecipients.length > 0);
  const isScheduled = !!sendAt;

  const buildPayload = () => {
    const payload: NotificationBlastPayload = { title: title.trim(), body: body.trim(), channels };
    if (actionUrl.trim()) payload.action_url = actionUrl.trim();
    // Segment builder — always send target_segment; "all" means no filtering.
    const segment: Record<string, unknown> = { role, tier };
    Object.entries(audience).forEach(([key, value]) => {
      if (!value || value === 'all' || value === 'any') return;
      segment[key] = key.endsWith('_days') ? Number(value) : value === 'yes' ? true : value === 'no' ? false : value;
    });
    if (selectedRecipients.length) segment.user_ids = selectedRecipients.map(person => person.id);
    payload.target_segment = segment;
    if (emailProvider !== 'default') payload.email_provider = emailProvider;
    // Keep legacy `segment` key for backward compat with the existing backend.
    payload.segment = segment;
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
      setRecipientQuery(''); setSelectedRecipients([]);
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
        ...intent.body(buildPayload()),
        test_email: user.email,
      });
      intent.clear();
      toast({ title: '✅ Test sent', description: `Test notification sent to ${user.email}` });
    } catch (e) {
      toast({ title: 'Failed to send test', description: e.message, variant: 'destructive' });
    }
    setSendingTest(false);
  };

  const testDeliverability = async () => {
    // Prompt admin for email addresses to test with
    const testEmails = prompt(
      'Enter email addresses to test deliverability (comma-separated):\n\n' +
      'Examples:\n' +
      '• your-email@gmail.com (check your own inbox)\n' +
      '• staff1@gmail.com, staff2@yahoo.com (test multiple providers)\n' +
      '• test@hotmail.com, test@outlook.com (test Microsoft providers)\n\n' +
      'The email will be sent to these addresses. You can then check:\n' +
      '• Did it land in Primary or Spam?\n' +
      '• Did it arrive quickly?\n' +
      '• Does it render correctly?'
    );
    
    if (!testEmails) return;
    
    // Parse and validate email addresses
    const emails = testEmails.split(',').map(e => e.trim()).filter(e => e);
    
    if (emails.length === 0) {
      toast({ title: 'No valid emails', description: 'Please enter at least one email address.', variant: 'destructive' });
      return;
    }
    
    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const invalidEmails = emails.filter(e => !emailRegex.test(e));
    
    if (invalidEmails.length > 0) {
      toast({ 
        title: 'Invalid email addresses', 
        description: `Please check: ${invalidEmails.join(', ')}`, 
        variant: 'destructive' 
      });
      return;
    }
    
    setSendingTest(true);
    try {
      // Send test email to each address
      const results = await Promise.allSettled(
        emails.map(email => 
          apiClient.post('/notifications/blasts/test', {
            ...buildPayload(),
            test_email: email,
          })
        )
      );
      
      const successful = results.filter(r => r.status === 'fulfilled').length;
      const failed = results.filter(r => r.status === 'rejected').length;
      
      if (successful > 0) {
        toast({
          title: '✅ Test emails sent',
          description: `Sent to ${successful} address${successful > 1 ? 'es' : ''}. Check your inboxes to see where they land!${failed > 0 ? ` (${failed} failed)` : ''}`,
        });
        
        // Show helpful tips
        setTimeout(() => {
          alert(
            'Test emails sent! Now check the inboxes:\n\n' +
            'What to look for:\n' +
            '1. Primary vs Spam folder\n' +
            '2. How quickly it arrived\n' +
            '3. Does it render correctly?\n' +
            '4. Are links working?\n\n' +
            'Tips for better deliverability:\n' +
            '• Use a clear, non-spammy subject line\n' +
            '• Avoid excessive capitalization or exclamation marks\n' +
            '• Include a clear unsubscribe link for marketing emails\n' +
            '• Send from a consistent email address\n' +
            '• Keep your sender reputation good'
          );
        }, 500);
      } else {
        toast({ 
          title: 'Failed to send tests', 
          description: 'All test emails failed to send.', 
          variant: 'destructive' 
        });
      }
    } catch (e) {
      toast({ title: 'Failed to send tests', description: e.message, variant: 'destructive' });
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

          <div className="grid grid-cols-2 gap-2">
            {([
              ['has_active_order', msg('FE_BLAST_ACTIVE_ORDERS', 'Active orders')],
              ['has_cart', msg('FE_BLAST_HAS_CART', 'Items in cart')],
              ['has_pending_hp', msg('FE_BLAST_PENDING_HP', 'Pending HP')],
              ['has_referral', msg('FE_BLAST_REFERRALS', 'Has referred someone')],
              ['has_reviewed', msg('FE_BLAST_REVIEWS', 'Has reviewed an order')],
              ['has_shared', msg('FE_BLAST_SHARES', 'Has shared an order')],
              ['has_squad_order', msg('FE_BLAST_SQUAD', 'Has squad orders')],
              ['has_graduated', msg('FE_BLAST_GRADUATED', 'Graduation claimed')],
            ] as const).map(([key,label]) => <Field key={key} label={label}><select aria-label={label} value={audience[key]} onChange={e => setAudience({...audience,[key]:e.target.value})} className="w-full p-2.5 rounded-xl border border-border bg-card text-sm"><option value="any">{msg('FE_BLAST_ANY', 'Any')}</option><option value="yes">{msg('FE_BLAST_YES', 'Yes')}</option><option value="no">{msg('FE_BLAST_NO', 'No')}</option></select></Field>)}
            {(['last_order_days','last_login_days'] as const).map(key => <Field key={key} label={key==='last_order_days' ? msg('FE_BLAST_RECENT_ORDERS', 'Ordered within') : msg('FE_BLAST_RECENT_LOGIN', 'Visited within')}><select aria-label={key==='last_order_days' ? msg('FE_BLAST_RECENT_ORDERS', 'Ordered within') : msg('FE_BLAST_RECENT_LOGIN', 'Visited within')} value={audience[key]} onChange={e=>setAudience({...audience,[key]:e.target.value})} className="w-full p-2.5 rounded-xl border border-border bg-card text-sm"><option value="any">{msg('FE_BLAST_ANY', 'Any')}</option>{[1,7,30,90].map(days=><option key={days} value={days}>{msg('FE_BLAST_DAYS', '{days} days', {days})}</option>)}</select></Field>)}
            <Field label={msg('FE_BLAST_HP_BAND','HP balance')}><select aria-label={msg('FE_BLAST_HP_BAND','HP balance')} value={audience.hp_balance} onChange={e=>setAudience({...audience,hp_balance:e.target.value})} className="w-full p-2.5 rounded-xl border border-border bg-card text-sm"><option value="all">{msg('FE_BLAST_ANY','Any')}</option><option value="low">{'<100 HP'}</option><option value="medium">100–500 HP</option><option value="high">{' >500 HP'}</option></select></Field>
            <Field label={msg('FE_BLAST_ORDER_BAND','Total orders')}><select aria-label={msg('FE_BLAST_ORDER_BAND','Total orders')} value={audience.total_orders} onChange={e=>setAudience({...audience,total_orders:e.target.value})} className="w-full p-2.5 rounded-xl border border-border bg-card text-sm"><option value="any">{msg('FE_BLAST_ANY','Any')}</option>{['0','1-5','6-20','20+'].map(value=><option key={value} value={value}>{value}</option>)}</select></Field>
            {(['faculty','department','level'] as const).map(key=><Field key={key} label={key==='faculty'?msg('FE_BLAST_FACULTY','Faculty'):key==='department'?msg('FE_BLAST_DEPARTMENT','Department'):msg('FE_BLAST_LEVEL','Academic level')}><TextInput aria-label={key==='faculty'?msg('FE_BLAST_FACULTY','Faculty'):key==='department'?msg('FE_BLAST_DEPARTMENT','Department'):msg('FE_BLAST_LEVEL','Academic level')} value={audience[key]} onChange={e=>setAudience({...audience,[key]:e.target.value})} /></Field>)}
          </div>
          <Field label={msg('FE_BLAST_SPECIFIC_PEOPLE', 'Specific recipients (optional)')} hint={msg('FE_BLAST_RECIPIENT_HELP', 'Search and select people to intersect with the filters above. No selection uses the filtered audience.')}>
            <TextInput value={recipientQuery} onChange={e=>setRecipientQuery(e.target.value)} placeholder={msg('FE_BLAST_SEARCH_PEOPLE','Search name, nickname or email')} />
            {recipientError && <p role="alert" className="text-xs text-destructive">{msg('FE_BLAST_SEARCH_FAILED','Recipient search failed. Try again.')}</p>}
            {recipientQuery.trim().length>=2 && !recipientError && <div className="max-h-40 overflow-y-auto">{recipientResults.map(person=><button type="button" key={person.id} className="block w-full text-left text-xs p-2 rounded-lg hover:bg-muted" onClick={()=>{setSelectedRecipients(rows=>rows.some(row=>row.id===person.id)?rows:[...rows,person]);setRecipientQuery('');}}>{person.full_name || person.nickname || person.email} · {person.email}</button>)}</div>}
            <div className="flex flex-wrap gap-1 mt-2">{selectedRecipients.map(person=><button type="button" key={person.id} className="rounded-full px-2 py-1 text-xs bg-muted" onClick={()=>setSelectedRecipients(rows=>rows.filter(row=>row.id!==person.id))}>{person.full_name || person.email} ×</button>)}</div>
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
              title="Send test email to specific addresses to check if it lands in Primary or Spam"
            >
              <Mail className="w-4 h-4" />
              Test Deliverability
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
