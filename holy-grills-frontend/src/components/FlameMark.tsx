import { cn } from '@/lib/utils';

// Brand flame mark — the HolyGrill mascot flame asset. Used everywhere a
// fire emoji or decorative flame icon used to live, so the brand stays
// consistent across the app. Sized via className; inherits no color (it's an
// image), so drop it on any background.
const FLAME_URL = 'https://media.base44.com/images/public/6aaecb077ba5fb7691376f5b/63660e4a8_flame.png';

export default function FlameMark({ className = 'w-5 h-5', decorative = true, ...props }) {
  return (
    <img
      src={FLAME_URL}
      alt={decorative ? '' : 'HolyGrill flame'}
      aria-hidden={decorative}
      className={cn('object-contain select-none', className)}
      {...props}
    />
  );
}