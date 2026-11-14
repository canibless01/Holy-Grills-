import Skeleton from '@/components/Skeleton';

/** Previews the Rewards layout: HP bar + tier card + tab switcher + reward cards. */
export default function RewardsSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-20 w-full rounded-2xl" />
      <Skeleton className="h-28 w-full rounded-2xl" />
      <div className="flex gap-1 p-1 rounded-full bg-secondary">
        {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8 flex-1 rounded-full" />)}
      </div>
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex gap-3 rounded-2xl bg-card border border-border p-3">
            <Skeleton className="w-16 h-16 rounded-xl shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
              <Skeleton className="h-7 w-24 rounded-full" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}