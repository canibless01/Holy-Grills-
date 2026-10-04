import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import AdminSidebar from './AdminSidebar';
import AdminHeader from './AdminHeader';
import SectionErrorBoundary from './SectionErrorBoundary';

/**
 * Shared chrome for the Admin panel: collapsible sidebar + header + an
 * error-bounded, animated content region. Manages the sidebar collapse and
 * mobile-drawer state locally so the page can focus on which section to show.
 */
export default function AdminLayout({ active, onSelect, onNavigate, title, subtitle, onSignOut, children }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('hg_admin_collapsed') === 'true');
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => { localStorage.setItem('hg_admin_collapsed', collapsed); }, [collapsed]);

  return (
    <div className="min-h-screen bg-background admin-scope">
      <AdminSidebar
        active={active}
        onSelect={onSelect}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
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