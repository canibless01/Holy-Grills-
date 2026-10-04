import React from 'react';
import Skeleton from '@/components/Skeleton';

/** Previews the event detail page: hero image + meta pills + info card + CTA. */
export default function EventDetailSkeleton() {
  return (
    <div className="space-y-5 max-w-2xl mx-auto">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-56 w-full rounded-3xl" />
      <div className="flex gap-2">
        <Skeleton className="h-8 w-40 rounded-full" />
        <Skeleton className="h-8 w-32 rounded-full" />
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-8 w-32 rounded-full" />
        <Skeleton className="h-8 w-28 rounded-full" />
      </div>
      <Skeleton className="h-28 w-full rounded-2xl" />
      <Skeleton className="h-20 w-full rounded-2xl" />
      <Skeleton className="h-14 w-full rounded-2xl" />
    </div>
  );
}