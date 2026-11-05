import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Mail, Loader2 } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';

export default function NewsletterUnsubscribe() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const invalid = msg('FE_NEWSLETTER_INVALID_LINK', 'This link is missing or invalid. Open the unsubscribe link from a newsletter email.');
  const unsubscribe = async () => {
    if (!token || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post('/storefront/newsletter/unsubscribe', { token });
      setDone(true);
    } catch (failure) {
      setError(failure.status === 400 ? invalid : (failure.message || msg('FE_NEWSLETTER_RETRY', 'Please try again in a moment.')));
    } finally { setBusy(false); }
  };
  return <div className="max-w-md mx-auto rounded-2xl bg-card border border-border p-6 space-y-4">
    <Mail className="w-8 h-8 text-primary" />
    <h1 className="font-heading font-bold text-xl">{msg('FE_NEWSLETTER_PREFERENCES', 'Newsletter preferences')}</h1>
    <p className="text-sm text-muted-foreground" role={done ? 'status' : undefined}>
      {done ? msg('FE_NEWSLETTER_UNSUBSCRIBED', 'You have unsubscribed from newsletter updates.') : token ? msg('FE_NEWSLETTER_UNSUBSCRIBE_BODY', 'Unsubscribe this email address from newsletter updates.') : invalid}
    </p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {!done && <button onClick={unsubscribe} disabled={!token || busy} className="w-full rounded-full bg-gradient-cta text-white font-bold text-sm py-3 disabled:opacity-50 flex items-center justify-center gap-2">
      {busy && <Loader2 className="w-4 h-4 animate-spin" />}
      {msg('FE_NEWSLETTER_UNSUBSCRIBE', 'Unsubscribe')}
    </button>}
    <Link to="/" className="block text-center text-sm text-primary font-semibold">{msg('FE_NEWSLETTER_RETURN_HOME', 'Return home')}</Link>
  </div>;
}
