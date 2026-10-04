import React from 'react';
import { Lock, ShieldAlert } from 'lucide-react';
import { useHolyGrill } from '@/lib/HolyGrillContext';

// Role helpers for admin panels (routes reference: system settings writes are
// super-admin-only — a regular admin gets a hard 403). Show the indicator ONLY
// on super-admin-only actions; actions both roles can perform carry no badge,
// so admins are never left guessing which role can do what.
export const useIsSuperAdmin = () => {
  const { user } = useHolyGrill();
  return user?.role === 'super_admin';
};

export function SuperAdminBadge() {
  return (
    <span
      title="Only a super admin can change this"
      className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-secondary text-muted-foreground text-[10px] font-extrabold uppercase tracking-wide border border-border shrink-0"
    >
      <Lock className="w-3 h-3" /> Super admin only
    </span>
  );
}

export function SuperAdminNotice({ children }) {
  return (
    <div className="flex items-start gap-2 rounded-2xl bg-accent/10 border border-accent/25 p-3 text-[11px] text-foreground/80">
      <ShieldAlert className="w-4 h-4 text-accent shrink-0 mt-0.5" />
      <div>{children || <>You can view this, but only a <b>super admin</b> can change it. Any change you need should go to a super admin.</>}</div>
    </div>
  );
}