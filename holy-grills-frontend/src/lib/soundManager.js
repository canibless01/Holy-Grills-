/**
 * Holy Grill — Sound Manager
 * ============================================================================
 * A Web-Audio-API synth sound system. No audio files needed — every sound is
 * synthesized from oscillator schedules, matching the character in the spec.
 *
 * Rules (from the micro-interaction & sound spec):
 *   • Audio ALWAYS respects device silent mode (Web Audio is muted by the
 *     hardware mute switch on iOS/Android — we never override it).
 *   • Global on/off toggle lives in user settings (persisted in localStorage).
 *   • "If the moment matters to the student, amplify it. If it is functional
 *     and routine, keep it quiet."
 *
 * Usage:
 *   import { playSound, setSoundEnabled, isSoundEnabled } from '@/lib/soundManager';
 *   playSound('cart_add');
 *
 * Sound names are validated against SOUND_NAMES — see BUILDER_RULES.md.
 * ============================================================================
 */
import { useEffect, useState, useCallback } from 'react';

const STORAGE_KEY = 'hg_sound_enabled';
let audioCtx = null;
let enabled = true;

if (typeof window !== 'undefined') {
  enabled = localStorage.getItem(STORAGE_KEY) !== 'false';
}

const initCtx = () => {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    audioCtx = new AC();
  }
  if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  return audioCtx;
};

// Call on the first user gesture to satisfy browser autoplay policies so the
// context is already 'running' before any playSound() fires (otherwise the
// very first sound can be silently dropped).
export const unlockAudio = () => {
  const ctx = initCtx();
  if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
};

// --- Low-level tone helper ---
const tone = (ctx, { freq, duration = 0.15, type = 'sine', gain = 0.15, startAt = 0, freqEnd, sweep = 'linear' }) => {
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type;
  const t0 = ctx.currentTime + startAt;
  osc.frequency.setValueAtTime(freq, t0);
  if (freqEnd) {
    if (sweep === 'exp') osc.frequency.exponentialRampToValueAtTime(Math.max(1, freqEnd), t0 + duration);
    else osc.frequency.linearRampToValueAtTime(freqEnd, t0 + duration);
  }
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
  osc.connect(g).connect(ctx.destination);
  osc.start(t0);
  osc.stop(t0 + duration + 0.02);
};

// --- Sound definitions: each is a function(ctx) scheduling oscillators ---
const SOUND_DEFS = {
  // ── Essential ──
  cart_add: (ctx) => tone(ctx, { freq: 600, freqEnd: 920, duration: 0.12, type: 'sine', gain: 0.18 }),
  cart_remove: (ctx) => tone(ctx, { freq: 520, freqEnd: 300, duration: 0.15, type: 'sine', gain: 0.14 }),
  order_placed: (ctx) => [523, 659, 784].forEach((f, i) => tone(ctx, { freq: f, duration: 0.18, type: 'sine', gain: 0.16, startAt: i * 0.09 })),
  order_status: (ctx) => tone(ctx, { freq: 880, duration: 0.1, type: 'sine', gain: 0.12 }),
  push_received: (ctx) => { tone(ctx, { freq: 440, duration: 0.18, type: 'triangle', gain: 0.13 }); tone(ctx, { freq: 330, duration: 0.24, type: 'sine', gain: 0.1, startAt: 0.07 }); },
  hp_earned: (ctx) => [784, 988, 1175].forEach((f, i) => tone(ctx, { freq: f, duration: 0.12, type: 'sine', gain: 0.15, startAt: i * 0.06 })),
  review_submitted: (ctx) => { tone(ctx, { freq: 659, duration: 0.14, type: 'sine', gain: 0.14 }); tone(ctx, { freq: 880, duration: 0.18, type: 'sine', gain: 0.12, startAt: 0.08 }); },

  // ── Celebratory ──
  spin_spinning: (ctx) => { for (let i = 0; i < 10; i++) tone(ctx, { freq: 180 + i * 35, duration: 0.05, type: 'square', gain: 0.07, startAt: i * 0.06 }); },
  spin_win: (ctx) => [523, 659, 784, 1047].forEach((f, i) => tone(ctx, { freq: f, duration: 0.2, type: 'sine', gain: 0.18, startAt: i * 0.1 })),
  spin_no_win: (ctx) => tone(ctx, { freq: 320, freqEnd: 140, duration: 0.4, type: 'sawtooth', gain: 0.1, sweep: 'exp' }),
  badge_unlock: (ctx) => tone(ctx, { freq: 600, freqEnd: 1200, duration: 0.3, type: 'sine', gain: 0.15, sweep: 'exp' }),
  tier_upgrade: (ctx) => [392, 523, 659, 784, 1047].forEach((f, i) => tone(ctx, { freq: f, duration: 0.25, type: 'sine', gain: 0.2, startAt: i * 0.12 })),
  set_completed: (ctx) => [523, 659, 784, 1047, 1319].forEach((f, i) => tone(ctx, { freq: f, duration: 0.3, type: 'sine', gain: 0.2, startAt: i * 0.1 })),
  leaderboard_up: (ctx) => tone(ctx, { freq: 400, freqEnd: 1000, duration: 0.3, type: 'sine', gain: 0.15, sweep: 'exp' }),
  streak_milestone: (ctx) => { for (let i = 0; i < 4; i++) tone(ctx, { freq: 600 + i * 100, duration: 0.08, type: 'square', gain: 0.11, startAt: i * 0.07 }); },
  hp_transfer_sent: (ctx) => tone(ctx, { freq: 800, freqEnd: 300, duration: 0.3, type: 'sine', gain: 0.14, sweep: 'exp' }),
  hp_transfer_received: (ctx) => { tone(ctx, { freq: 523, duration: 0.14, type: 'sine', gain: 0.14 }); tone(ctx, { freq: 784, duration: 0.2, type: 'sine', gain: 0.12, startAt: 0.1 }); },
  first_order: (ctx) => [523, 659, 784, 659, 784, 1047].forEach((f, i) => tone(ctx, { freq: f, duration: 0.2, type: 'sine', gain: 0.16, startAt: i * 0.1 })),

  // ── Ambient (off by default — only via explicit playSound call) ──
  spin_idle: (ctx) => tone(ctx, { freq: 200, duration: 0.04, type: 'square', gain: 0.03 }),
  flash_countdown: (ctx) => tone(ctx, { freq: 600, duration: 0.03, type: 'square', gain: 0.04 }),
};

export const SOUND_NAMES = Object.keys(SOUND_DEFS);

export const isSoundEnabled = () => enabled;

export const setSoundEnabled = (value) => {
  enabled = !!value;
  try { localStorage.setItem(STORAGE_KEY, String(enabled)); } catch (e) { /* ignore */ }
};

export const playSound = (name) => {
  if (!enabled) return;
  const def = SOUND_DEFS[name];
  if (!def) {
    if (typeof console !== 'undefined') console.warn(`[soundManager] Unknown sound: "${name}". Valid: ${SOUND_NAMES.join(', ')}`);
    return;
  }
  try {
    const ctx = initCtx();
    if (!ctx) return;
    def(ctx);
  } catch (e) { /* audio errors are non-fatal */ }
};

// --- React hook for components that need the enabled state reactively ---
export const useSoundState = () => {
  const [on, setOn] = useState(enabled);
  const toggle = useCallback(() => {
    const next = !enabled;
    setSoundEnabled(next);
    setOn(next);
  }, []);
  return { soundOn: on, toggleSound: toggle, setSoundOn: (v) => { setSoundEnabled(v); setOn(v); } };
};