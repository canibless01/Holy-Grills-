import React from 'react';
import { useCountUp } from '@/hooks/useCountUp';

/**
 * Renders a number that counts up from its previous value to `value`.
 * Pass `format` for currency/other formatting (e.g. formatNaira); otherwise
 * the animated value is rounded to an integer.
 */
export default function CountUp({
  value = 0,
  duration = 1000,
  format,
  className,
}: {
  value?: number;
  duration?: number;
  format?: (v: number) => React.ReactNode;
  className?: string;
}) {
  const v = useCountUp(Number(value) || 0, duration);
  return <span className={className}>{format ? format(v) : Math.round(v)}</span>;
}