import { msg } from '@/lib/messages';
import { bannerSpec, BANNER_ICON_SIZE, type BannerSpecId } from '@/lib/bannerSpec';

/**
 * BannerSpecNote — the design brief shown next to every admin image input.
 *
 * The numbers come from lib/bannerSpec, the same module the storefront cards
 * render from, so the size an administrator is told to design to is always the
 * size the frame actually is.
 */
export default function BannerSpecNote({ rows }: { rows: Array<{ spec: BannerSpecId; when?: string }> }) {
  return (
    <div className="space-y-1 rounded-xl border border-dashed border-border bg-muted/40 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
      <p className="font-bold text-foreground">{msg('FE_SF_ARTWORK_SPEC_TITLE', 'Design to the frame')}</p>
      {rows.map(({ spec, when }) => {
        const frame = bannerSpec(spec);
        return (
          <p key={spec}>
            {when ? `${when} — ` : ''}
            <span className="font-bold text-foreground">{frame.width} × {frame.height} px</span> ({frame.ratio})
          </p>
        );
      })}
      <p>
        {msg(
          'FE_SF_ARTWORK_SPEC_HELP',
          '“Full design image only” fills this whole rounded frame: upload exactly that size, square corners (the frame rounds them), and keep important content inside a 40 px safe margin. A text card instead shows a square {icon} × {icon} px icon or photo in its own rounded frame, with the title, description and a button carrying your CTA link.',
          { icon: BANNER_ICON_SIZE },
        )}
      </p>
    </div>
  );
}
