import Skeleton from '@/components/Skeleton';

/** Previews the Squads layout: header + squad rows. */
export default function SquadsSkeleton() {
  return (
    <div className="space-y-4 pb-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-7 w-32" />
          <Skeleton className="h-3.5 w-56" />
        </div>
        <Skeleton className="h-10 w-28 rounded-xl shrink-0" />
      </div>
      <div className="space-y-2.5">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-4 rounded-2xl bg-card border border-border">
            <Skeleton className="w-11 h-11 rounded-xl shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-40" />
            </div>
            <Skeleton className="w-4 h-4 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}