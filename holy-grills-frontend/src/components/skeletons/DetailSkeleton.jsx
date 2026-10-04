import React from 'react';
import Skeleton from '@/components/Skeleton';

/** Generic detail-page loading state: back link + hero + body card + CTA. */
export default function DetailSkeleton() {
  return (
    <div className="space-y-5 max-w-2xl mx-auto">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-64 w-full rounded-3xl" />
      <div className="space-y-2">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
      </div>
      <Skeleton className="h-32 w-full rounded-2xl" />
      <Skeleton className="h-14 w-full rounded-2xl" />
    </div>
  );
}