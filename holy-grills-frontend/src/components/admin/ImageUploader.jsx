import React, { useState, useRef, useCallback } from 'react';
import { UploadCloud, X, Loader2, ImageOff } from 'lucide-react';
import { apiClient } from '@/lib/apiClient';

const MAX_SIZE = 5 * 1024 * 1024; // 5MB
const ACCEPTED = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];

export default function ImageUploader({ value, onChange, folder = 'general', label = 'Image' }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleFile = useCallback(
    async (file) => {
      setError('');
      if (!file) return;
      const type = (file.type || '').toLowerCase();
      if (!ACCEPTED.includes(type)) {
        setError('Please upload PNG, JPG, or WEBP');
        return;
      }
      if (file.size > MAX_SIZE) {
        setError('File size exceeds 5MB limit');
        return;
      }
      setUploading(true);
      try {
        // 1. Request a signed payload from the admin-only live API endpoint
        //    (POST /api/upload/signature, @require_role("admin")).
        const sigRes = await apiClient.post('/upload/signature', { folder });
        const { signature, timestamp, api_key, cloud_name, folder: signedFolder } =
          sigRes;

        // 2. Read the file as a base64 data URL for direct upload.
        const base64 = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
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
        if (!cloudRes.ok) throw new Error('Upload failed');
        const cloudData = await cloudRes.json();

        // 4. Hand the secure URL back to the parent form.
        onChange(cloudData.secure_url);
      } catch (e) {
        setError('Upload failed. Please try again.');
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
    setError('');
    onChange('');
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
          <img src={value} alt={label} className="w-full h-40 object-cover" />
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

      {error && (
        <div className="mt-1.5 flex items-center gap-1.5 text-xs text-red-600 font-semibold">
          <ImageOff className="w-3.5 h-3.5" /> {error}
        </div>
      )}
    </div>
  );
}