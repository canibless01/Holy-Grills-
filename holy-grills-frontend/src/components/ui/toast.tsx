import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/* Compact, swipeable toast system.
 *
 *   - Auto-dismisses after a short duration (wired in use-toast.toast()).
 *   - User can swipe left or right to dismiss — the toast snaps back to origin
 *     if the swipe is short, or fires onOpenChange(false) if the swipe is large.
 *   - Smaller padding / text than the shadcn default so it doesn't dominate
 *     the screen every time a quick action happens.
 */

const ToastProvider = React.forwardRef<React.ElementRef<'div'>, React.ComponentPropsWithoutRef<'div'>>(({ ...props }, ref) => (
  <div
    ref={ref}
    className="fixed top-20 z-[100] left-0 right-0 mx-auto flex max-h-[calc(100vh-6rem)] w-full flex-col-reverse gap-2 p-4 sm:right-4 sm:left-auto sm:max-w-[400px] sm:top-20 sm:flex-col pointer-events-none"
    {...props}
  />
));
ToastProvider.displayName = "ToastProvider";

const ToastViewport = React.forwardRef<React.ElementRef<'div'>, React.ComponentPropsWithoutRef<'div'>>(({ ...props }, ref) => (
  <div
    ref={ref}
    className="fixed top-20 z-[100] left-0 right-0 mx-auto flex max-h-[calc(100vh-6rem)] w-full flex-col-reverse gap-2 p-4 sm:right-4 sm:left-auto sm:max-w-[400px] sm:top-20 sm:flex-col pointer-events-none"
    {...props}
  />
));
ToastViewport.displayName = "ToastViewport";

const toastVariants = cva(
  "group pointer-events-auto relative flex w-full items-center justify-between space-x-3 overflow-hidden rounded-2xl border p-4 pr-4 shadow-glow bg-card text-card-foreground transition-all data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-80 data-[state=closed]:slide-out-to-right-full data-[state=open]:slide-in-from-top-full",
  {
    variants: {
      variant: {
        default: "border-border",
        destructive: "border-primary bg-primary text-primary-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

const Toast = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof motion.div> & VariantProps<typeof toastVariants> & { onOpenChange?: (open: boolean) => void }>(({ className, variant, onOpenChange, ...props }, ref) => {
  return (
    <motion.div
      ref={ref}
      drag="x"
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.7}
      dragMomentum={false}
      whileDrag={{ opacity: 0.85 }}
      onDragEnd={(e, info) => {
        if (Math.abs(info.offset.x) > 80) onOpenChange?.(false);
      }}
      className={cn(toastVariants({ variant }), className)}
      {...props}
    />
  );
});
Toast.displayName = "Toast";

const ToastAction = React.forwardRef<React.ElementRef<'div'>, React.ComponentPropsWithoutRef<'div'>>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "inline-flex h-7 shrink-0 items-center justify-center rounded-md border bg-transparent px-2 text-xs font-medium ring-offset-background transition-colors hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
      className
    )}
    {...props}
  />
));
ToastAction.displayName = "ToastAction";

const ToastClose = React.forwardRef<React.ElementRef<'button'>, React.ComponentPropsWithoutRef<'button'>>(({ className, onClick, ...props }, ref) => (
  <button
    ref={ref}
    onClick={onClick}
    className={cn(
      "shrink-0 rounded-md p-1 text-muted-foreground transition-opacity hover:text-foreground hover:bg-secondary focus:outline-none focus:ring-2",
      className
    )}
    {...props}
  >
    <X className="h-3.5 w-3.5" />
  </button>
));
ToastClose.displayName = "ToastClose";

const ToastTitle = React.forwardRef<React.ElementRef<'div'>, React.ComponentPropsWithoutRef<'div'>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("text-[13px] font-bold leading-tight", className)} {...props} />
));
ToastTitle.displayName = "ToastTitle";

const ToastDescription = React.forwardRef<React.ElementRef<'div'>, React.ComponentPropsWithoutRef<'div'>>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("text-xs text-foreground leading-snug", className)} {...props} />
));
ToastDescription.displayName = "ToastDescription";

export {
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
  ToastAction,
};