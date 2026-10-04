import React, { useEffect, useRef, useState } from 'react';
import { Camera, X, AlertCircle, Keyboard } from 'lucide-react';
import ModalPortal from '@/components/ModalPortal';

/**
 * EventCheckInScanner — opens the device camera and reads the venue's QR code
 * (encoded as `HG-EVT-{event_id}-{token}`) using the native BarcodeDetector API
 * where available, with a manual-token-entry fallback for unsupported browsers.
 *
 * Props:
 *  eventId  — the event id, used to validate the scanned QR.
 *  onScan   — (qrToken) => void  called once a valid token is extracted.
 */
export default function EventCheckInScanner({ eventId, onScan, onClose }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const detectorRef = useRef(null);
  const [error, setError] = useState(null);
  const [supported, setSupported] = useState(true);
  const [manual, setManual] = useState(false);
  const [manualToken, setManualToken] = useState('');
  const [scanning, setScanning] = useState(true);

  const stopCamera = () => {
    if (detectorRef.current) { cancelAnimationFrame(detectorRef.current); detectorRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
  };

  useEffect(() => {
    if (manual) { stopCamera(); return; }
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices) { setSupported(false); return; }

    let cancelled = false;
    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play().catch(() => {}); }
        const Detector = window.BarcodeDetector;
        const detector = new Detector({ formats: ['qr_code'] });
        const tick = async () => {
          if (cancelled || !videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            if (codes && codes.length) {
              const raw = codes[0].rawValue || '';
              handleRaw(raw);
              return;
            }
          } catch { /* detect throws on empty frames occasionally — keep going */ }
          detectorRef.current = requestAnimationFrame(tick);
        };
        detectorRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setError('Could not open the camera. Allow camera access or enter the token manually.');
        setSupported(false);
      }
    };
    start();
    return () => { cancelled = true; stopCamera(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manual]);

  // Parse `HG-EVT-{event_id}-{token}` → validate event → emit token.
  const handleRaw = (raw) => {
    const parts = raw.split('-'); // ['HG','EVT',eventId, ...tokenParts]
    if (parts.length < 4 || parts[0] !== 'HG' || parts[1] !== 'EVT') {
      setError('That QR code is not a Holy Grill event code.');
      stopCamera();
      return;
    }
    const scannedEventId = parts.slice(2, -1).join('-') || parts[2];
    const token = parts[parts.length - 1];
    if (scannedEventId !== eventId) {
      setError('This QR code is for a different event.');
      stopCamera();
      return;
    }
    if (!token) { setError('Invalid QR code.'); stopCamera(); return; }
    setScanning(false);
    stopCamera();
    onScan(token);
  };

  const submitManual = () => {
    const raw = manualToken.trim();
    if (!raw) return;
    handleRaw(raw.startsWith('HG-EVT-') ? raw : `HG-EVT-${eventId}-${raw}`);
  };

  return (
    // Portalled to <body>: inside the page's animated wrapper, `fixed inset-0`
    // was clipped to the wrapper so the dimmed backdrop missed the top/bottom
    // of the screen.
    <ModalPortal>
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl p-5 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-heading font-bold text-base text-foreground flex items-center gap-2"><Camera className="w-5 h-5 text-primary" /> Scan Event QR</h3>
          <button onClick={() => { stopCamera(); onClose(); }}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>

        {manual ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">Enter the token shown on the venue's QR code (the part after <code>HG-EVT-{eventId}-</code>).</p>
            <input
              value={manualToken}
              onChange={(e) => setManualToken(e.target.value)}
              placeholder="token"
              className="w-full p-3 rounded-xl border border-border text-sm font-mono focus:outline-none focus:border-primary/60"
            />
            <button onClick={submitManual} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Check In</button>
            <button onClick={() => { setManual(false); setError(null); setScanning(true); }} className="w-full text-xs text-muted-foreground font-semibold">Use camera instead</button>
          </div>
        ) : supported ? (
          <>
            <div className="relative rounded-2xl overflow-hidden bg-foreground/90 aspect-square">
              <video ref={videoRef} playsInline muted className="w-full h-full object-cover" />
              {/* Scan target overlay */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-48 h-48 border-2 border-white/80 rounded-2xl" />
              </div>
              {scanning && (
                <div className="absolute bottom-2 left-0 right-0 text-center text-[11px] text-white/80">Point at the Holy Grill QR at the entrance</div>
              )}
            </div>
            {error && (
              <div className="flex items-center gap-2 mt-3 p-2.5 rounded-xl bg-red-50 border border-red-200">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span className="text-xs text-red-800">{error}</span>
              </div>
            )}
            <button onClick={() => { setManual(true); }} className="w-full mt-3 flex items-center justify-center gap-1.5 text-xs font-semibold text-muted-foreground">
              <Keyboard className="w-3.5 h-3.5" /> Enter code manually
            </button>
          </>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span className="text-xs text-amber-800">{error || 'Your browser does not support QR scanning. Enter the code manually.'}</span>
            </div>
            <input
              value={manualToken}
              onChange={(e) => setManualToken(e.target.value)}
              placeholder="token from the QR code"
              className="w-full p-3 rounded-xl border border-border text-sm font-mono focus:outline-none focus:border-primary/60"
            />
            <button onClick={submitManual} className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">Check In</button>
          </div>
        )}
      </div>
    </div>
    </ModalPortal>
  );
}