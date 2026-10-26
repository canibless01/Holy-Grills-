import { useState, useRef, useCallback } from 'react';
import { Bold, Italic, Underline, Link, List, ListOrdered, Heading1, Heading2, AlignLeft, AlignCenter, Image as ImageIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface RichTextEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

/**
 * RichTextEditor — lightweight rich text editor with toolbar.
 * Uses contentEditable for simplicity, stores HTML output.
 * Supports: bold, italic, underline, links, lists, headings, alignment, images.
 */
export default function RichTextEditor({ value, onChange, placeholder = 'Write your message...', className }: RichTextEditorProps) {
  const editorRef = useRef<HTMLDivElement>(null);
  const [isFocused, setIsFocused] = useState(false);

  const execCommand = useCallback((command: string, value?: string) => {
    document.execCommand(command, false, value);
    if (editorRef.current) {
      onChange(editorRef.current.innerHTML);
    }
  }, [onChange]);

  const handleInsertLink = () => {
    const url = prompt('Enter URL:');
    if (url) {
      execCommand('createLink', url);
    }
  };

  const handleInsertImage = () => {
    const url = prompt('Enter image URL:');
    if (url) {
      execCommand('insertImage', url);
    }
  };

  const handleInput = () => {
    if (editorRef.current) {
      onChange(editorRef.current.innerHTML);
    }
  };

  const handleFocus = () => setIsFocused(true);
  const handleBlur = () => setIsFocused(false);

  return (
    <div className={cn('rounded-xl border border-border bg-card overflow-hidden', isFocused && 'ring-2 ring-primary/40', className)}>
      {/* Toolbar */}
      <div className="flex items-center gap-1 p-2 border-b border-border bg-secondary/30 flex-wrap">
        <button
          type="button"
          onClick={() => execCommand('bold')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Bold"
        >
          <Bold className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => execCommand('italic')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Italic"
        >
          <Italic className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => execCommand('underline')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Underline"
        >
          <Underline className="w-4 h-4" />
        </button>
        
        <div className="w-px h-5 bg-border mx-1" />
        
        <button
          type="button"
          onClick={handleInsertLink}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Insert Link"
        >
          <Link className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={handleInsertImage}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Insert Image"
        >
          <ImageIcon className="w-4 h-4" />
        </button>
        
        <div className="w-px h-5 bg-border mx-1" />
        
        <button
          type="button"
          onClick={() => execCommand('formatBlock', '<h1>')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Heading 1"
        >
          <Heading1 className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => execCommand('formatBlock', '<h2>')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Heading 2"
        >
          <Heading2 className="w-4 h-4" />
        </button>
        
        <div className="w-px h-5 bg-border mx-1" />
        
        <button
          type="button"
          onClick={() => execCommand('insertUnorderedList')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Bullet List"
        >
          <List className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => execCommand('insertOrderedList')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Numbered List"
        >
          <ListOrdered className="w-4 h-4" />
        </button>
        
        <div className="w-px h-5 bg-border mx-1" />
        
        <button
          type="button"
          onClick={() => execCommand('justifyLeft')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Align Left"
        >
          <AlignLeft className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => execCommand('justifyCenter')}
          className="p-1.5 rounded hover:bg-secondary transition"
          title="Align Center"
        >
          <AlignCenter className="w-4 h-4" />
        </button>
      </div>

      {/* Editor */}
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        onInput={handleInput}
        onFocus={handleFocus}
        onBlur={handleBlur}
        dangerouslySetInnerHTML={{ __html: value }}
        className="min-h-[120px] max-h-[400px] overflow-y-auto p-3 text-sm text-foreground focus:outline-none prose prose-sm max-w-none"
        style={{
          lineHeight: '1.6',
        }}
        data-placeholder={placeholder}
      />

      <style>{`
        [contenteditable]:empty:before {
          content: attr(data-placeholder);
          color: hsl(var(--muted-foreground));
          pointer-events: none;
        }
        [contenteditable] h1 {
          font-size: 1.5rem;
          font-weight: 700;
          margin: 0.5rem 0;
        }
        [contenteditable] h2 {
          font-size: 1.25rem;
          font-weight: 600;
          margin: 0.5rem 0;
        }
        [contenteditable] ul, [contenteditable] ol {
          margin: 0.5rem 0;
          padding-left: 1.5rem;
        }
        [contenteditable] li {
          margin: 0.25rem 0;
        }
        [contenteditable] a {
          color: hsl(var(--primary));
          text-decoration: underline;
        }
        [contenteditable] img {
          max-width: 100%;
          height: auto;
          border-radius: 0.5rem;
          margin: 0.5rem 0;
        }
      `}</style>
    </div>
  );
}
