import { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import confetti from 'canvas-confetti';
import { liveApi } from '@/lib/liveApi';
import { playSound } from '@/lib/soundManager';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { localStore } from '@/lib/storage';
import ModalPortal from '@/components/ModalPortal';
import type { ExclusiveSpinPrize, ExclusiveSpinResult } from '@/types/exclusive-spin';
import { msg, useMessages } from '@/lib/messages';

const RADIUS = 130;
const CENTER = 150;

// Brand colours for the configured prize segments.
const FALLBACK_COLORS = ['#F72B13', '#FFC251', '#FF6B1A', '#FFDD9F', '#D4200C', '#ECA829', '#FF7070', '#C4A57D', '#F2542D', '#FFB347'];

// Mix a hex colour toward white (amt > 0) or black (amt < 0) — used to give
// every segment a light-to-dark gradient so the wheel reads as a physical,
// lit object instead of flat 2D fills.
const shade = (hex, amt) => {
  const num = parseInt(hex.replace('#', ''), 16);
  const ch = (v) => Math.max(0, Math.min(255, Math.round(v)));
  const mix = (c) => (amt >= 0 ? ch(c + (255 - c) * amt) : ch(c * (1 + amt)));
  const r = mix((num >> 16) & 255);
  const g = mix((num >> 8) & 255);
  const b = mix(num & 255);
  return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
};

// Visuals follow the stored category; an unavailable pool has no mock prizes.
const buildSegments = (backendPrizes) => {
  if (!Array.isArray(backendPrizes)) return [];
  const icons = { hp: '⚡', free_delivery: '🚚', hp_multiplier: '🔥', physical: '🎁' };
  return backendPrizes.map((p, i) => ({ id: p.id, label: p.name,
    icon: icons[p.reward_config?.kind] || '🎁', color: FALLBACK_COLORS[i % FALLBACK_COLORS.length] }));
};

const polarToCartesian = (angleDeg, r) => {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: CENTER + r * Math.cos(rad), y: CENTER + r * Math.sin(rad) };
};

const describeSegment = (i, segAngle) => {
  const start = polarToCartesian(i * segAngle, RADIUS);
  const end = polarToCartesian((i + 1) * segAngle, RADIUS);
  return `M ${CENTER} ${CENTER} L ${start.x} ${start.y} A ${RADIUS} ${RADIUS} 0 0 1 ${end.x} ${end.y} Z`;
};

// Accelerate (ease-in cubic) for first 12%, then decelerate with increasing
// friction (ease-out quartic) for the rest — a real wheel losing momentum.
const easeSpin = (t) => {
  if (t < 0.12) {
    const tt = t / 0.12;
    return 0.04 * tt * tt * tt;
  }
  const tt = (t - 0.12) / 0.88;
  return 0.04 + 0.96 * (1 - Math.pow(1 - tt, 4));
};

// Display the committed receipt, including the actual credited amount.
const revealCopy = (result) => {
  const title = msg('FE_SPIN_PRIZE_WON', '{prize} won!', { prize: result.prize });
  switch (result.prize_type) {
    case 'hp': return { emoji: '⚡', title: msg('FE_SPIN_HP_WON', '+{amount} HP!', { amount: result.hp_won }), body: msg('FE_SPIN_HP_CREDITED', 'Holy Points added to your balance.') };
    case 'free_delivery': return { emoji: '🚚', title, body: msg('FE_SPIN_DELIVERY_GRANTED', 'Up to ₦{amount} in delivery fees covered on your next order.', { amount: result.delivery_cap }) };
    case 'hp_multiplier': return { emoji: '🔥', title, body: msg('FE_SPIN_MULTIPLIER_GRANTED', 'Saved: {multiplier}× food HP. Choose an order at checkout.', { multiplier: result.hp_multiplier }) };
    default: return { emoji: '🎁', title, body: msg('FE_SPIN_PHYSICAL_PENDING', 'Your campus team has your prize for fulfilment. Track its status in My Rewards.') };
  }
};

interface SpinWheelProps {
  open: boolean;
  onClose: () => void;
  onResult?: (result?: ExclusiveSpinResult) => void;
  canSpin?: boolean;
  // Optional: when omitted the wheel fetches GET /exclusive-spin itself.
  prizes?: ExclusiveSpinPrize[];
}

export default function SpinWheel({ open, onClose, onResult, canSpin = true, prizes }: SpinWheelProps) {
  useMessages();
  const { refreshHp, user } = useHolyGrill();
  const intentStorageKey = user?.id ? `hg_exclusive_spin_intent:${user.id}` : null;
  const busyRef = useRef(false);
  const openRef = useRef(open);
  openRef.current = open;
  const hasPendingIntent = !!(intentStorageKey && localStore.getItem(intentStorageKey));
  const close = () => {
    if (prize && intentStorageKey) localStore.removeItem(intentStorageKey);
    onClose();
  };
  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [prize, setPrize] = useState(null);
  const [flashing, setFlashing] = useState(false);
  const [winningIndex, setWinningIndex] = useState(-1);
  const [segments, setSegments] = useState(() => buildSegments(prizes));
  const SEG_COUNT = segments.length;
  const SEG_ANGLE = SEG_COUNT ? 360 / SEG_COUNT : 360;
  const rotRef = useRef(0);
  const rafRef = useRef(null);

  // Sync segments when the parent passes a backend prize list (Rewards already
  // fetches GET /exclusive-spin → prizes[]). Fall back to fetching it ourselves
  // when no prizes prop is supplied, so the wheel always shows the live pool.
  useEffect(() => {
    if (prizes) setSegments(buildSegments(prizes));
  }, [prizes]);

  useEffect(() => {
    if (!open || prizes) return;
    let cancelled = false;
    (async () => {
      try {
        const status = await liveApi.hp.getExclusiveSpinStatus();
        const list = Array.isArray(status?.prizes) ? status.prizes : null;
        if (!cancelled && list) setSegments(buildSegments(list));
      } catch { if (!cancelled) setSegments([]); }
    })();
    return () => { cancelled = true; };
  }, [open, prizes]);

  // Idle slow rotation — only when the user can actually spin. When unusable
  // the wheel stays static so it's not misleading.
  useEffect(() => {
    if (!open || spinning || prize || !canSpin || !segments.length) return;
    let lastTime = performance.now();
    const idle = (time) => {
      const dt = (time - lastTime) / 1000;
      lastTime = time;
      rotRef.current += 15 * dt; // 15 deg/sec
      setRotation(rotRef.current % 360);
      rafRef.current = requestAnimationFrame(idle);
    };
    rafRef.current = requestAnimationFrame(idle);
    return () => cancelAnimationFrame(rafRef.current);
  }, [open, spinning, prize, canSpin, segments.length]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      cancelAnimationFrame(rafRef.current);
      setSpinning(false);
      setPrize(null);
      setFlashing(false);
      setWinningIndex(-1);
    }
  }, [open]);

  const handleSpin = async () => {
    if (busyRef.current || (!canSpin && !hasPendingIntent) || (!segments.length && !hasPendingIntent) || !intentStorageKey) return;
    busyRef.current = true;
    setSpinning(true);
    setPrize(null);
    setFlashing(false);
    setWinningIndex(-1);
    cancelAnimationFrame(rafRef.current);
    playSound('spin_spinning');

    let apiResult;
    try {
      let intentKey = localStore.getItem(intentStorageKey);
      if (!intentKey) { intentKey = crypto.randomUUID(); localStore.setItem(intentStorageKey, intentKey); }
      apiResult = await liveApi.hp.exclusiveSpin({ intent_key: intentKey });
    } catch (e) {
      busyRef.current = false;
      setSpinning(false);
      // A definitive admission rejection spent no credit. Uncertain network
      // failures retain the request identity so the committed result can replay.
      if (e.status === 400 || e.status === 409) localStore.removeItem(intentStorageKey);
      onResult?.();
      toast({ title: msg('FE_SPIN_WHEEL_SPIN_FAILED', 'Spin failed'), description: e.message, variant: 'destructive' });
      return;
    }

    if (!openRef.current) { busyRef.current = false; setSpinning(false); return; }
    const resolved = apiResult;
    const segIndex = segments.findIndex((s) => s.id === apiResult.prize_id);
    // A pool edit after the wheel loaded cannot make it announce another segment.
    if (segIndex < 0) {
      busyRef.current = false; setSpinning(false); setPrize(resolved);
      refreshHp().catch(() => {}); onResult?.(apiResult); return;
    }

    // Calculate landing rotation: 5 full turns + offset to target segment.
    const targetCenter = segIndex * SEG_ANGLE + SEG_ANGLE / 2;
    const currentRot = rotRef.current % 360;
    const baseTarget = (360 - targetCenter) % 360;
    let delta = baseTarget - currentRot;
    if (delta < 0) delta += 360;
    const totalDelta = 360 * 5 + delta;
    const startRot = rotRef.current;
    const duration = 4500;
    const startTime = performance.now();

    const animate = (time) => {
      const elapsed = time - startTime;
      const t = Math.min(elapsed / duration, 1);
      const eased = easeSpin(t);
      const currentRot = startRot + totalDelta * eased;
      rotRef.current = currentRot;
      setRotation(currentRot % 360);

      if (t < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        // Landed — flash winning segment, then confetti + fanfare + reveal.
        busyRef.current = false;
        setSpinning(false);
        setWinningIndex(segIndex);
        setPrize(resolved);
        refreshHp().catch(() => {});

        let flashCount = 0;
        const flashInterval = setInterval(() => {
          setFlashing((prev) => !prev);
          flashCount++;
          if (flashCount >= 4) {
            clearInterval(flashInterval);
            setFlashing(false);
            playSound('spin_win');
            confetti({ particleCount: 100, spread: 70, origin: { y: 0.5 }, colors: ['#F72B13', '#FFC251', '#FFDD9F'] });
            if (onResult) onResult(apiResult);
          }
        }, 200);
      }
    };
    rafRef.current = requestAnimationFrame(animate);
  };

  if (!open) return null;

  const reveal = prize ? revealCopy(prize) : null;

  return (
    <ModalPortal>
    <div className="fixed inset-0 z-50 hg-scrim flex items-center justify-center p-4" onClick={close}>
      <div className="bg-card rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-heading font-bold text-lg text-foreground">{msg('FE_SPIN_TITLE', '🎡 Exclusive Spin')}</h3>
          <button onClick={close} aria-label={msg('FE_SPIN_CLOSE', 'Close spin wheel')}><X className="w-5 h-5 text-muted-foreground" /></button>
        </div>

        {/* Wheel — layered like a physical wheel: dark wood rim, gold band,
            gradient segments, gloss highlight, branded hub. The pointer is a
            real rendered triangle (its old colour class didn't exist in the
            Tailwind config, so no pointer ever painted). */}
        <div className="relative w-72 h-72 mx-auto mb-4">
          {/* Fixed pointer at top */}
          <div
            className="absolute top-[-2px] left-1/2 -translate-x-1/2 z-20 w-0 h-0 border-l-[11px] border-r-[11px] border-t-[20px] border-l-transparent border-r-transparent"
            style={{ borderTopColor: '#3D1200', filter: 'drop-shadow(0 2px 3px rgba(31,10,0,0.45))' }}
          />
          <svg viewBox="0 0 300 300" className="w-full h-full" style={{ transform: `rotate(${rotation}deg)`, filter: 'drop-shadow(0 10px 24px rgba(31,10,0,0.35))' }}>
            <defs>
              {segments.map((seg, i) => (
                <linearGradient key={i} id={`seg-grad-${i}`} x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor={shade(seg.color, 0.28)} />
                  <stop offset="55%" stopColor={seg.color} />
                  <stop offset="100%" stopColor={shade(seg.color, -0.22)} />
                </linearGradient>
              ))}
              <radialGradient id="hub-grad" cx="0.5" cy="0.35" r="0.8">
                <stop offset="0%" stopColor="#FFE08A" />
                <stop offset="60%" stopColor="#F2B84B" />
                <stop offset="100%" stopColor="#D89A22" />
              </radialGradient>
              <radialGradient id="rim-grad" cx="0.5" cy="0.4" r="0.75">
                <stop offset="0%" stopColor="#4A1B05" />
                <stop offset="78%" stopColor="#2A0E00" />
                <stop offset="100%" stopColor="#180700" />
              </radialGradient>
              <linearGradient id="gloss-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgba(255,255,255,0.22)" />
                <stop offset="100%" stopColor="rgba(255,255,255,0)" />
              </linearGradient>
            </defs>

            {/* Rim stack — dark wood outer, warm gold band, cream inner edge */}
            <circle cx={CENTER} cy={CENTER} r={148} fill="url(#rim-grad)" />
            <circle cx={CENTER} cy={CENTER} r={139} fill="none" stroke="#F2B84B" strokeWidth="7" />
            <circle cx={CENTER} cy={CENTER} r={134} fill="none" stroke="#FFF5F0" strokeWidth="1.5" opacity="0.85" />
            {/* Gold band bulbs — small dots around the rim */}
            {SEG_COUNT > 0 && Array.from({ length: Math.max(SEG_COUNT, 12) }).map((_, i, arr) => {
              const p = polarToCartesian((i * 360) / arr.length, 139);
              return <circle key={i} cx={p.x} cy={p.y} r="2.2" fill="#FFE9A8" opacity="0.9" />;
            })}

            {segments.map((seg, i) => {
              const isWinning = flashing && i === winningIndex;
              const labelPos = polarToCartesian(i * SEG_ANGLE + SEG_ANGLE / 2, RADIUS * 0.62);
              return (
                <g key={i}>
                  <path
                    d={SEG_COUNT === 1 ? `M ${CENTER-RADIUS} ${CENTER} a ${RADIUS} ${RADIUS} 0 1 0 ${2*RADIUS} 0 a ${RADIUS} ${RADIUS} 0 1 0 ${-2*RADIUS} 0` : describeSegment(i, SEG_ANGLE)}
                    fill={`url(#seg-grad-${i})`}
                    stroke="#FFF5F0"
                    strokeWidth="1.5"
                    style={{ opacity: isWinning ? 1 : 0.96, filter: isWinning ? 'brightness(1.45)' : 'none', transition: 'opacity 0.1s' }}
                  />
                  <text
                    x={labelPos.x}
                    y={labelPos.y}
                    fontSize="22"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.45))' }}
                  >
                    {seg.icon}
                  </text>
                </g>
              );
            })}

            {/* Gloss — a soft light sweep over the upper third, clipped to the
                wheel face (reads as varnish, not as a flat overlay) */}
            <path
              d={`M ${CENTER - RADIUS} ${CENTER} A ${RADIUS} ${RADIUS} 0 0 1 ${CENTER + RADIUS} ${CENTER} L ${CENTER + RADIUS * 0.55} ${CENTER} A ${RADIUS * 0.55} ${RADIUS * 0.55} 0 0 0 ${CENTER - RADIUS * 0.55} ${CENTER} Z`}
              fill="url(#gloss-grad)"
              pointerEvents="none"
            />

            {/* Hub — dark socket, gold dome, flame */}
            <circle cx={CENTER} cy={CENTER} r="26" fill="#2A0E00" />
            <circle cx={CENTER} cy={CENTER} r="21" fill="url(#hub-grad)" stroke="#3D1200" strokeWidth="2" />
            <text x={CENTER} y={CENTER + 1} fontSize="17" textAnchor="middle" dominantBaseline="middle">🔥</text>
          </svg>
        </div>

        {!segments.length && !prize && <p role="status" className="text-xs text-center text-muted-foreground mb-3">{msg('FE_SPIN_NO_POOL', 'Spin prizes are unavailable. Your credits are safe.')}</p>}
        {segments.length > 0 && <ul className="grid grid-cols-2 gap-1 text-[10px] text-muted-foreground mb-3">{segments.map((s) => <li key={s.id}>{s.icon} {s.label}</li>)}</ul>}
        {/* Result or Spin button */}
        {prize && reveal ? (
          <div className="text-center">
            <div className="text-4xl mb-1">{reveal.emoji}</div>
            <div className="text-2xl font-heading font-extrabold text-foreground">{reveal.title}</div>
            <p className="text-xs text-muted-foreground mt-1">{reveal.body}</p>
            <button onClick={close} className="mt-4 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">
              {msg('FE_SPIN_COLLECT_CLOSE', 'Collect & Close')}
            </button>
          </div>
        ) : (
          <button
            onClick={handleSpin}
            disabled={spinning || (!canSpin && !hasPendingIntent) || (!segments.length && !hasPendingIntent)}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {spinning ? msg('FE_SPIN_SPINNING', 'Spinning...') : hasPendingIntent ? msg('FE_SPIN_RECOVER', 'Recover spin result') : msg('FE_SPIN_NOW', 'Spin Now 🎡')}
          </button>
        )}
      </div>
    </div>
    </ModalPortal>
  );
}
