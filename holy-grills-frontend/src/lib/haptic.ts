/**
 * Haptic feedback utility for mobile devices.
 * Uses navigator.vibrate() for tactile feedback on important actions.
 * 
 * Usage:
 *   haptic('success') // on successful action
 *   haptic('error')   // on error/failure
 *   haptic('tap')     // on button press
 */

type HapticPattern = 'tap' | 'success' | 'error' | 'warning' | 'selection';

const PATTERNS: Record<HapticPattern, number | number[]> = {
  tap: 10,           // Short tap feedback
  success: [10, 50, 10],  // Double pulse for success
  error: [20, 100, 20],   // Stronger double pulse for error
  warning: [15, 75, 15],  // Medium double pulse for warning
  selection: 5,      // Very short pulse for selection
};

export function haptic(pattern: HapticPattern = 'tap'): void {
  // Only run on devices that support vibration
  if (typeof navigator === 'undefined' || !navigator.vibrate) {
    return;
  }

  // Respect user's motion preferences
  if (typeof window !== 'undefined' && window.matchMedia) {
    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (motionQuery.matches) {
      return; // Skip haptics if user prefers reduced motion
    }
  }

  try {
    navigator.vibrate(PATTERNS[pattern]);
  } catch {
    // Vibration API not supported or failed silently
  }
}

/**
 * Hook for components that need haptic feedback.
 * Returns a function that triggers haptic feedback.
 */
export function useHaptic() {
  return haptic;
}
