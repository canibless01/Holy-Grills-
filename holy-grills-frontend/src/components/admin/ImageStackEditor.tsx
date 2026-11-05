import { Plus, X, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import ImageUploader from './ImageUploader';

interface ImageBlock {
  id: string;
  url: string;
  alt: string;
  link?: string;
}

interface ImageStackEditorProps {
  value: ImageBlock[];
  onChange: (images: ImageBlock[]) => void;
  className?: string;
  maxImages?: number;
}

/**
 * ImageStackEditor — manages 2-6 full-width images in the composer.
 * Each image can have alt text and an optional link.
 */
export default function ImageStackEditor({ value, onChange, className, maxImages = 6 }: ImageStackEditorProps) {
  const addImage = () => {
    if (value.length >= maxImages) return;
    const newImage: ImageBlock = {
      id: `img-${Date.now()}`,
      url: '',
      alt: '',
      link: '',
    };
    onChange([...value, newImage]);
  };

  const updateImage = (id: string, updates: Partial<ImageBlock>) => {
    onChange(value.map(img => img.id === id ? { ...img, ...updates } : img));
  };

  const removeImage = (id: string) => {
    onChange(value.filter(img => img.id !== id));
  };

  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
          Image Stack ({value.length}/{maxImages})
        </label>
        {value.length < maxImages && (
          <button
            type="button"
            onClick={addImage}
            className="flex items-center gap-1 px-2 py-1 rounded-lg bg-primary/10 text-primary text-xs font-bold hover:bg-primary/20 transition"
          >
            <Plus className="w-3 h-3" />
            Add Image
          </button>
        )}
      </div>

      {value.length === 0 && (
        <p className="text-xs text-muted-foreground italic">
          No images added. Click "Add Image" to add images to your message.
        </p>
      )}

      <div className="space-y-2">
        {value.map((image, index) => (
          <div key={image.id} className="flex items-start gap-2 p-3 rounded-xl border border-border bg-secondary/30">
            <div className="flex-1 space-y-2">
              <div className="flex items-start gap-2">
                <span className="text-xs font-bold text-muted-foreground mt-2">#{index + 1}</span>
                <div className="flex-1 min-w-0">
                  {/* Same Cloudinary uploader every other admin image field uses —
                      a bare URL box meant "upload an image" required a link, which is
                      exactly what the campaign page used to demand. */}
                  <ImageUploader
                    value={image.url}
                    onChange={(url: string) => updateImage(image.id, { url })}
                    folder="campaigns"
                    label="Image"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => removeImage(image.id)}
                  className="p-1.5 rounded-lg hover:bg-destructive/10 text-destructive transition"
                  title="Remove Image"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={image.alt}
                  onChange={(e) => updateImage(image.id, { alt: e.target.value })}
                  placeholder="Alt text (visible when images are blocked)"
                  className="flex-1 px-2 py-1.5 rounded-lg border border-border text-sm bg-card focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div className="flex items-center gap-2">
                <Link2 className="w-4 h-4 text-muted-foreground" />
                <input
                  type="url"
                  value={image.link || ''}
                  onChange={(e) => updateImage(image.id, { link: e.target.value })}
                  placeholder="Optional: Click link (e.g., https://holygrills.online/menu)"
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

export type { ImageBlock };
