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

        {/* Wheel */}
        <div className="relative w-72 h-72 mx-auto mb-4">
          {/* Fixed pointer at top */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 z-10 w-0 h-0 border-l-[10px] border-r-[10px] border-t-[18px] border-l-transparent border-r-transparent border-t-cocoa-800" />
          <svg viewBox="0 0 300 300" className="w-full h-full" style={{ transform: `rotate(${rotation}deg)` }}>
            {segments.map((seg, i) => {
              const isWinning = flashing && i === winningIndex;
              const labelPos = polarToCartesian(i * SEG_ANGLE + SEG_ANGLE / 2, RADIUS * 0.62);
              return (
                <g key={i}>
                  <path
                    d={SEG_COUNT === 1 ? `M ${CENTER-RADIUS} ${CENTER} a ${RADIUS} ${RADIUS} 0 1 0 ${2*RADIUS} 0 a ${RADIUS} ${RADIUS} 0 1 0 ${-2*RADIUS} 0` : describeSegment(i, SEG_ANGLE)}
                    fill={seg.color}
                    stroke="#fff"
                    strokeWidth="2"
                    style={{ opacity: isWinning ? 1 : 0.88, filter: isWinning ? 'brightness(1.4)' : 'none', transition: 'opacity 0.1s' }}
                  />
                  <text
                    x={labelPos.x}
                    y={labelPos.y}
                    fontSize="20"
                    textAnchor="middle"
                    dominantBaseline="middle"
                    style={{ textShadow: '0 1px 2px rgba(0,0,0,0.4)' }}
                  >
                    {seg.icon}
                  </text>
                </g>
              );
            })}
            <circle cx={CENTER} cy={CENTER} r="20" fill="#3D1200" />
            <circle cx={CENTER} cy={CENTER} r="15" fill="#FFC251" />
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
