import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import AdminSidebar from './AdminSidebar';
import AdminHeader from './AdminHeader';
import SectionErrorBoundary from './SectionErrorBoundary';

/**
 * Shared chrome for the Admin panel: collapsible sidebar + header + an
 * error-bounded, animated content region. Manages the sidebar collapse and
 * mobile-drawer state locally so the page can focus on which section to show.
 */
export default function AdminLayout({ active, onSelect, onNavigate, title, subtitle, onSignOut, children, allowedIds = null }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('hg_admin_collapsed') === 'true');
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => { localStorage.setItem('hg_admin_collapsed', String(collapsed)); }, [collapsed]);

  // The mobile drawer MUST close when a section is chosen. Closing is driven
  // from here (not just the sidebar's own handlers) so the drawer can never
  // stay open over the page you just navigated to — selection always closes.
  useEffect(() => { setMobileOpen(false); }, [active]);

  // Escape closes the mobile drawer too.
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e) => { if (e.key === 'Escape') setMobileOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileOpen]);

  // Lock page scroll behind the mobile drawer so the page you're leaving
  // doesn't scroll under it.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    document.body.style.overflow = mobileOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [mobileOpen]);

  return (
    <div className="min-h-screen bg-background admin-scope">
      <AdminSidebar
        active={active}
        onSelect={onSelect}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        allowedIds={allowedIds}
      />

      <div className={`transition-all duration-300 ${collapsed ? 'lg:ml-[76px]' : 'lg:ml-64'}`}>
        <AdminHeader
          title={title}
          subtitle={subtitle}
          onOpenMobile={() => setMobileOpen(true)}
          onSignOut={onSignOut}
          onNavigate={onNavigate}
        />

        <div className="p-4 lg:p-8 max-w-[1600px]">
          <SectionErrorBoundary sectionName={active}>
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
            >
              {children}
            </motion.div>
          </SectionErrorBoundary>
        </div>
      </div>
    </div>
  );
}