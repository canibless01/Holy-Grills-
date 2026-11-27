import { Geolocation } from '@capacitor/geolocation';
import { Share } from '@capacitor/share';
import { isNativeApp } from './platform';

export async function nativeCurrentPosition(options: PositionOptions = {}) {
  let position;
  try { position = await Geolocation.getCurrentPosition({ enableHighAccuracy: options.enableHighAccuracy,
    timeout: options.timeout, maximumAge: options.maximumAge }); }
  catch (failure) {
    // Permission denial needs the user's settings; a slow indoor GPS fix can
    // still use the phone's approximate/network location without another prompt.
    if (['OS-PLUG-GLOC-0003', 'OS-PLUG-GLOC-0007', 'OS-PLUG-GLOC-0009'].includes(String((failure as { code?: string }).code)) || !options.enableHighAccuracy) throw failure;
    position = await Geolocation.getCurrentPosition({ enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
  }
  return { coords: position.coords, timestamp: position.timestamp };
}
export async function shareNative(title: string, text: string, url: string) {
  if (!isNativeApp()) return false;
  await Share.share({ title, text, url, dialogTitle: title });
  return true;
}
