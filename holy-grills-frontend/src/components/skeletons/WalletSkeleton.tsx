import React from 'react';
import Skeleton from '@/components/Skeleton';

/** Previews the Wallet layout: title + two balance cards + virtual account + transactions. */
export default function WalletSkeleton() {
  return (
    <div className="space-y-5 max-w-2xl mx-auto">
      <Skeleton className="h-8 w-32" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Skeleton className="h-40 rounded-3xl" />
        <Skeleton className="h-40 rounded-3xl" />
      </div>
      <Skeleton className="h-24 w-full rounded-2xl" />
      <div className="space-y-2">
        <Skeleton className="h-5 w-28" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-3 rounded-2xl bg-card border border-border">
            <Skeleton className="w-9 h-9 rounded-full shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
            <Skeleton className="h-4 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}