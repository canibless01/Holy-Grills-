import Skeleton from '@/components/Skeleton';

/** Previews the Addresses layout: header + address cards. */
export default function AddressesSkeleton() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-36" />
        <Skeleton className="h-10 w-24 rounded-xl" />
      </div>
      <div className="space-y-2.5">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3 rounded-2xl bg-card border border-border p-4">
            <Skeleton className="w-10 h-10 rounded-xl shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <div className="flex gap-1">
              <Skeleton className="w-8 h-8 rounded-xl" />
              <Skeleton className="w-8 h-8 rounded-xl" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}