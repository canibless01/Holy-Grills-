import { motion, AnimatePresence } from 'framer-motion';
import ProfileMenuContent from '@/components/ProfileMenuContent';

/**
 * MobileProfileDrawer — the account menu as a full-height side panel on phones.
 *
 * It slides in above the floating tab bar (higher z-index than the nav) and its
 * body scrolls independently, so every link — including Log out at the very
 * bottom — stays reachable no matter how short the screen is. The panel itself
 * is just the shell; the header, list and close button all come from
 * ProfileMenuContent, the same body the desktop dropdown renders.
 */
export default function MobileProfileDrawer({ open, onClose, user, hpBalance, tierInfo, onNavigate, onLogout }) {
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[60] md:hidden">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-md"
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 340, damping: 34 }}
            className="absolute right-0 top-0 h-full w-[86%] max-w-sm bg-card shadow-2xl flex flex-col overflow-hidden"
          >
            <div className="flex-1 overflow-y-auto overscroll-contain">
              <ProfileMenuContent
                user={user}
                hpBalance={hpBalance}
                tierInfo={tierInfo}
                onNavigate={onNavigate}
                onLogout={onLogout}
                onClose={onClose}
              />
            </div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  );
}