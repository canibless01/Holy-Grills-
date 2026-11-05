import type { CSSProperties, ReactNode } from 'react';
import { ChevronRight, Sparkles } from 'lucide-react';
import type { BannerSpec } from '@/lib/bannerSpec';

/**
 * BannerCard — the one card shell every admin image surface renders through.
 * ============================================================================
 * Two modes, one outer rounded frame (`rounded-2xl`, `overflow-hidden`):
 *
 *   text     → picture inset in its own rounded box, then eyebrow/badge/title/
 *              description, then a gradient button carrying the CMS CTA link;
 *   artwork  → the uploaded design fills the whole frame edge to edge. No inner
 *              rectangle, no letterboxing, no extra copy on top: the artwork is
 *              expected to be designed at the frame's own size (see bannerSpec).
 *
 * The frame is width-driven (aspect-ratio), so a desktop container scales the
 * artwork up with it instead of pinning it to a phone-sized strip.
 */
export interface BannerCardProps {
  spec: BannerSpec;
  mode?: 'text' | 'artwork';
  image?: string;
  title?: string;
  line?: string;
  eyebrow?: string;
  badge?: string;
  /** Label on the CTA button. Empty = no button. */
  actionLabel?: string;
  /** Called when the card (or its button) is activated. Empty = not clickable. */
  onAction?: () => void;
  /** Accessible name for the whole card. */
  label?: string;
  eager?: boolean;
  /** Optional line rendered under the copy (e.g. a small reassurance note). */
  footer?: ReactNode;
  className?: string;
  style?: CSSProperties;
}

export default function BannerCard({
  spec,
  mode = 'text',
  image = '',
  title = '',
  line = '',
  eyebrow = '',
  badge = '',
  actionLabel = '',
  onAction,
  label,
  eager = false,
  footer = null,
  className = '',
  style,
}: BannerCardProps) {
  const artworkOnly = mode === 'artwork';
  const clickable = typeof onAction === 'function';
  const Element = (clickable ? 'button' : 'div') as 'button' | 'div';
  const buttonProps = clickable
    ? { type: 'button' as const, onClick: onAction, 'aria-label': label || title || undefined }
    : {};
  const loading = eager ? 'eager' : 'lazy';
  const showAction = Boolean(actionLabel) && clickable;

  return (
    <Element
      {...buttonProps}
      className={`group relative block w-full overflow-hidden rounded-2xl border border-border bg-card text-left ${
        clickable ? 'transition-transform duration-200 active:scale-[0.995]' : ''
      } ${className}`}
      style={style}
    >
      {artworkOnly ? (
        /* The design owns the frame: edge to edge, corners from the container. */
        <div className="relative w-full overflow-hidden" style={{ aspectRatio: spec.aspect }}>
          {image && (
            <img
              src={image}
              alt={title}
              loading={loading}
              decoding="async"
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
        </div>
      ) : spec.layout === 'row' ? (
        <div className="flex items-center gap-3 p-3">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border/60 bg-muted/50 p-1.5 sm:h-[72px] sm:w-[72px]">
            {image ? (
              <img src={image} alt="" loading={loading} decoding="async" className="h-full w-full rounded-lg object-contain" />
            ) : (
              <Sparkles className="h-7 w-7 text-primary" aria-hidden="true" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            {eyebrow && <span className="mb-1 block text-[10px] font-bold text-primary">{eyebrow}</span>}
            {badge && (
              <span className="mb-1 inline-block rounded-full bg-accent/20 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-accent-foreground">
                {badge}
              </span>
            )}
            {title && <h3 className="line-clamp-1 font-heading text-sm font-extrabold leading-tight text-foreground">{title}</h3>}
            {line && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{line}</p>}
          </div>
          {showAction && <ActionPill label={actionLabel} />}
        </div>
      ) : (
        <div className="flex flex-col">
          {/* Inset picture frame — this is the rounded rectangle around the photo. */}
          <div className="p-2.5 sm:p-3">
            <div
              className="w-full overflow-hidden rounded-xl border border-border/60 bg-muted/40"
              style={{ aspectRatio: spec.aspect }}
            >
              {image && (
                <img src={image} alt={title} loading={loading} decoding="async" className="h-full w-full object-cover" />
              )}
            </div>
          </div>
          <div className="flex items-end gap-3 px-3 pb-3 sm:px-4 sm:pb-4">
            <div className="min-w-0 flex-1">
              {eyebrow && <span className="mb-1 block text-[11px] font-bold text-primary">{eyebrow}</span>}
              {badge && (
                <span className="mb-1 inline-block rounded-full bg-accent/20 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-accent-foreground">
                  {badge}
                </span>
              )}
              {title && <h3 className="line-clamp-2 font-heading text-base font-extrabold leading-tight text-foreground">{title}</h3>}
              {line && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{line}</p>}
            </div>
            {showAction && <ActionPill label={actionLabel} />}
          </div>
          {footer && <div className="px-3 pb-3 text-[10px] text-muted-foreground sm:px-4">{footer}</div>}
        </div>
      )}
    </Element>
  );
}

/** The CTA inside the card. Rendered as a span — the card itself is the button. */
function ActionPill({ label }: { label: string }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5 whitespace-nowrap rounded-full bg-gradient-cta px-3.5 py-2 text-xs font-extrabold text-white shadow-sm">
      {label}
      <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
    </span>
  );
}
