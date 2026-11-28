import { cn } from '@/lib/utils';

/**
 * Skeleton — animated placeholder for loading states.
 * Follows skills/mobile-native and skills/apple-design principles:
 * - Provides visual feedback during data fetch
 * - Matches the shape of the content that will load
 * - Respects prefers-reduced-motion
 * - Uses brand colors for consistency
 */

interface SkeletonProps {
  className?: string;
  /** Height in Tailwind units or CSS value */
  height?: string;
  /** Width in Tailwind units or CSS value */
  width?: string;
  /** Border radius */
  rounded?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  /** Show pulse animation */
  animate?: boolean;
}

const RADIUS_MAP = {
  sm: 'rounded-sm',
  md: 'rounded-md',
  lg: 'rounded-lg',
  xl: 'rounded-xl',
  full: 'rounded-full',
};

export default function Skeleton({
  className,
  height = 'h-4',
  width = 'w-full',
  rounded = 'md',
  animate = true,
}: SkeletonProps) {
  return (
    <div
      className={cn(
        'bg-muted border border-border/50',
        RADIUS_MAP[rounded],
        height,
        width,
        animate && 'animate-pulse',
        className
      )}
      aria-hidden="true"
    />
  );
}

/**
 * CardSkeleton — skeleton for card-based content
 */
export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('rounded-xl bg-card border border-border p-4 space-y-3', className)}>
      <Skeleton height="h-4" width="w-3/4" rounded="md" />
      <Skeleton height="h-3" width="w-full" rounded="md" />
      <Skeleton height="h-3" width="w-5/6" rounded="md" />
    </div>
  );
}

/**
 * ListSkeleton — skeleton for list items
 */
export function ListSkeleton({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-card border border-border">
          <Skeleton height="h-10 w-10" rounded="full" />
          <div className="flex-1 space-y-2">
            <Skeleton height="h-3" width="w-3/4" rounded="md" />
            <Skeleton height="h-2" width="w-1/2" rounded="md" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * StatSkeleton — skeleton for stat cards (like HP balance, order count)
 */
export function StatSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('flex flex-col items-start gap-1 rounded-xl bg-card border border-border px-2.5 py-2.5', className)}>
      <Skeleton height="h-3 w-3" rounded="full" />
      <Skeleton height="h-4 w-12" rounded="md" />
      <Skeleton height="h-2 w-16" rounded="md" />
    </div>
  );
}
