import React from 'react';
import Skeleton from '@/components/Skeleton';

/** Previews the Leaderboard layout: header + pinned rank + prize banner + toggle + ranking rows. */
export default function LeaderboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <Skeleton className="h-7 w-36" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-28 rounded-full" />
          <Skeleton className="h-8 w-16 rounded-full" />
        </div>
      </div>
      <Skeleton className="h-16 w-full rounded-2xl" />
      <Skeleton className="h-14 w-full rounded-2xl" />
      <div className="flex bg-secondary rounded-full p-1 max-w-xs">
        <Skeleton className="h-8 flex-1 rounded-full" />
        <Skeleton className="h-8 flex-1 rounded-full" />
      </div>
      <div className="flex gap-2">
        {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-9 w-24 rounded-xl" />)}
      </div>
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-3 rounded-2xl bg-card border border-border">
            <Skeleton className="w-8 h-8 rounded-full shrink-0" />
            <Skeleton className="w-5 h-5 rounded-full shrink-0" />
            <Skeleton className="h-4 flex-1 max-w-[140px]" />
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}