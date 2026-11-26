import { Geolocation } from '@capacitor/geolocation';
import { Share } from '@capacitor/share';
import { isNativeApp } from './platform';

export async function nativeCurrentPosition(options: PositionOptions = {}) {
  const position = await Geolocation.getCurrentPosition({ enableHighAccuracy: options.enableHighAccuracy,
    timeout: options.timeout, maximumAge: options.maximumAge });
  return { coords: position.coords, timestamp: position.timestamp };
}
export async function shareNative(title: string, text: string, url: string) {
  if (!isNativeApp()) return false;
  await Share.share({ title, text, url, dialogTitle: title });
  return true;
}
