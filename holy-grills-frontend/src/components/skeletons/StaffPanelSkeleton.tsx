import Skeleton from '@/components/Skeleton';

/**
 * StaffPanelSkeleton — the unified loading state for the staff panels (Admin
 * sections, Kitchen, Rider), composed from the same Skeleton shimmer primitive
 * as the user-facing pages, so a "loading" moment looks identical everywhere
 * in the product. Replaces the old flame spinner: the skeleton previews the
 * page's actual anatomy (KPI tiles, boards, lists) so the layout never jumps
 * when the data arrives.
 *
 *   <StaffPanelSkeleton />                    // admin section (dashboard-like)
 *   <StaffPanelSkeleton variant="kitchen" />  // KDS board
 *   <StaffPanelSkeleton variant="rider" />    // earnings hero + batch list
 */
export default function StaffPanelSkeleton({ variant = 'admin' }) {
  if (variant === 'kitchen') {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 space-y-4">
          {/* header + capacity + metrics + tabs + 3 KDS columns */}
          <Skeleton className="h-14 w-full rounded-2xl" />
          <Skeleton className="h-16 w-full rounded-2xl" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}
          </div>
          <Skeleton className="h-10 w-full rounded-full" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 lg:gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="space-y-2.5">
                <Skeleton className="h-5 w-28" />
                {Array.from({ length: 2 }).map((_, j) => <Skeleton key={j} className="h-28 rounded-2xl" />)}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'rider') {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-2xl w-full mx-auto px-4 sm:px-6 py-4 space-y-4">
          {/* header + earnings hero + stats + tabs + batch */}
          <Skeleton className="h-14 w-full rounded-2xl" />
          <Skeleton className="h-32 w-full rounded-2xl" />
          <div className="grid grid-cols-4 gap-2">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}
          </div>
          <Skeleton className="h-10 w-full rounded-full" />
          <Skeleton className="h-40 w-full rounded-2xl" />
        </div>
      </div>
    );
  }

  // admin — mirrors the dashboard anatomy: KPI tiles, two panels, table rows
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Skeleton className="h-72" />
        <Skeleton className="h-72" />
      </div>
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}
      </div>
    </div>
  );
}
