import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Bold, Italic, Underline, Link as LinkIcon, List, ListOrdered, Heading1, Heading2,
  AlignLeft, AlignCenter, Image as ImageIcon, Undo2, Redo2, Unlink, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { msg } from '@/lib/messages';

interface RichTextEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  /**
   * When provided, the image button uploads through this handler instead of
   * embedding an <img> in the HTML. Campaign images belong in the image stack:
   * the blast API sanitises body_html and drops <img> tags, so an image pasted
   * into the body would silently disappear from the email.
   */
  onInsertImage?: () => void;
  disabled?: boolean;
}

/**
 * RichTextEditor — the admin panel's rich text field.
 *
 * Deliberately UNCONTROLLED. The previous version fed `dangerouslySetInnerHTML`
 * from state on every render, and since `onChange` fires on every keystroke the
 * whole subtree was re-created each time — which reset the caret to the start of
 * the field. Typing then prepended each new character (the "writing backwards"
 * bug). Now the DOM is the source of truth while editing; we only write `value`
 * back into it when it changed *outside* the editor (form reset, template load).
 *
 * Formatting uses execCommand, which is deprecated but still the only way to get
 * caret-preserving rich text without pulling in an editor dependency. Toolbar
 * buttons use onMouseDown + preventDefault so the selection survives the click.
 */

const ALLOWED_PASTE_TAGS = new Set(['p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'a', 'ul', 'ol', 'li', 'h1', 'h2']);

/** Keep basic formatting from a paste, drop everything else (scripts, styles, inline JS). */
function sanitizePastedHtml(raw: string): string {
  try {
    const doc = new DOMParser().parseFromString(raw, 'text/html');
    const walk = (node: Node): string => {
      if (node.nodeType === Node.TEXT_NODE) {
        return (node.textContent || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return '';
      const el = node as HTMLElement;
      const tag = el.tagName.toLowerCase();
      const inner = Array.from(el.childNodes).map(walk).join('');
      if (!ALLOWED_PASTE_TAGS.has(tag)) return inner;
      if (tag === 'a') {
        const href = el.getAttribute('href') || '';
        if (!/^https:\/\//i.test(href)) return inner;
        return `<a href="${href.replace(/"/g, '&quot;')}">${inner}</a>`;
      }
      if (tag === 'br') return '<br>';
      return `<${tag}>${inner}</${tag}>`;
    };
    return Array.from(doc.body.childNodes).map(walk).join('');
  } catch {
    return '';
  }
}

export default function RichTextEditor({
  value, onChange, placeholder = 'Write your message...', className, onInsertImage, disabled = false,
}: RichTextEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const lastEmitted = useRef<string>('');   // last HTML this component produced
  const [focused, setFocused] = useState(false);
  const [empty, setEmpty] = useState(!value);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkDraft, setLinkDraft] = useState('');

  // Write incoming HTML into the DOM only when it did not come from this editor.
  // This is the fix for the caret jumping: a keystroke no longer tears down the
  // content the browser is editing.
  useEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    if (value === lastEmitted.current) return;      // our own change — DOM already matches
    if (el.innerHTML === (value || '')) {
      lastEmitted.current = value || '';
      return;
    }
    el.innerHTML = value || '';
    lastEmitted.current = value || '';
    setEmpty(!value);
  }, [value]);

  const emit = useCallback(() => {
    const el = editorRef.current;
    if (!el) return;
    const html = el.innerHTML;
    lastEmitted.current = html;
    setEmpty(!el.textContent?.trim() && !el.querySelector('img'));
    onChange(html);
  }, [onChange]);

  const exec = useCallback((command: string, arg?: string) => {
    if (disabled) return;
    editorRef.current?.focus();
    try {
      document.execCommand(command, false, arg);
    } catch { /* unsupported command in this browser — ignore */ }
    emit();
  }, [disabled, emit]);

  const applyLink = () => {
    const url = linkDraft.trim();
    setLinkOpen(false);
    setLinkDraft('');
    if (!/^https:\/\/\S+$/i.test(url)) return;
    exec('createLink', url);
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLDivElement>) => {
    const html = event.clipboardData?.getData('text/html');
    const text = event.clipboardData?.getData('text/plain');
    // Always paste as our own sanitised markup: source markup can carry inline
    // styles the blast API strips anyway, plus event handlers we never want.
    event.preventDefault();
    const safe = html ? sanitizePastedHtml(html) : '';
    if (safe) {
      document.execCommand('insertHTML', false, safe);
    } else if (text) {
      document.execCommand('insertText', false, text);
    }
    emit();
  };

  const button = (title: string, onClick: () => void, Icon: typeof Bold, opts: { active?: boolean } = {}) => (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      // preventDefault keeps the caret/selection in the editor when the button is pressed.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className={cn(
        'p-1.5 rounded-lg text-muted-foreground transition hover:bg-secondary hover:text-foreground disabled:opacity-40',
        opts.active && 'bg-secondary text-foreground',
      )}
    >
      <Icon className="w-4 h-4" />
    </button>
  );

  const divider = <div className="w-px h-5 bg-border mx-0.5" aria-hidden />;

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card overflow-hidden focus-within:ring-2 focus-within:ring-primary/40',
        disabled && 'opacity-60',
        className,
      )}
    >
      <div className="flex items-center gap-0.5 p-1.5 border-b border-border bg-secondary/30 flex-wrap">
        {button(msg('FE_EDITOR_BOLD', 'Bold'), () => exec('bold'), Bold)}
        {button(msg('FE_EDITOR_ITALIC', 'Italic'), () => exec('italic'), Italic)}
        {button(msg('FE_EDITOR_UNDERLINE', 'Underline'), () => exec('underline'), Underline)}
        {divider}
        {button(msg('FE_EDITOR_HEADING_1', 'Heading 1'), () => exec('formatBlock', '<h1>'), Heading1)}
        {button(msg('FE_EDITOR_HEADING_2', 'Heading 2'), () => exec('formatBlock', '<h2>'), Heading2)}
        {button(msg('FE_EDITOR_PARAGRAPH', 'Paragraph'), () => exec('formatBlock', '<p>'), AlignLeft)}
        {divider}
        {button(msg('FE_EDITOR_BULLET_LIST', 'Bullet list'), () => exec('insertUnorderedList'), List)}
        {button(msg('FE_EDITOR_NUMBERED_LIST', 'Numbered list'), () => exec('insertOrderedList'), ListOrdered)}
        {divider}
        {button(msg('FE_EDITOR_ALIGN_LEFT', 'Align left'), () => exec('justifyLeft'), AlignLeft)}
        {button(msg('FE_EDITOR_ALIGN_CENTER', 'Align centre'), () => exec('justifyCenter'), AlignCenter)}
        {divider}
        {button(msg('FE_EDITOR_ADD_LINK', 'Add link'), () => setLinkOpen((open) => !open), LinkIcon, { active: linkOpen })}
        {button(msg('FE_EDITOR_REMOVE_LINK', 'Remove link'), () => exec('unlink'), Unlink)}
        {onInsertImage && button(msg('FE_EDITOR_ADD_IMAGE', 'Add image'), onInsertImage, ImageIcon)}
        {divider}
        {button(msg('FE_EDITOR_UNDO', 'Undo'), () => exec('undo'), Undo2)}
        {button(msg('FE_EDITOR_REDO', 'Redo'), () => exec('redo'), Redo2)}
      </div>

      {linkOpen && (
        <div className="flex items-center gap-1.5 p-2 border-b border-border bg-secondary/20">
          <LinkIcon className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          <input
            autoFocus
            value={linkDraft}
            onChange={(e) => setLinkDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); applyLink(); }
              if (e.key === 'Escape') { setLinkOpen(false); setLinkDraft(''); }
            }}
            placeholder={msg('FE_EDITOR_LINK_PLACEHOLDER', 'https://holygrills.online/menu')}
            className="flex-1 min-w-0 px-2 py-1.5 rounded-lg border border-border bg-card text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <button type="button" onClick={applyLink} className="shrink-0 px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-bold">
            {msg('FE_EDITOR_APPLY', 'Apply')}
          </button>
          <button type="button" onClick={() => { setLinkOpen(false); setLinkDraft(''); }} className="shrink-0 p-1.5 rounded-lg hover:bg-secondary" aria-label={msg('FE_PLATFORM_CLOSE', 'Close')}>
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <div className="relative">
        {empty && !focused && (
          <div className="pointer-events-none absolute inset-0 p-3 text-sm text-muted-foreground">{placeholder}</div>
        )}
        <div
          ref={editorRef}
          contentEditable={!disabled}
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          aria-label={placeholder}
          onInput={emit}
          onBlur={() => { setFocused(false); emit(); }}
          onFocus={() => setFocused(true)}
          onPaste={handlePaste}
          className={cn(
            'min-h-[140px] max-h-[400px] overflow-y-auto p-3 text-sm text-foreground focus:outline-none',
            '[&_h1]:text-xl [&_h1]:font-bold [&_h1]:my-2',
            '[&_h2]:text-lg [&_h2]:font-semibold [&_h2]:my-2',
            '[&_p]:my-1.5',
            '[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1.5',
            '[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1.5',
            '[&_a]:text-primary [&_a]:underline',
            '[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
          )}
          style={{ lineHeight: 1.6 }}
        />
      </div>
    </div>
  );
}
