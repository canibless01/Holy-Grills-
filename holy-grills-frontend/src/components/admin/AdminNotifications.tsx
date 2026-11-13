import { plainBlastHtml } from '@/lib/blastPreview';
import { useState, useEffect, useRef } from 'react';
import { Send, Bell, Calendar, Clock, CheckCircle2, AlertCircle, Eye, Mail, TrendingUp } from 'lucide-react';
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
import ImageUploader from './ImageUploader';
import CTABlockEditor, { type CTABlock } from './CTABlockEditor';
import ImageStackEditor, { type ImageBlock } from './ImageStackEditor';
import EmailPreviewModal from './EmailPreviewModal';
import BlastAnalyticsModal from './BlastAnalyticsModal';
import { useHolyGrill } from '@/lib/HolyGrillContext';

type RecoverableDelivery = {
  id: string; channel: string; status: string; provider?: string;
  title?: string; recipient?: string; error_message?: string; attempts: string;
};

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

const DEFAULT_AUDIENCE = { has_active_order: 'any', has_cart: 'any', last_order_days: 'any', last_login_days: 'any', hp_balance: 'all', total_orders: 'any', has_pending_hp: 'any', has_referral: 'any', has_reviewed: 'any', has_shared: 'any', has_squad_order: 'any', has_graduated: 'any', event_attendance: 'any', department: '', faculty: '', level: '' };

const STATUS_STYLE = {
  cancelled: {tone:'cocoa',icon:CheckCircle2,label:msg('FE_BLAST_CANCELLED','Cancelled')},
  sent: { tone: 'green', icon: CheckCircle2, label: msg('FE_BLAST_PROCESSED', 'Processed') },
  scheduled: { tone: 'amber', icon: Clock, label: 'Scheduled' },
  pending: { tone: 'cocoa', icon: AlertCircle, label: 'Pending' },
  // A blast that errored mid-send used to render as "Pending", which read as
  // "still on its way" when it had actually stopped.
  failed: { tone: 'red', icon: AlertCircle, label: msg('FE_BLAST_FAILED', 'Failed') },
  sending: { tone: 'amber', icon: Clock, label: msg('FE_BLAST_SENDING', 'Sending') },
};

export default function AdminNotifications() {
  const { user } = useHolyGrill();
  const operationLock=useRef(false);const reviewLock=useRef(false);const syncLock=useRef(false);
  const previewGeneration=useRef(0);const loadGeneration=useRef(0);const recoveryGeneration=useRef(0);
  const [historyBusy,setHistoryBusy]=useState<string|null>(null);
  const [historyOffset,setHistoryOffset]=useState(0);const [historyStatus,setHistoryStatus]=useState('');
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [recoveries, setRecoveries] = useState<RecoverableDelivery[]>([]);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const [recoveryError, setRecoveryError] = useState('');
  const [review, setReview] = useState<RecoverableDelivery | null>(null);
  const [reviewId, setReviewId] = useState('');
  const [reviewOutcome, setReviewOutcome] = useState('sent');
  const [reviewProvider, setReviewProvider] = useState('onesignal');
  const [reviewMessage, setReviewMessage] = useState('');
  const [reviewEvidence, setReviewEvidence] = useState('');
  const [reviewSaving, setReviewSaving] = useState(false);
  const loadRecovery = async () => {
    const current=++recoveryGeneration.current;setRecoveryLoading(true); setRecoveryError('');
    try { const result = await apiClient.get('/notifications/dispatch/recovery'); if(current===recoveryGeneration.current)setRecoveries(result.deliveries || []); }
    catch { if(current===recoveryGeneration.current)setRecoveryError('Delivery recovery could not load. Please retry.'); }
    finally { if(current===recoveryGeneration.current)setRecoveryLoading(false); }
  };
  const openReview = (row: RecoverableDelivery) => {
    setReview(row); setReviewId(crypto.randomUUID()); setReviewOutcome('sent');
    setReviewProvider(row.provider || 'onesignal'); setReviewMessage(''); setReviewEvidence(''); setRecoveryError('');
  };
  const saveReview = async (event: React.FormEvent) => {
    event.preventDefault(); if (!review || reviewLock.current) return;reviewLock.current=true;
    setReviewSaving(true); setRecoveryError('');
    try {
      await apiClient.post(`/notifications/dispatch/${review.id}/review`, {
        review_id: reviewId, outcome: reviewOutcome, provider: reviewProvider,
        provider_message_id: reviewMessage.trim() || null, evidence: reviewEvidence.trim(),
      });
      setReview(null); await loadRecovery();
    } catch { setRecoveryError('Review could not be saved. Check the provider evidence and refresh if the delivery changed.'); }
    finally { reviewLock.current=false;setReviewSaving(false); }
  };
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [images, setImages] = useState<ImageBlock[]>([]);
  const [ctaBlocks, setCtaBlocks] = useState<CTABlock[]>([]);
  const [channels, setChannels] = useState(['push', 'in_app']);
  const [role, setRole] = useState('all');
  const [tier, setTier] = useState('all');
  const [audience, setAudience] = useState(DEFAULT_AUDIENCE);
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
  const testIntent = useCmsCreateIntent();
  const [previewCount, setPreviewCount] = useState(null);
  const [pushImage, setPushImage] = useState(''); // Image for push/in-app notifications
  const [trackingEnabled, setTrackingEnabled] = useState(false); // Enable open/click tracking
  const [analyticsBlastId, setAnalyticsBlastId] = useState<string | null>(null); // Blast ID for analytics modal
  const [analyticsBlastTitle, setAnalyticsBlastTitle] = useState<string>(''); // Blast title for analytics modal
  // Why mail might not land: which providers are configured and how much of
  // today's allowance each has used (GET /admin/email-health). Read-only.
  const [emailHealth, setEmailHealth] = useState<any>(null);
  const [showTips, setShowTips] = useState(false);
  const [syncingSubscribers, setSyncingSubscribers] = useState(false);
  const preview = async () => {
    const current=++previewGeneration.current;
    try { const result = await apiClient.post('/notifications/blasts/preview', buildPayload()); if(current===previewGeneration.current)setPreviewCount(result.recipient_count); }
    catch { if(current===previewGeneration.current)toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), variant: 'destructive' }); }
  };
  const cancelCampaign = async (id) => {
    if(operationLock.current)return;operationLock.current=true;setHistoryBusy(id);
    try { await apiClient.post(`/notifications/blasts/${id}/cancel`, {}); await load(); }
    catch (e) { toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: e.message, variant: 'destructive' }); }
    finally{operationLock.current=false;setHistoryBusy(null);}
  };
  const retryCampaign = async (id) => {
    if(operationLock.current)return;operationLock.current=true;setHistoryBusy(id);
    try { await apiClient.post(`/notifications/blasts/${id}/retry`, {}); await load(); }
    catch (e) { toast({ title: msg('FE_PLATFORM_LOAD_FAILED', "We couldn't load this page. Please try again."), description: e.message, variant: 'destructive' }); }
    finally{operationLock.current=false;setHistoryBusy(null);}
  };
  useEffect(() => { previewGeneration.current++;setPreviewCount(null); }, [role, tier, audience, selectedRecipients]);

  const load = async () => {
    const current=++loadGeneration.current;setLoading(true);setLoadError(false);
    await Promise.all([
      mockApi.admin.getNotificationBlasts({limit:25,offset:historyOffset,...(historyStatus?{status:historyStatus}:{})}).then(rows=>{if(current===loadGeneration.current)setBlasts(rows);}).catch(()=>{if(current===loadGeneration.current)setLoadError(true);}),
      apiClient.get('/admin/email-health').then(value=>{if(current===loadGeneration.current)setEmailHealth(value);}).catch(()=>{if(current===loadGeneration.current)setEmailHealth(null);}),
    ]);
    if(current===loadGeneration.current)setLoading(false);
  };
  useEffect(() => { void load();return()=>{loadGeneration.current++;previewGeneration.current++;recoveryGeneration.current++;}; }, [historyOffset,historyStatus]);

  const toggleChannel = (id, checked) => setChannels(checked ? [...channels, id] : channels.filter((x) => x !== id));
  // The editor's image button appends an image block (max 6) and points the admin
  // at it, rather than embedding an <img> the blast API would strip.
  const addImageBlock = () => {
    if (images.length >= 6) {
      toast({ title: msg('FE_ADMIN_NOTIFICATIONS_IMAGE_LIMIT', 'Image limit reached'), description: msg('FE_ADMIN_NOTIFICATIONS_IMAGE_LIMIT_BODY', 'A campaign can carry up to 6 images.'), variant: 'destructive' });
      return;
    }
    setImages([...images, { id: `img-${Date.now()}`, url: '', alt: '', link: '' }]);
  };
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
      const d = new Date(`${sendAt.length===16?sendAt+':00':sendAt}+01:00`);
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
    if(operationLock.current)return;operationLock.current=true;setSending(true);
    try {
      const res = await mockApi.admin.sendNotificationBlast(intent.body(buildPayload()));
      if (res?.already_created && ['pending', 'sending', 'failed'].includes(res?.blast?.status)) {
        toast({ title: msg('FE_BLAST_EXISTS_PENDING', 'This campaign is already saved. Check its history entry to review progress or retry.') });
        setConfirmOpen(false);
        await load();
        setSending(false);operationLock.current=false;
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
      setRecipientQuery(''); setSelectedRecipients([]);setAudience(DEFAULT_AUDIENCE);setEmailProvider('default');setTrackingEnabled(false);
      setConfirmOpen(false);
      await load();
    } catch (e) {
      toast({ title: msg('FE_ADMIN_NOTIFICATIONS_FAILED_TO_SEND', 'Failed to send'), description: e.message, variant: 'destructive' });
      setConfirmOpen(false);
      await load();
    }
    operationLock.current=false;setSending(false);
  };

  const sendTest = async () => {
    if (!user?.email) {
      toast({ title: 'Cannot send test', description: 'Your email address is not available.', variant: 'destructive' });
      return;
    }
    if(operationLock.current)return;operationLock.current=true;setSendingTest(true);
    try {
      const res = await apiClient.post('/notifications/blasts/test', {
        ...testIntent.body(buildPayload()),
        test_email: user.email,
      });
      testIntent.clear();
      // Report what the provider said, not just that the request was accepted: a
      // test that "sent" while OneSignal had no subscription for the address is
      // exactly the failure this page needs to make visible.
      const receipt = res?.email;
      if (channels.includes('email') && !['sent','delivered'].includes(receipt?.status)) {
        toast({
          title: msg('FE_TEST_EMAIL_NOT_DELIVERED', 'Test email was not delivered'),
          description: receipt.error || msg('FE_TEST_EMAIL_NO_RECEIPT', 'The provider did not confirm delivery.'),
          variant: 'destructive',
        });
      } else {
        toast({
          title: msg('FE_BLAST_TEST_PROCESSED','Test request processed'),
          description: receipt?.message_id
            ? `${user.email} · ${msg('FE_TEST_EMAIL_ACCEPTED', 'accepted, id {id}', { id: receipt.message_id })}`
            : `Test notification sent to ${user.email}`,
        });
      }
    } catch (e) {
      toast({ title: 'Failed to send test', description: e.message, variant: 'destructive' });
    }
    operationLock.current=false;setSendingTest(false);
  };

  // Existing accounts were never registered as OneSignal email subscribers, which
  // is why a campaign to "everyone" reached almost no inboxes. This backfills them.
  const syncEmailSubscribers = async () => {
    if(syncLock.current)return;syncLock.current=true;setSyncingSubscribers(true);
    try {
      await apiClient.post('/admin/email-subscriptions/backfill', { limit: 500 });
      toast({
        title: msg('FE_EMAIL_HEALTH_BACKFILL_STARTED', 'Email subscriber sync started'),
        description: msg('FE_BLAST_SYNC_SCOPE_HINT','Up to 500 accounts in the current campus scope are being checked. Re-check OneSignal for the result.'),
      });
    } catch (e) {
      toast({
        title: msg('FE_EMAIL_HEALTH_BACKFILL_FAILED', "Couldn't start the sync"),
        description: e.message,
        variant: 'destructive',
      });
    }
    syncLock.current=false;setSyncingSubscribers(false);
  };

  const testDeliverability = async () => {
    await sendTest();setShowTips(true);
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
        <fieldset disabled={sending||sendingTest||!!historyBusy} className="space-y-3">
          <Field label="Title (required)">
            <TextInput maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. New menu drop is live 🔥" />
          </Field>
          <Field label="Body (required)">
            <RichTextEditor
              value={bodyHtml}
              onChange={setBodyHtml}
              placeholder="Write your notification message with rich formatting..."
              // Campaign images live in the image stack below, not inside the HTML:
              // the blast API sanitises body_html and drops <img>, so an inline image
              // would silently vanish from the email.
              onInsertImage={addImageBlock}
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
            <ImageUploader value={pushImage} onChange={setPushImage} folder="campaigns" label="Push image" />
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
          <Field label={msg('FE_BLAST_SCHEDULE_WAT','Schedule (WAT, optional)')} hint="Leave empty to send immediately. Pick a date & time to schedule for later.">
            <div className="flex items-center gap-2 mt-1">
              <Calendar className="w-4 h-4 text-muted-foreground shrink-0" />
              <input
                type="datetime-local"
                aria-label={msg('FE_BLAST_SCHEDULE_WAT','Schedule (WAT, optional)')}
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

          {/* Email provider health — the same counters that decide the fallback
              switch. Shown next to the provider picker so an admin can see why
              mail is going out on the other provider, or not at all. */}
          {emailHealth && (
            <div className="rounded-xl border border-border bg-secondary/40 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-primary" />
                  {msg('FE_EMAIL_HEALTH_TITLE', 'Email delivery today')}
                </span>
                {emailHealth.onesignal_email_from && (
                  <span className="text-[10px] font-bold text-muted-foreground truncate" title={emailHealth.onesignal_email_from}>
                    {msg('FE_EMAIL_HEALTH_FROM', 'From {address}', { address: emailHealth.onesignal_email_from })}
                  </span>
                )}
              </div>
              <div className="space-y-1">
                {(emailHealth.providers || []).map((p) => {
                  const used = p.sent_today ?? 0;
                  const limit = p.daily_limit ?? 0;
                  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
                  const exhausted = limit > 0 && used >= limit;
                  return (
                    <div key={p.provider} className="flex items-center gap-2 text-[11px]">
                      <span className="font-bold text-foreground capitalize w-20 shrink-0">{p.provider}</span>
                      {p.configured === false ? (
                        <Pill tone="cocoa">{msg('FE_EMAIL_HEALTH_NOT_CONFIGURED', 'Not configured')}</Pill>
                      ) : (
                        <span className={`font-bold ${exhausted ? 'text-destructive' : 'text-muted-foreground'}`}>
                          {limit > 0
                            ? msg('FE_EMAIL_HEALTH_USAGE', '{used} of {limit} today', { used, limit })
                            : msg('FE_EMAIL_HEALTH_UNLIMITED', '{used} today', { used })}
                        </span>
                      )}
                      {exhausted && <Pill tone="red">{msg('FE_EMAIL_HEALTH_EXHAUSTED', 'Switched away')}</Pill>}
                      {limit > 0 && (
                        <div className="flex-1 h-1 rounded-full bg-border overflow-hidden">
                          <div className={`h-full ${exhausted ? 'bg-destructive' : 'bg-primary'}`} style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center justify-between gap-2 pt-1">
                <button
                  onClick={syncEmailSubscribers}
                  disabled={syncingSubscribers}
                  className="text-[10px] font-bold text-primary hover:underline disabled:opacity-50"
                  title="Register existing accounts as OneSignal email subscribers"
                >
                  {syncingSubscribers
                    ? msg('FE_EMAIL_HEALTH_BACKFILLING', 'Starting sync…')
                    : msg('FE_EMAIL_HEALTH_BACKFILL', 'Sync existing email subscribers')}
                </button>
              </div>
              <p className="text-[10px] text-muted-foreground">
                {msg('FE_EMAIL_HEALTH_NOTE', 'Providers switch at quota limits. Unconfirmed sends need provider review before another attempt.')}
              </p>
            </div>
          )}

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
              title={msg('FE_BLAST_OWN_TEST_HINT','Send a test to your signed-in admin account and check its inbox.')}
            >
              <Mail className="w-4 h-4" />
              Test Deliverability
            </button>
          </div>

          <button
            onClick={handleSubmit}
            disabled={sending || sendingTest || !!historyBusy || !valid}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
            {sending ? 'Sending...' : isScheduled ? 'Schedule Campaign' : 'Send Blast Now'}
          </button>
          {showTips && (
            <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-foreground">{msg('FE_EMAIL_TIPS_TITLE', 'Checking what landed')}</span>
                <button onClick={() => setShowTips(false)} className="text-[10px] font-bold text-muted-foreground hover:underline">
                  {msg('FE_EMAIL_TIPS_DISMISS', 'Dismiss')}
                </button>
              </div>
              <ul className="text-[11px] text-muted-foreground space-y-0.5 list-disc pl-4">
                <li>{msg('FE_EMAIL_TIPS_PRIMARY', 'Did it land in Primary or in Spam?')}</li>
                <li>{msg('FE_EMAIL_TIPS_SPEED', 'How quickly did it arrive?')}</li>
                <li>{msg('FE_EMAIL_TIPS_RENDER', 'Does it render correctly, and do the links work?')}</li>
                <li>{msg('FE_EMAIL_TIPS_SENDER', 'A clear subject and one consistent sender address help most.')}</li>
              </ul>
            </div>
          )}
          <button onClick={preview} className="text-primary font-bold text-sm">{msg('FE_BLAST_PREVIEW', 'Preview recipients')}</button>
          {previewCount !== null && <p className="text-sm">{msg('FE_BLAST_AUDIENCE_COUNT', '{count} recipients in this audience.', { count: previewCount })}</p>}
        </fieldset>
      </Card>

      <Card>
        <button type="button" aria-expanded={recoveryOpen} className="font-bold text-sm text-primary" onClick={() => {
          if (!recoveryOpen) void loadRecovery(); setRecoveryOpen(!recoveryOpen);
        }}>Delivery recovery</button>
        {recoveryOpen && <div className="space-y-3 mt-3">
          <p className="text-xs text-muted-foreground">Unsent messages recover automatically. An uncertain email needs a provider log review before another attempt, to avoid duplicates.</p>
          <button type="button" disabled={recoveryLoading} className="text-primary font-bold text-sm disabled:opacity-50" onClick={() => void loadRecovery()}>Refresh deliveries</button>
          {recoveryLoading && <LoadingSpinner label="Loading deliveries..." />}
          {recoveryError && !review && <p role="alert" className="text-destructive text-sm">{recoveryError}</p>}
          {!recoveryLoading && !recoveryError && recoveries.length === 0 && <p className="text-sm">No deliveries need recovery.</p>}
          {recoveries.map(row => <div key={row.id} className="border border-border rounded-xl p-3 space-y-1 break-words">
            <p className="font-bold text-sm">{row.title || 'Notification'}</p>
            <p className="text-xs">{row.channel} · {row.status} · {row.attempts} attempts</p>
            <p className="text-xs text-muted-foreground">{row.recipient}</p>
            {row.error_message && <p className="text-xs text-muted-foreground">{row.error_message}</p>}
            {['uncertain', 'failed'].includes(row.status) && <button type="button" className="text-primary font-bold text-sm" onClick={() => openReview(row)}>Review provider result</button>}
          </div>)}
        </div>}
      </Card>
      <Modal open={!!review} onClose={() => { if (!reviewSaving) setReview(null); }} title="Review delivery">
        <form onSubmit={saveReview} className="space-y-4">
          <p className="text-sm">Check the provider logs for this recipient and message. Requeue only when the provider confirms it did not send.</p>
          <Field label="Provider"><select value={reviewProvider} onChange={e => { setReviewProvider(e.target.value); setReviewId(crypto.randomUUID()); }} disabled={reviewSaving} className="w-full rounded-xl border border-border p-3 bg-card">
            <option value="onesignal">OneSignal</option>{review?.channel !== 'push' && <option value="resend">Resend</option>}
          </select></Field>
          <Field label="Confirmed result"><select value={reviewOutcome} onChange={e => { setReviewOutcome(e.target.value); setReviewId(crypto.randomUUID()); }} disabled={reviewSaving} className="w-full rounded-xl border border-border p-3 bg-card">
            <option value="sent">Provider accepted — mark sent</option><option value="not_sent">Provider confirms not sent — queue another attempt</option>
          </select></Field>
          <Field label="Provider message ID"><TextInput value={reviewMessage} onChange={e => { setReviewMessage(e.target.value); setReviewId(crypto.randomUUID()); }} required={reviewOutcome === 'sent'} maxLength={300} disabled={reviewSaving} /></Field>
          <Field label="Provider log evidence"><textarea value={reviewEvidence} onChange={e => { setReviewEvidence(e.target.value); setReviewId(crypto.randomUUID()); }} required minLength={10} maxLength={500} disabled={reviewSaving} className="w-full rounded-xl border border-border p-3 bg-card" /></Field>
          {recoveryError && <p role="alert" className="text-destructive text-sm">{recoveryError}</p>}
          <button type="submit" disabled={reviewSaving || reviewEvidence.trim().length < 10 || (reviewOutcome === 'sent' && !reviewMessage.trim())} className="w-full rounded-full bg-gradient-cta text-white font-bold p-3 disabled:opacity-50">{reviewSaving ? 'Saving...' : 'Save provider review'}</button>
        </form>
      </Modal>

      {/* Recent blasts */}
      <div>
        <h3 className="font-bold text-sm text-foreground mb-2">Recent Campaigns</h3>
        <Field label={msg('FE_BLAST_HISTORY_STATUS','Campaign status')}><select value={historyStatus} onChange={e=>{setHistoryOffset(0);setHistoryStatus(e.target.value);}} className="w-full rounded-xl border border-border bg-card p-3 text-sm"><option value="">{msg('FE_BLAST_HISTORY_ALL','All statuses')}</option>{Object.entries(STATUS_STYLE).map(([value,info])=><option key={value} value={value}>{info.label}</option>)}</select></Field>
        <div className="flex justify-between gap-2 py-3"><button disabled={loading||historyOffset===0||!!historyBusy} onClick={()=>setHistoryOffset(v=>Math.max(0,v-25))} className="rounded-full border border-border px-4 py-2 text-xs font-bold disabled:opacity-50">{msg('FE_BLAST_HISTORY_PREVIOUS','Previous campaigns')}</button><button disabled={loading||blasts.length<25||!!historyBusy} onClick={()=>setHistoryOffset(v=>v+25)} className="rounded-full border border-border px-4 py-2 text-xs font-bold disabled:opacity-50">{msg('FE_BLAST_HISTORY_NEXT','Next campaigns')}</button></div>
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
                  {['pending', 'scheduled'].includes(b.status) && <button disabled={!!historyBusy || sending || sendingTest} onClick={() => cancelCampaign(b.id)} className="text-destructive font-bold text-xs">{msg('FE_BLAST_CANCEL', 'Cancel campaign')}</button>}
                  {['failed', 'sending'].includes(b.status) && <button disabled={!!historyBusy || sending || sendingTest} onClick={() => retryCampaign(b.id)} className="text-primary font-bold text-xs">{msg('FE_BLAST_RETRY', 'Retry campaign')}</button>}
                  {b.metadata?.processed_count != null && <p className="text-xs">{msg('FE_BLAST_PROCESSED_RECIPIENTS', 'Campaign processed for {count} recipients.', { count: b.metadata.processed_count })}</p>}
                  {b.metadata?.notification_records != null && <p className="text-xs">{msg('FE_BLAST_STORED_RECORDS', '{count} notification records stored', { count: b.metadata.notification_records })}</p>}
                  {/* Real delivery, not just "processed": counted from
                      notification_deliveries after the send settles. */}
                  {b.metadata?.dispatch?.email && (
                    <p className={`text-xs font-bold ${b.metadata.email_delivery_failed ? 'text-destructive' : 'text-muted-foreground'}`}>
                      {msg('FE_BLAST_EMAIL_DELIVERY', 'Email accepted: {sent}; confirmed failures: {failed}.', {
                        sent: b.metadata.dispatch.email.sent ?? 0,
                        failed: b.metadata.dispatch.email.failed ?? 0,
                      })}
                    </p>
                  )}
                  {b.metadata?.dispatch?.push && (
                    <p className="text-xs text-muted-foreground">
                      {msg('FE_BLAST_PUSH_DELIVERY', 'Push accepted: {sent}; confirmed failures: {failed}.', {
                        sent: b.metadata.dispatch.push.sent ?? 0,
                        failed: b.metadata.dispatch.push.failed ?? 0,
                      })}
                    </p>
                  )}
                  {b.metadata?.email_delivery_failed && (
                    <Pill tone="red">{msg('FE_BLAST_EMAIL_FAILED', 'Email not delivered')}</Pill>
                  )}
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
        bodyHtml={bodyHtml||plainBlastHtml(body)}
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
            {' '}{selectedRecipients.length?msg('FE_BLAST_CONFIRM_SELECTED','{count} selected accounts',{count:selectedRecipients.length}):msg('FE_BLAST_CONFIRM_AUDIENCE','eligible accounts matching this audience and campus scope')}.
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
