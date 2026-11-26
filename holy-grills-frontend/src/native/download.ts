import { registerPlugin } from '@capacitor/core';
import { isNativeApp } from './platform';

const documents = registerPlugin<{ save(options: { data: string; name: string; mime: string }): Promise<{ saved?: boolean; cancelled?: boolean }> }>('HolyGrillsDocuments');

/** Save/share a generated document through Android's chooser, no broad storage access. */
export async function saveNativeBlobUrl(url: string, name: string) {
  if (!isNativeApp()) return false;
  if (!url.startsWith('blob:') && !url.startsWith('data:image/')) throw new Error('Invalid generated document');
  const blob = await (await fetch(url)).blob();
  if (blob.size > 20 * 1024 * 1024) throw new Error('This document is too large to share');
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = reject; reader.readAsDataURL(blob);
  });
  await documents.save({ data, name, mime: blob.type || 'application/octet-stream' });
  return true;
}
