import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { liveApi } from '@/lib/liveApi';
import { safeCallHref } from '@/lib/safeNavigation';
import { isAuthenticated, clearTokens } from '@/lib/apiClient';
import { useSound } from '@/lib/SoundProvider';
import { toast } from '@/components/ui/use-toast';

/**
 * All data + action logic for the Rider panel, isolated from its UI.
 * Polls the active delivery batch, detects new orders (sound alert), and
 * exposes the pickup/delivery/call/availability handlers the rider screen needs.
 */
export function useRiderData() {
  const [batch, setBatch] = useState(null);
  const [earnings, setEarnings] = useState(null);
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [online, setOnline] = useState(true);
  const [period, setPeriod] = useState('week');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [calling, setCalling] = useState(null);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState(null);
  const [authed] = useState(isAuthenticated());
  const navigate = useNavigate();
  const { play } = useSound();

  const prevOrderIds = useRef(new Set());
  const initialized = useRef(false);

  const applyBatch = (b) => {
    setBatch(b);
    const orderIds = new Set((b?.orders || []).map((o) => o.id));
    if (initialized.current) {
      const newIds = [...orderIds].filter((id) => !prevOrderIds.current.has(id));
      if (newIds.length > 0) play('push_received');
    }
    prevOrderIds.current = orderIds;
    initialized.current = true;
  };

  const loadBatch = async () => {
    try {
      const b = await liveApi.riders.getMyBatch();
      applyBatch(b);
    } catch (e) { /* ignore poll errors */ }
  };

  useEffect(() => {
    if (!authed) { setLoading(false); return; }
    const init = async () => {
      try {
        const [b, e, s, h] = await Promise.all([
          liveApi.riders.getMyBatch(),
          liveApi.riders.getEarnings({ period: 'week' }),
          liveApi.riders.getStats(),
          liveApi.riders.getHistory(),
        ]);
        applyBatch(b);
        setEarnings(e); setStats(s); setHistory(h);
        setOnline(Boolean(s?.is_available));
      } catch (e) {
        console.error(e);
        setError('Could not load rider dashboard. Check your connection and try again.');
      }
      setLoading(false);
    };
    init();
    const interval = setInterval(loadBatch, 15000);
    return () => clearInterval(interval);
  }, [authed]);

  // Rider live tracking — POST /riders/location-update on an interval while the
  // rider is online. Uses the geolocation watch if available, otherwise a polled
  // getCurrentPosition. Failures are silent so a bad GPS fix never blocks the
  // dispatch UI; the backend simply won't get a fresh ping until the next one.
  useEffect(() => {
    if (!authed || !online || !navigator.geolocation) return undefined;
    let last = null;
    const send = (lat, lng) => {
      // Throttle to one update per ~10s + only when the pin moved >15m.
      const now = Date.now();
      if (last && now - last.t < 9000 && last.lat != null) {
        const moved = Math.hypot(lat - last.lat, lng - last.lng);
        if (moved < 0.00015) return; // ~15m in degrees
      }
      last = { lat, lng, t: now };
      // Backend reads location_lat / location_lng (not lat/lng) — the old body
      // was silently dropped, so live tracking never updated.
      liveApi.riders.locationUpdate({ location_lat: lat, location_lng: lng }).catch(() => { /* silent */ });
    };
    const watchId = navigator.geolocation.watchPosition(
      (pos) => send(pos.coords.latitude, pos.coords.longitude),
      () => { /* GPS denied — fall back to poll below */ },
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 }
    );
    // Poll fallback in case watchPosition never fires (some browsers stall).
    const poll = setInterval(() => {
      navigator.geolocation.getCurrentPosition(
        (pos) => send(pos.coords.latitude, pos.coords.longitude),
        () => {},
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 8000 }
      );
    }, 20000);
    return () => { navigator.geolocation.clearWatch(watchId); clearInterval(poll); };
  }, [authed, online]);

  const changePeriod = async (p) => {
    setPeriod(p);
    try {
      const e = await liveApi.riders.getEarnings({ period: p });
      setEarnings(e);
    } catch (e2) { /* ignore */ }
  };

  const handleAction = async (orderId, action) => {
    setActionLoading(orderId);
    try {
      if (action === 'pickup') await liveApi.riders.pickup(orderId);
      else if (action === 'deliver') await liveApi.riders.deliver(orderId);
      else if (action === 'attempt') await liveApi.riders.attempt(orderId, { notes: 'Customer not reachable at delivery' });
      toast({ title: action === 'pickup' ? 'Pickup confirmed' : action === 'deliver' ? 'Delivery completed — HP awarded to customer' : 'Delivery attempted' });
      await loadBatch();
    } catch (e) {
      toast({ title: 'Action failed', description: e.message, variant: 'destructive' });
    }
    setActionLoading(null);
  };

  const handleCall = async (orderId) => {
    setCalling(orderId);
    try {
      const link = await liveApi.riders.getCallLink(orderId);
      // S7 — only tel:/https: from the backend is followed.
      const href = safeCallHref(link && (link.call_link || link.call_url));
      if (!href) throw new Error('No phone number available');
      window.location.href = href;
    } catch (e) {
      toast({ title: 'Call failed', description: e?.message || 'No phone number available', variant: 'destructive' });
    }
    setCalling(null);
  };

  const navigateTo = (address) => {
    window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent((address || '') + ', FUTA, Akure')}`, '_blank');
  };

  const toggleOnline = async () => {
    const newStatus = !online;
    if (newStatus) {
      if (!navigator.geolocation) {
        toast({ title: 'Location unsupported', description: 'This device cannot share GPS.', variant: 'destructive' });
        return;
      }
      setToggling(true);
      // Two attempts. A single high-accuracy request with a short timeout is
      // what produced the false "Location required" error: indoors the GPS
      // fix takes longer than the timeout and the request fails even though
      // location is enabled. Try a fast network fix first, then a precise one.
      const attempt = (opts) => new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, opts));
      let pos = null;
      let lastErr = null;
      try {
        pos = await attempt({ enableHighAccuracy: false, timeout: 15000, maximumAge: 120000 });
      } catch (e) {
        lastErr = e;
        try {
          pos = await attempt({ enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
        } catch (e2) { lastErr = e2; }
      }
      if (!pos) {
        setToggling(false);
        const code = lastErr && lastErr.code;
        toast({
          title: 'Could not get your location',
          description: code === 1
            ? 'Location is blocked for this site. Allow location access in your browser settings, then try again.'
            : code === 3
              ? 'Getting a GPS fix took too long. Step outside or near a window and try again.'
              : 'Your device could not get a GPS fix right now. Try again in a moment.',
          variant: 'destructive',
        });
        return;
      }
      setOnline(true);
      try {
        await liveApi.riders.setAvailability({ is_available: true, location_lat: pos.coords.latitude, location_lng: pos.coords.longitude });
        toast({ title: 'You are online', description: 'GPS shared with dispatch.' });
      } catch (e) {
        setOnline(false);
        toast({ title: 'Could not go online', description: e.message, variant: 'destructive' });
      }
      setToggling(false);
    } else {
      setOnline(false);
      try {
        await liveApi.riders.setAvailability({ is_available: false });
        toast({ title: 'You are offline' });
      } catch (e) {
        setOnline(true);
        toast({ title: 'Could not go offline', description: e.message, variant: 'destructive' });
      }
    }
  };

  const handleSignOut = () => {
    clearTokens();
    navigate('/');
  };

  return {
    authed, loading, error, batch, earnings, stats, history, online, period,
    actionLoading, calling, toggling, changePeriod, handleAction, handleCall, navigateTo, toggleOnline, handleSignOut,
  };
}