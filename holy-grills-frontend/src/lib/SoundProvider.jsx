/**
 * Holy Grill — SoundProvider
 * ----------------------------------------------------------------------------
 * App-wide context for the sound system. Wraps the app once (in App.jsx) and
 * exposes play() + enabled state to every component via useSound().
 *
 *   import { useSound } from '@/lib/SoundProvider';
 *   const { play, soundOn, toggleSound } = useSound();
 *   play('cart_add');
 */
import React, { createContext, useContext, useCallback, useEffect } from 'react';
import { playSound, setSoundEnabled, isSoundEnabled, unlockAudio } from '@/lib/soundManager';

const SoundContext = createContext(null);

// Selective haptics — a light buzz alongside the sounds that mark a real
// moment (cart add/remove, order placed, reward/streak win). Cheap taps stay
// silent so the phone isn't buzzing on every nav press. Respects the user's
// sound toggle: if sounds are off, haptics stay off too.
const HAPTICS = {
  cart_add: 12,
  cart_remove: 18,
  order_placed: [18, 40, 18],
  reward_unlock: [14, 30, 14, 30, 24],
  streak_hit: [14, 30, 14, 30, 24],
};

const fireHaptic = (name, enabled) => {
  if (!enabled) return;
  const pattern = HAPTICS[name];
  if (pattern && typeof navigator !== 'undefined' && navigator.vibrate) {
    try { navigator.vibrate(pattern); } catch { /* ignore */ }
  }
};

export const SoundProvider = ({ children }) => {
  const [soundOn, setSoundOnState] = React.useState(isSoundEnabled());

  // Unlock the Web Audio context on the first user gesture (browser autoplay
  // policy). Without this, the first playSound() can be silently dropped.
  useEffect(() => {
    const unlock = () => {
      unlockAudio();
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      window.removeEventListener('touchstart', unlock);
    };
    window.addEventListener('pointerdown', unlock);
    window.addEventListener('keydown', unlock);
    window.addEventListener('touchstart', unlock);
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      window.removeEventListener('touchstart', unlock);
    };
  }, []);

  const play = useCallback((name) => {
    playSound(name);
    fireHaptic(name, soundOn);
  }, [soundOn]);

  const toggleSound = useCallback(() => {
    const next = !isSoundEnabled();
    setSoundEnabled(next);
    setSoundOnState(next);
  }, []);

  const setSoundOn = useCallback((v) => {
    setSoundEnabled(v);
    setSoundOnState(v);
  }, []);

  return (
    <SoundContext.Provider value={{ play, soundOn, toggleSound, setSoundOn }}>
      {children}
    </SoundContext.Provider>
  );
};

export const useSound = () => {
  const ctx = useContext(SoundContext);
  if (!ctx) {
    // Graceful fallback if used outside provider — still plays, just no reactive state.
    return { play: playSound, soundOn: isSoundEnabled(), toggleSound: () => {}, setSoundOn: setSoundEnabled };
  }
  return ctx;
};

export default SoundProvider;