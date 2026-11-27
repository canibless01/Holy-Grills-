import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.holygrills.app',
  appName: 'Holy Grills',
  webDir: 'dist-android',
  server: { hostname: 'localhost', androidScheme: 'https', cleartext: false },
  android: { allowMixedContent: false, webContentsDebuggingEnabled: false },
  // onesignal:managed v1 — leave notification ownership with OneSignal.
  ios: { handleApplicationNotifications: false },
  plugins: {
    SplashScreen: { launchAutoHide: false, backgroundColor: '#FFF5F0', showSpinner: false },
    SystemBars: { insetsHandling: 'native', initialViewportFitValueHint: 'contain', style: 'DARK' },
    StatusBar: { style: 'DARK', backgroundColor: '#FFF5F0' },
  },
};
export default config;
