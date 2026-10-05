import { useState, useRef, useCallback, useEffect } from 'react';
import { UploadCloud, X, Loader2, ImageOff, Link2 } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';
import { msg } from '@/lib/messages';

const MAX_SIZE = 5 * 1024 * 1024; // 5MB
const ACCEPTED = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];

/**
 * Admin image field.
 *
 * TWO ways to fill it, because the two failure modes were indistinguishable
 * before and both looked like "the upload button is broken":
 *
 *   1. Direct upload — the browser signs and posts the file straight to
 *      Cloudinary using a short-lived signature from POST /upload/signature.
 *      Needs CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET on the server; when
 *      they are absent the endpoint answers 503 and we say so, naming the
 *      variables, instead of "Upload failed. Please try again."
 *   2. Paste a URL — always available, and the only option that still works
 *      when Cloudinary is not configured. Every create form that requires an
 *      image (storefront sections, banners, share templates) was a dead end
 *      without it: the API rejects the row with "image_url is required" and
 *      there was no way to supply one.
 */
export default function ImageUploader({ value, onChange, folder = 'general', label = 'Image' }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<{ text: string; hint?: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [urlMode, setUrlMode] = useState(false);
  const [urlDraft, setUrlDraft] = useState('');
  const inputRef = useRef(null);
  // Ask the server once, on mount, whether direct upload exists at all. Without
  // this the only way to learn Cloudinary is unconfigured was to pick a file,
  // wait for the round trip, and read a failure toast — which is exactly what
  // made every image field look like a broken button.
  const [status, setStatus] = useState<{ configured: boolean; missing?: string[] } | null>(null);
  useEffect(() => {
    let alive = true;
    apiClient
      .get('/upload/status')
      .then((r: any) => {
        if (!alive || !r) return;
        setStatus({ configured: r.configured !== false, missing: r.missing || [] });
        if (r.configured === false && !value) setUrlMode(true);
      })
      .catch(() => { if (alive) setStatus({ configured: true, missing: [] }); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFile = useCallback(
    async (file) => {
      setError(null);
      if (!file) return;
      const type = (file.type || '').toLowerCase();
      if (!ACCEPTED.includes(type)) {
        setError({ text: msg('FE_IMAGE_UPLOADER_PLEASE_UPLOAD_PNG_JPG_OR_WEBP', 'Please upload PNG, JPG, or WEBP') });
        return;
      }
      if (file.size > MAX_SIZE) {
        setError({ text: msg('FE_IMAGE_UPLOADER_FILE_SIZE_EXCEEDS_5_MB_LIMIT', 'File size exceeds 5MB limit') });
        return;
      }
      setUploading(true);
      try {
        // 1. Request a signed payload from the backend (POST /api/upload/signature:
        //    @require_auth — admins may target any folder, everyone else is scoped to
        //    profile_photos/<own user id> by app/routes/uploads.py).
        const sigRes = await apiClient.post('/upload/signature', { folder });
        const { signature, timestamp, api_key, cloud_name, folder: signedFolder } =
          sigRes;

        // 2. Read the file as a base64 data URL for direct upload.
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });

        // 3. Upload straight to Cloudinary.
        const form = new FormData();
        form.append('file', base64);
        form.append('api_key', api_key);
        form.append('timestamp', String(timestamp));
        form.append('signature', signature);
        form.append('folder', signedFolder);

        const cloudRes = await fetch(
          `https://api.cloudinary.com/v1_1/${cloud_name}/image/upload`,
          { method: 'POST', body: form }
        );
        if (!cloudRes.ok) {
          const detail = await cloudRes.json().catch(() => null);
          throw Object.assign(
            new Error(detail?.error?.message || msg('FE_IMAGE_UPLOADER_UPLOAD_FAILED', 'Upload failed')),
            { status: cloudRes.status, detail }
          );
        }
        const cloudData = await cloudRes.json();

        // 4. Hand the secure URL back to the parent form.
        onChange(cloudData.secure_url);
        setUrlMode(false);
      } catch (e) {
        // Surface what actually went wrong. apiClient puts the server's `error`
        // text on `message` and the raw body on `detail`, so a 503 from
        // /upload/signature arrives here with the missing-variable hint.
        const text = e?.message || msg('FE_IMAGE_UPLOADER_UPLOAD_FAILED_PLEASE_TRY_AGAIN', 'Upload failed. Please try again.');
        setError({ text, hint: e?.detail?.hint });
        // Uploading is unavailable right now — reveal the URL field so this
        // form is never a dead end.
        if (e?.status === 503 || e?.status === 501) setUrlMode(true);
      } finally {
        setUploading(false);
      }
    },
    [folder, onChange]
  );

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const remove = () => {
    setError(null);
    onChange('');
    if (inputRef.current) inputRef.current.value = '';
  };

  const applyUrl = () => {
    const url = urlDraft.trim();
    if (!url) return;
    if (!/^https?:\/\/\S+$/i.test(url)) {
      setError({ text: msg('FE_IMAGE_UPLOADER_ENTER_A_FULL_IMAGE_URL', 'Enter a full image URL starting with http:// or https://') });
      return;
    }
    setError(null);
    onChange(url);
    setUrlDraft('');
    setUrlMode(false);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="w-full">
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />

      {value ? (
        <div className="relative rounded-xl overflow-hidden border border-border group">
          <img src={value} alt={label} loading="lazy" decoding="async" className="w-full h-40 object-cover" />
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="opacity-0 group-hover:opacity-100 transition-opacity px-3 py-1.5 rounded-full bg-white/90 text-foreground text-xs font-bold flex items-center gap-1 disabled:opacity-50"
            >
              <UploadCloud className="w-3.5 h-3.5" /> Replace
            </button>
            <button
              type="button"
              onClick={remove}
              disabled={uploading}
              className="opacity-0 group-hover:opacity-100 transition-opacity px-3 py-1.5 rounded-full bg-red-600 text-white text-xs font-bold flex items-center gap-1 disabled:opacity-50"
            >
              <X className="w-3.5 h-3.5" /> Remove
            </button>
          </div>
          {uploading && (
            <div className="absolute inset-0 bg-white/70 flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-primary animate-spin" />
            </div>
          )}
        </div>
      ) : (
        <div
          onClick={() => !uploading && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`flex flex-col items-center justify-center gap-2 h-40 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
            dragging ? 'border-primary/60 bg-primary/10' : 'border-border bg-muted hover:border-primary/40 hover:bg-primary/10/40'
          } ${uploading ? 'pointer-events-none' : ''}`}
        >
          {uploading ? (
            <>
              <Loader2 className="w-6 h-6 text-primary animate-spin" />
              <span className="text-xs text-muted-foreground font-semibold">Uploading…</span>
            </>
          ) : (
            <>
              <div className="w-10 h-10 rounded-full bg-primary/15 flex items-center justify-center">
                <UploadCloud className="w-5 h-5 text-primary" />
              </div>
              <div className="text-xs font-bold text-foreground">Upload {label}</div>
              <div className="text-[10px] text-muted-foreground">Drag & drop or click · PNG, JPG, WEBP · max 5MB</div>
            </>
          )}
        </div>
      )}

      {status && status.configured === false && (
        <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-amber-700 font-semibold">
          <ImageOff className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span className="min-w-0 break-words">
            {msg('FE_IMAGE_UPLOADER_FILE_UPLOAD_OFF', 'File upload is off')} —{' '}
            {msg('FE_IMAGE_UPLOADER_MISSING_SERVER_SETTING', 'missing server setting')}{' '}
            <span className="font-mono break-all">{(status.missing || []).join(', ')}</span>.{' '}
            {msg('FE_IMAGE_UPLOADER_PASTE_A_URL_INSTEAD', 'Paste an image URL instead.')}
          </span>
        </div>
      )}

      {/* Paste-a-URL fallback — always reachable, auto-opened when the server
          says uploads are not configured, so no image field is ever a dead end. */}
      <button
        type="button"
        onClick={() => setUrlMode((v) => !v)}
        className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline"
      >
        <Link2 className="w-3 h-3" /> {urlMode ? 'Hide URL field' : 'Use an image URL instead'}
      </button>
      {urlMode && (
        <div className="mt-1.5 flex gap-1.5">
          <input
            value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                applyUrl();
              }
            }}
            placeholder="https://…/image.jpg"
            className="flex-1 min-w-0 p-2 rounded-xl border border-border text-xs focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <button
            type="button"
            onClick={applyUrl}
            className="shrink-0 px-3 py-2 rounded-xl bg-secondary text-secondary-foreground text-xs font-bold active:scale-95 transition"
          >
            Use
          </button>
        </div>
      )}

      {error && (
        <div className="mt-1.5 flex items-start gap-1.5 text-xs text-red-600 font-semibold">
          <ImageOff className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span className="min-w-0 break-words">
            {error.text}
            {error.hint && <span className="block font-normal text-red-500 mt-0.5">{error.hint}</span>}
          </span>
        </div>
      )}
    </div>
  );
}
