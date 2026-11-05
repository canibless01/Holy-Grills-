import { Plus, X, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CTABlock {
  id: string;
  label: string;
  url: string;
  style: 'primary' | 'secondary';
}

interface CTABlockEditorProps {
  value: CTABlock[];
  onChange: (blocks: CTABlock[]) => void;
  className?: string;
}

/**
 * CTABlockEditor — manages multiple CTA buttons in the composer.
 * Each block has a label, URL, and style (primary/secondary).
 */
export default function CTABlockEditor({ value, onChange, className }: CTABlockEditorProps) {
  const addBlock = () => {
    const newBlock: CTABlock = {
      id: `cta-${Date.now()}`,
      label: '',
      url: '',
      style: 'primary',
    };
    onChange([...value, newBlock]);
  };

  const updateBlock = (id: string, updates: Partial<CTABlock>) => {
    onChange(value.map(block => block.id === id ? { ...block, ...updates } : block));
  };

  const removeBlock = (id: string) => {
    onChange(value.filter(block => block.id !== id));
  };

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
          Call-to-Action Buttons
        </label>
        <button
          type="button"
          onClick={addBlock}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 transition"
        >
          <Plus className="w-3 h-3" />
          Add CTA
        </button>
      </div>

      {value.length === 0 && (
        <p className="text-xs text-muted-foreground italic">
          No CTA buttons added. Click "Add CTA" to add buttons to your message.
        </p>
      )}

      <div className="space-y-2">
        {value.map((block, index) => (
          <div key={block.id} className="flex items-start gap-2 p-3 rounded-xl border border-border bg-secondary/30">
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-muted-foreground">#{index + 1}</span>
                <input
                  type="text"
                  value={block.label}
                  onChange={(e) => updateBlock(block.id, { label: e.target.value })}
                  placeholder="Button label (e.g., Order Now)"
                  className="flex-1 px-2 py-1.5 rounded-lg border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
                <select
                  value={block.style}
                  onChange={(e) => updateBlock(block.id, { style: e.target.value as 'primary' | 'secondary' })}
                  className="px-2 py-1.5 rounded-lg border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
                >
                  <option value="primary">Primary</option>
                  <option value="secondary">Secondary</option>
                </select>
                <button
                  type="button"
                  onClick={() => removeBlock(block.id)}
                  className="p-1.5 rounded-lg hover:bg-destructive/10 text-destructive transition"
                  title="Remove CTA"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center gap-2">
                <Link2 className="w-4 h-4 text-muted-foreground" />
                <input
                  type="url"
                  value={block.url}
                  onChange={(e) => updateBlock(block.id, { url: e.target.value })}
                  placeholder="https://holygrills.online/menu"
                  className="flex-1 px-2 py-1.5 rounded-lg border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export type { CTABlock };
