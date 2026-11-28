import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useMascotCelebrationState, clearMascotCelebration, mascotUrl } from '@/lib/mascots';
import MascotConfetti from './MascotConfetti';

/**
 * Mode 2 — Celebration overlay.
 *
 * Mounted once (in Layout). When any page calls `triggerMascotCelebration`:
 *  1. Background dims (~0.7s fade in).
 *  2. Mascot pops in with a confetti + glow burst (entrance < 1s).
 *  3. Holds briefly, then fades out and undims — back to normal content.
 *
 * This is a transient toast-style overlay, never a permanent element.
 */
export default function MascotCelebrationOverlay() {
  const { active, mascot, key } = useMascotCelebrationState();
  const url = mascotUrl(mascot);
  const timer = useRef(null);

  useEffect(() => {
    if (!active) return;
    // Total visible time before auto-dismiss (~3s): dim/pop + hold + fade.
    timer.current = setTimeout(() => clearMascotCelebration(), 2800);
    return () => clearTimeout(timer.current);
  }, [active, key]);

  // Allow a tap to dismiss early.
  const dismiss = () => clearMascotCelebration();

  return (
    <AnimatePresence>
      {active && url && (
        <motion.div
          key={key}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.7, ease: 'easeInOut' }}
          onClick={dismiss}
          className="fixed inset-0 z-[100] flex items-center justify-center cursor-pointer"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        >
          <MascotConfetti />
          <motion.img
            src={url}
            alt=""
            aria-hidden="true"
            initial={{ scale: 0.4, opacity: 0, y: 24 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.8, opacity: 0, y: 10 }}
            transition={{ type: 'spring', stiffness: 240, damping: 14, delay: 0.15 }}
            className="relative w-44 sm:w-52 select-none pointer-events-none"
            style={{ filter: 'none' }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}