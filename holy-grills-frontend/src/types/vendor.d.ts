/**
 * Ambient declarations for non-standard / vendor globals used by the app.
 * These are browser APIs TypeScript's DOM lib does not ship (or third-party
 * SDKs loaded from a CDN), so they are declared here instead of casting at
 * each call site.
 */

/**
 * OneSignal web SDK, loaded from https://cdn.onesignal.com (lib/onesignal.ts).
 * The SDK bootstraps as a command queue (`window.OneSignal = window.OneSignal
 * || []`) and swaps itself for the real object on load, which no small
 * interface can model faithfully.
 *
 * TODO(ts): replace with generated OneSignal typings if the SDK is ever bundled.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type OneSignalGlobal = any;

interface Window {
  /** Safari/WebKit prefix — lib/soundManager.ts. */
  webkitAudioContext?: typeof AudioContext;
  /** OneSignal web SDK queue/instance — lib/onesignal.ts. */
  OneSignal?: OneSignalGlobal;
}

interface Navigator {
  /** iOS standalone (PWA) flag — lib/installPromptStore.ts. */
  standalone?: boolean;
}

/** Barcode Detection API constructor (Chrome on Android). */
interface BarcodeDetectorConstructor {
  new (options?: { formats?: string[] }): {
    detect(source: CanvasImageSource): Promise<Array<{ rawValue: string }>>;
  };
}

interface Window {
  /**
   * Barcode Detection API — components/EventCheckInScanner.tsx. Missing from
   * lib.dom; support is runtime-detected there (`'BarcodeDetector' in window`),
   * so it is declared non-optional to keep the call sites cast-free.
   */
  BarcodeDetector: BarcodeDetectorConstructor;
}
