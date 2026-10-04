import { useState, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import confetti from 'canvas-confetti';
import { liveApi } from '@/lib/liveApi';
import { playSound } from '@/lib/soundManager';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { toast } from '@/components/ui/use-toast';
import { EXCLUSIVE_SPIN_PRIZES, getExclusivePrize } from '@/lib/rewardUtils';
import ModalPortal from '@/components/ModalPortal';
import type { ExclusiveSpinPrize, ExclusiveSpinResult } from '@/types/exclusive-spin';
import { msg } from '@/lib/messages';

const RADIUS = 130;
const CENTER = 150;

// Fallback colours for backend prizes not present in the static prize table.
const FALLBACK_COLORS = ['#F72B13', '#FFC251', '#FF6B1A', '#FFDD9F', '#D4200C', '#ECA829', '#FF7070', '#C4A57D', '#F2542D', '#FFB347'];

// Default segments — the static prize set. Used until the backend prize list
// loads (or when the backend returns none), so the wheel never renders empty.
const DEFAULT_SEGMENTS = EXCLUSIVE_SPIN_PRIZES.map((p) => ({
  label: p.label, icon: p.icon, color: p.color, id: p.id,
}));

// Build wheel segments from the backend-provided prize list (GET /exclusive-spin
// → prizes[]). Each backend prize is matched onto the static prize table for its
// icon/colour; unknown names get a rotating fallback colour so every segment
// is distinct and the wheel reflects the admin-configured pool, not a hardcode.
const buildSegments = (backendPrizes) => {
  if (!Array.isArray(backendPrizes) || backendPrizes.length === 0) return DEFAULT_SEGMENTS;
  return backendPrizes.map((p, i) => {
    const label = p.name || p.label || p.prize_name || 'Prize';
    const match = EXCLUSIVE_SPIN_PRIZES.find((sp) => sp.label === label || sp.token === label || sp.id === p.id);
    return {
      id: p.id || (match && match.id) || `prize_${i}`,
      label,
      icon: match?.icon || '🎁',
      color: match?.color || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
    };
  });
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

// Reveal copy per prize effect.
const revealCopy = (prize) => {
  if (!prize) return { emoji: '🎁', title: 'Prize won!', body: 'Check your rewards.' };
  switch (prize.type) {
    case 'hp':
      return { emoji: prize.icon || '⚡', title: `+${prize.hp} HP!`, body: 'Holy Points added to your balance.' };
    case 'status':
      return { emoji: prize.icon || '🔥', title: `${prize.label}!`, body: 'Earn double HP on your next order.' };
    case 'next_order':
    default:
      return { emoji: prize.icon || '🎁', title: `${prize.label} won!`, body: `Enjoy a free ${prize.label.replace('Free ', '')} on your next order.` };
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
  const { refreshHp } = useHolyGrill();
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
      } catch { /* keep default segments */ }
    })();
    return () => { cancelled = true; };
  }, [open, prizes]);

  // Idle slow rotation — only when the user can actually spin. When unusable
  // the wheel stays static so it's not misleading.
  useEffect(() => {
    if (!open || spinning || prize || !canSpin) return;
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
  }, [open, spinning, prize, canSpin]);

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
    if (spinning) return;
    setSpinning(true);
    setPrize(null);
    setFlashing(false);
    setWinningIndex(-1);
    cancelAnimationFrame(rafRef.current);
    playSound('spin_spinning');

    let apiResult;
    try {
      apiResult = await liveApi.hp.exclusiveSpin();
    } catch (e) {
      setSpinning(false);
      toast({ title: msg('FE_SPIN_WHEEL_SPIN_FAILED', 'Spin failed'), description: e.message, variant: 'destructive' });
      return;
    }

    // Map API result to a prize, then to a wheel segment.
    const resolved = getExclusivePrize(apiResult?.prize || apiResult);
    let segIndex = resolved ? segments.findIndex((s) => s.id === resolved.id) : -1;
    if (segIndex < 0) segIndex = 0;

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
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl p-6 w-full max-w-sm animate-slide-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-heading font-bold text-lg text-foreground">🎡 Exclusive Spin</h3>
          <button onClick={onClose}><X className="w-5 h-5 text-muted-foreground" /></button>
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
                    d={describeSegment(i, SEG_ANGLE)}
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

        {/* Result or Spin button */}
        {prize && reveal ? (
          <div className="text-center">
            <div className="text-4xl mb-1">{reveal.emoji}</div>
            <div className="text-2xl font-heading font-extrabold text-foreground">{reveal.title}</div>
            <p className="text-xs text-muted-foreground mt-1">{reveal.body}</p>
            <button onClick={onClose} className="mt-4 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm">
              Collect & Close
            </button>
          </div>
        ) : (
          <button
            onClick={handleSpin}
            disabled={spinning}
            className="w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {spinning ? 'Spinning...' : 'Spin Now 🎡'}
          </button>
        )}
      </div>
    </div>
    </ModalPortal>
  );
}