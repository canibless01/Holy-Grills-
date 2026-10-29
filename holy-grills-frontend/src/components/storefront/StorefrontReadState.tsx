import { msg } from '@/lib/messages';

export default function StorefrontReadState({ loading = false, retry, label = 'Storefront' }) {
  return (
    <div role="status" aria-label={label} className="rounded-2xl border border-border bg-card p-4 text-sm text-muted-foreground">
      {loading ? msg('FE_STOREFRONT_LOADING', 'Loading the latest from the grill…') : <>
        <p>{msg('FE_STOREFRONT_LOAD_FAILED', 'This section couldn’t load. Please try again.')}</p>
        <button type="button" onClick={retry} className="mt-2 font-semibold text-primary underline">
          {msg('FE_STOREFRONT_RETRY', 'Retry')}
        </button>
      </>}
    </div>
  );
}
