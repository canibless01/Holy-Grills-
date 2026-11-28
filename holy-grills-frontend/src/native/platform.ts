import { Capacitor } from '@capacitor/core';
/** Native identity comes from Capacitor's bridge, never from a user-agent string. */
export const isNativeApp = () => typeof window !== 'undefined' && Capacitor.isNativePlatform();
