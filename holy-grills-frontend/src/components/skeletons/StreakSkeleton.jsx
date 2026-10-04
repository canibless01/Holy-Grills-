import React from 'react';
import Skeleton from '@/components/Skeleton';

/** Previews the Streak layout: title + hero card + week calendar + milestone cards. */
export default function StreakSkeleton() {
  return (
    <div className="space-y-5 max-w-2xl mx-auto">
      <div className="space-y-1.5">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-3.5 w-full max-w-md" />
      </div>
      <Skeleton className="h-44 w-full rounded-3xl" />
      <Skeleton className="h-28 w-full rounded-2xl" />
      <div className="space-y-3">
        <Skeleton className="h-5 w-28" />
        {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-2xl" />)}
      </div>
    </div>
  );
}