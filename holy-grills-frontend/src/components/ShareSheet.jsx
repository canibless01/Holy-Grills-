import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Share2, Copy, Check, Loader2 } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import ModalPortal from '@/components/ModalPortal';

/**
 * ShareSheet — frontend-only share-with-image flow (see Confirmed Business
 * Logic · Share With Image). On open it:
 *   1. Fetches the admin-uploaded base template (GET /storefront/sections?
 *      section_type=share_template).
 *   2. Overlays the dynamic headline / value / caption onto it via a canvas.
 *   3. Offers the native Web Share API (image file + caption + link) where
 *      supported, then platform-specific URLs (WhatsApp / Twitter / Facebook)
 *      and copy-to-clipboard as fallback.
 *
 * For order shares, POST /api/orders/{id}/share is called to record the share
 * and award 25 HP (pending). Referral / rank shares use the referral link +
 * code only (no backend call).
 *
 * Props: open, onClose, type ('order'|'referral'|'achievement'|'rank'),
 *        payload ({ orderId, headline, value, caption, link }) .
 */
const PLATFORMS = [
  { id: 'whatsapp', label: 'WhatsApp', color: 'bg-green-500', url: (text, url) => `https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}` },
  { id: 'twitter', label: 'Twitter', color: 'bg-sky-500', url: (text, url) => `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}` },
  { id: 'facebook', label: 'Facebook', color: 'bg-blue-600', url: (text, url) => `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}&quote=${encodeURIComponent(text)}` },
  { id: 'instagram', label: 'Instagram', color: 'bg-pink-500', url: (text, url) => `https://www.instagram.com/` },
];

export default function ShareSheet({ open, onClose, type = 'referral', templateKey = null, payload = {} }) {
  const { refreshHp } = useHolyGrill();
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const [busy, setBusy] = useState(true);
  [canvasRef, imgRef]; // satisfy linter refs usage
  const [dataUrl, setDataUrl] = useState(null);
  const [blob, setBlob] = useState(null);
  const [copied, setCopied] = useState(false);
  const [recorded, setRecorded] = useState(false);

  const caption = payload.caption || '';
  const link = payload.link || (typeof window !== 'undefined' ? window.location.origin : '');
  const shareText = `${payload.headline ? payload.headline + ' · ' : ''}${caption}`;

  // Compose the shareable image onto a canvas: draw the base template, then
  // overlay the dynamic headline / value / caption in the brand palette.
  const compose = useCallback(async () => {
    setBusy(true);
    try {
      const sections = await mockApi.storefront.getSections({ section_type: 'share_template' }).catch(() => []);
      // Each share surface (order confirmation, Hall of Fame, …) has its own
      // template, distinguished by the section's `key` — same API, own upload.
      const list = Array.isArray(sections) ? sections : [];
      const tpl = (templateKey && list.find((s) => (s.key || s.content?.key) === templateKey)) || list[0] || null;
      const baseImg = tpl?.image_url || tpl?.content?.image_url || tpl?.content?.base_image_url || tpl?.content?.image || '';
      const canvas = document.createElement('canvas');
      const W = 1080, H = 1080;
      canvas.width = W; canvas.height = H;
      const ctx = canvas.getContext('2d');
      // Background — flame gradient fill as the fallback base.
      const g = ctx.createLinearGradient(0, 0, W, H);
      g.addColorStop(0, '#6B1500'); g.addColorStop(1, '#2A0500');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

      if (baseImg) {
        try {
          const img = await new Promise((res, rej) => {
            const i = new Image();
            i.crossOrigin = 'anonymous';
            i.onload = () => res(i);
            i.onerror = rej;
            i.src = baseImg;
          });
          // cover-fit
          const scale = Math.max(W / img.width, H / img.height);
          const dw = img.width * scale, dh = img.height * scale;
          ctx.drawImage(img, (W - dw) / 2, (H - dh) / 2, dw, dh);
          // darken for text legibility
          ctx.fillStyle = 'rgba(20,5,0,0.45)'; ctx.fillRect(0, 0, W, H);
        } catch { /* image failed → keep gradient base */ }
      }

      // Dynamic text overlay.
      ctx.textAlign = 'center';
      ctx.fillStyle = '#FFC251';
      ctx.font = 'bold 64px Georgia, serif';
      if (payload.headline) ctx.fillText(payload.headline, W / 2, 220);
      if (payload.value) {
        ctx.fillStyle = '#FFF3DA';
        ctx.font = 'bold 120px Georgia, serif';
        ctx.fillText(String(payload.value), W / 2, 560);
      }
      // caption — wrap into lines lower on the canvas
      ctx.fillStyle = '#FFF3DA';
      ctx.font = '36px Georgia, serif';
      if (caption) {
        const words = caption.split(' ');
        const maxW = W - 160;
        let line = '', y = 720;
        for (let i = 0; i < words.length; i++) {
          const test = line ? line + ' ' + words[i] : words[i];
          if (ctx.measureText(test).width > maxW) {
            ctx.fillText(line, W / 2, y); line = words[i]; y += 48;
            if (y > H - 120) break;
          } else { line = test; }
        }
        if (line && y <= H - 120) ctx.fillText(line, W / 2, y);
      }
      // brand mark
      ctx.fillStyle = '#FFC251';
      ctx.font = 'bold 40px Georgia, serif';
      ctx.fillText('Holy Grills 🔥', W / 2, H - 60);

      canvas.toBlob((b) => {
        if (b) { setBlob(b); setDataUrl(URL.createObjectURL(b)); }
        else setDataUrl(canvas.toDataURL('image/png'));
        setBusy(false);
      }, 'image/png');
    } catch (e) {
      console.error(e);
      setBusy(false);
    }
  }, [payload.headline, payload.value, caption, templateKey]);

  useEffect(() => {
    if (open) { setRecorded(false); compose(); }
  }, [open, compose]);

  // Record an order share once so the 25 HP (pending) is awarded.
  const recordOrderShare = useCallback(async (platform) => {
    if (type !== 'order' || !payload.orderId || recorded) return;
    try {
      await mockApi.orders.share(payload.orderId, { platform });
      setRecorded(true);
      toast({ title: 'Shared ❤️‍🔥', description: 'Thanks for sharing. HP lands in your pending balance.' });
      refreshHp?.();
    } catch { /* ignore — still let the user share */ }
  }, [type, payload.orderId, recorded, refreshHp]);

  const nativeShare = async () => {
    recordOrderShare('native');
    try {
      if (blob && navigator.canShare && navigator.canShare({ files: [new File([blob], 'holygrills-share.png', { type: 'image/png' })] })) {
        await navigator.share({ files: [new File([blob], 'holygrills-share.png', { type: 'image/png' })], title: payload.headline || 'Holy Grills', text: shareText, url: link });
        return;
      }
      if (navigator.share) { await navigator.share({ title: payload.headline || 'Holy Grills', text: shareText, url: link }); return; }
    } catch (e) { /* user cancelled or unsupported */ }
    copyLink();
  };

  const openPlatform = (p) => {
    recordOrderShare(p.id);
    window.open(p.url(shareText, link), '_blank', 'noopener,noreferrer');
  };

  const copyLink = () => {
    navigator.clipboard?.writeText(`${shareText} ${link}`.trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <AnimatePresence>
      {open && (
        <ModalPortal>
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-lg flex items-end sm:items-center justify-center p-0 sm:p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 40, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 220, damping: 26 }}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-t-3xl sm:rounded-3xl w-full max-w-md p-5 pb-8"
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-heading font-bold text-base text-foreground flex items-center gap-2"><Share2 className="w-5 h-5 text-primary" /> Share</h3>
              <button onClick={onClose} className="p-1.5 rounded-full hover:bg-secondary"><X className="w-5 h-5 text-muted-foreground" /></button>
            </div>

            {/* Composed share image preview */}
            <div className="rounded-2xl overflow-hidden border border-border bg-secondary aspect-square mb-4 flex items-center justify-center">
              {busy ? (
                <div className="flex flex-col items-center text-muted-foreground"><Loader2 className="w-8 h-8 animate-spin mb-2" /><span className="text-xs">Composing your share card…</span></div>
              ) : dataUrl ? (
                <img src={dataUrl} alt="Share card" className="w-full h-full object-cover" />
              ) : null}
            </div>

            {/* Caption + link (editable in most platforms) */}
            <div className="rounded-xl bg-muted border border-border p-3 mb-3">
              {payload.headline && <div className="font-heading font-bold text-sm text-foreground">{payload.headline}{payload.value ? ` · ${payload.value}` : ''}</div>}
              {caption && <div className="text-xs text-muted-foreground mt-0.5">{caption}</div>}
              <div className="text-[11px] text-primary font-semibold mt-1 truncate">{link}</div>
            </div>

            {/* Native share (image) */}
            <button
              onClick={nativeShare}
              disabled={busy}
              className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm flex items-center justify-center gap-2 mb-3 disabled:opacity-50"
            >
              <Share2 className="w-4 h-4" /> Share Image via…
            </button>

            {/* Platform shortcuts */}
            <div className="grid grid-cols-4 gap-2 mb-3">
              {PLATFORMS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => openPlatform(p)}
                  className="flex flex-col items-center gap-1.5"
                >
                  <span className={`w-12 h-12 rounded-full ${p.color} flex items-center justify-center text-white text-[10px] font-bold`}>{p.label.slice(0, 2)}</span>
                  <span className="text-[10px] text-muted-foreground font-medium">{p.label}</span>
                </button>
              ))}
            </div>

            {/* Copy fallback */}
            <button onClick={copyLink} className="w-full py-2.5 rounded-full bg-muted border border-border text-foreground text-xs font-bold flex items-center justify-center gap-1.5">
              {copied ? <><Check className="w-4 h-4 text-green-600" /> Copied!</> : <><Copy className="w-4 h-4" /> Copy caption + link</>}
            </button>
          </motion.div>
        </motion.div>
        </ModalPortal>
      )}
    </AnimatePresence>
  );
}