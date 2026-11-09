// Card-sized versions of unsigned Cloudinary photos. Signed, transformed,
// local and third-party URLs retain their existing delivery settings.
export function menuImage(src: string | null | undefined, width = 480): string | undefined {
  if (!src) return undefined;
  try {
    const url = new URL(src);
    if (url.protocol !== 'https:' || url.hostname !== 'res.cloudinary.com' || ![320, 480, 768].includes(width)) return src;
    if (!/\/image\/upload\/v\d+\/.+\.(?:png|jpe?g|webp|avif)$/i.test(url.pathname)) return src;
    url.pathname = url.pathname.replace('/image/upload/', `/image/upload/f_auto,q_auto,c_limit,w_${width}/`);
    return url.href;
  } catch { return src; }
}

export function menuImageSet(src: string | null | undefined): string | undefined {
  if (!src || menuImage(src) === src) return undefined;
  return [320, 480, 768].map(width => `${menuImage(src, width)} ${width}w`).join(', ');
}
