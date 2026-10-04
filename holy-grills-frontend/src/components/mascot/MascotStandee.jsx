import React from 'react';
import { motion } from 'framer-motion';
import { mascotUrl } from '@/lib/mascots';

/**
 * Mode 1 — Standee.
 *
 * Renders a mascot as a free-floating transparent PNG directly on the page
 * background, with a gentle 3.5s idle float (~5px). Global mascot rules:
 *  · No CSS box-shadow or drop-shadow (shadow is baked into the artwork).
 *  · Never wrapped in a card / panel / backgrounded container.
 *
 * Props:
 *  · mascot   — registry name (worried, waving, thinking, …)
 *  · className — sizing + positioning (e.g. "w-32 absolute right-6 bottom-4")
 *  · float     — enable idle bob (default true)
 *  · alt       — accessibility label
 */
export default function MascotStandee({ mascot, className = '', float = true, alt }) {
  const url = mascotUrl(mascot);
  if (!url) return null;

  const floatProps = float
    ? {
        animate: { y: [0, -5, 0] },
        transition: { duration: 3.5, repeat: Infinity, ease: 'easeInOut' },
      }
    : {};

  return (
    <motion.img
      src={url}
      alt={alt || ''}
      aria-hidden={alt ? undefined : 'true'}
      className={`select-none pointer-events-none object-contain aspect-square ${className}`}
      // No box-shadow / drop-shadow — artwork carries its own shadow.
      // object-contain + aspect-square: the mascot NEVER stretches or gets
      // squeezed into a rectangle — it keeps its upright square shape.
      style={{ filter: 'none' }}
      {...floatProps}
    />
  );
}