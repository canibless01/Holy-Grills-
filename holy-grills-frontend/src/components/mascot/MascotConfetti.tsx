import { useMemo } from 'react';
import { motion } from 'framer-motion';

// Brand palette for the celebration burst.
const COLORS = ['#E71D26', '#FF9800', '#FFD959', '#FFFDF0', '#F0371F'];

/**
 * A short confetti + glow burst that radiates from the centre, used behind
 * the celebration mascot pop-in. Pure framer-motion — no external deps.
 * Self-contained: mounts, plays once, and is removed by the overlay.
 */
export default function MascotConfetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 26 }).map((_, i) => {
        const angle = (i / 26) * Math.PI * 2 + Math.random() * 0.4;
        const dist = 90 + Math.random() * 130;
        return {
          id: i,
          x: Math.cos(angle) * dist,
          y: Math.sin(angle) * dist,
          color: COLORS[i % COLORS.length],
          size: 6 + Math.random() * 6,
          rotate: Math.random() * 360,
          round: Math.random() > 0.5,
          delay: Math.random() * 0.12,
        };
      }),
    [],
  );

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      {/* Soft glow halo */}
      <motion.div
        initial={{ scale: 0.2, opacity: 0 }}
        animate={{ scale: [0.2, 1.4, 1], opacity: [0, 0.5, 0] }}
        transition={{ duration: 0.9, ease: 'easeOut' }}
        className="absolute w-72 h-72 rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(255,217,89,0.45) 0%, rgba(255,217,89,0) 70%)' }}
      />
      {pieces.map((p) => (
        <motion.span
          key={p.id}
          initial={{ x: 0, y: 0, opacity: 1, scale: 0 }}
          animate={{ x: p.x, y: p.y, opacity: [1, 1, 0], scale: 1, rotate: p.rotate }}
          transition={{ duration: 1, ease: 'easeOut', delay: p.delay }}
          className="absolute"
          style={{
            width: p.size,
            height: p.size,
            background: p.color,
            borderRadius: p.round ? '9999px' : '2px',
          }}
        />
      ))}
    </div>
  );
}