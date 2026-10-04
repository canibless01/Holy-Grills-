import React, { useState } from 'react';
import { X, ChevronRight, Flame, Sparkles } from 'lucide-react';
import { ADMIN_GROUPS as GROUPS } from '@/lib/adminSections';
import BrandLogo from '@/components/BrandLogo';

export default function AdminSidebar({ active, onSelect, collapsed, onToggleCollapse, mobileOpen, onCloseMobile }) {
  const [expandedGroup, setExpandedGroup] = useState(null);

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-foreground/50 backdrop-blur-sm lg:hidden" onClick={onCloseMobile} />
      )}

      <aside
        className={`fixed left-0 top-0 z-50 h-full bg-sidebar text-sidebar-foreground flex flex-col transition-all duration-300 ${collapsed ? 'lg:w-[76px]' : 'lg:w-64'} ${mobileOpen ? 'w-64 translate-x-0' : 'w-64 -translate-x-full lg:translate-x-0'}`}
      >
        {/* Brand */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-sidebar-border shrink-0">
          <div className={`flex items-center ${collapsed ? 'lg:justify-center' : 'gap-2.5'}`}>
            <BrandLogo size="sm" className="shrink-0" />
            {!collapsed && (
              <div className="leading-none">
                <div className="font-heading font-extrabold text-sm text-white">Holy Grills</div>
                <div className="text-[9px] text-sidebar-ring uppercase tracking-wider font-bold">Admin Control</div>
              </div>
            )}
          </div>
          <button onClick={onCloseMobile} className="lg:hidden p-2 -mr-2 rounded-xl hover:bg-sidebar-accent active:scale-95 transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Collapse toggle */}
        <button
          onClick={onToggleCollapse}
          className="hidden lg:flex items-center gap-2 mx-3 my-2 px-3 py-2 rounded-xl text-[11px] font-bold text-sidebar-foreground/50 hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
        >
          {collapsed
            ? <ChevronRight className="w-3.5 h-3.5 mx-auto rotate-180" />
            : <><ChevronRight className="w-3.5 h-3.5" /> Collapse</>}
        </button>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 scrollbar-hide">
          {GROUPS.map((g, gi) => {
            const hasLabel = !!g.label;
            const isExpanded = expandedGroup === g.label || !hasLabel;
            const activeInGroup = g.items.some((s) => s.id === active);

            return (
              <div key={gi}>
                {!collapsed && hasLabel && (
                  <button
                    onClick={() => setExpandedGroup((prev) => (prev === g.label ? null : g.label))}
                    className={`w-full flex items-center justify-between px-4 pt-3.5 pb-1 text-[10px] font-extrabold uppercase tracking-wider transition-colors ${activeInGroup ? 'text-sidebar-ring' : 'text-sidebar-foreground/40 hover:text-sidebar-foreground'}`}
                  >
                    <span>{g.label}</span>
                    <ChevronRight className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                  </button>
                )}
                {collapsed && hasLabel && <div className="my-2 mx-4 border-t border-sidebar-border" />}

                {isExpanded && g.items.map((s) => {
                  const Icon = s.icon;
                  const isActive = active === s.id;
                  return (
                    <button
                      key={s.id}
                      onClick={() => { onSelect(s.id); onCloseMobile(); }}
                      title={s.label}
                      className={`group relative flex items-center gap-2.5 w-[calc(100%-12px)] mx-auto px-3 py-2 rounded-xl transition-all ${collapsed ? 'lg:justify-center lg:px-0' : ''} ${isActive ? 'bg-sidebar-primary text-sidebar-primary-foreground shadow-glow' : 'text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'}`}
                    >
                      {isActive && <span className="absolute -left-1 top-1/2 -translate-y-1/2 w-1 h-6 rounded-full bg-sidebar-ring hidden lg:block" />}
                      <Icon className={`w-[18px] h-[18px] shrink-0 ${isActive ? '' : 'group-hover:scale-110'} transition-transform`} />
                      {!collapsed && (
                        <div className="flex-1 text-left min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[13px] font-bold leading-tight truncate">{s.label}</span>
                            {s.superAdminOnly && (
                              <span className="shrink-0 text-[8px] font-extrabold uppercase tracking-wide px-1 py-0.5 rounded bg-sidebar-accent text-sidebar-ring border border-sidebar-ring/30" title="Editing requires a super admin">SA</span>
                            )}
                          </div>
                          <div className={`text-[10px] truncate ${isActive ? 'text-sidebar-primary-foreground/70' : 'text-sidebar-foreground/40'}`}>{s.desc}</div>
                        </div>
                      )}
                      {collapsed && s.superAdminOnly && (
                        <span className="hidden lg:block absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-sidebar-ring" title="Editing requires a super admin" />
                      )}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </nav>

        {!collapsed && (
          <div className="px-4 py-3 border-t border-sidebar-border">
            <div className="flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5 text-sidebar-ring" />
              <span className="text-[10px] font-bold text-sidebar-foreground/40">Holy Grills · Admin v3</span>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}