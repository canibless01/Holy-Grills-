import React from 'react';
import { cn } from '@/lib/utils';

/**
 * Single shimmer skeleton primitive — the one loading-state building block
 * shared by cart, checkout, menu, orders so every "loading" moment looks
 * intentional instead of ad-hoc. Renders a rounded block with the brand
 * shimmer sweep; compose a few of these to build any skeleton layout.
 *
 *   <Skeleton className="h-4 w-2/3" />             // a line
 *   <Skeleton className="h-16 w-16 rounded-xl" />   // a thumb (override radius)
 */
export default function Skeleton({ className }) {
  return (
    <div className={cn('relative overflow-hidden bg-muted/70 rounded-lg', className)}>
      <div className="absolute inset-0 animate-shimmer bg-[length:200%_100%] bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.45),transparent)]" />
    </div>
  );
}