import { useMessages } from '@/lib/messages';
import { Outlet, useLocation } from 'react-router-dom';
import PromoFlyerPopup from './storefront/PromoFlyerPopup';
import TopNav from './TopNav';
import BottomNav from './BottomNav';
import Footer from './Footer';
import { useCampus } from '@/lib/campusContext';
import MascotCelebrationOverlay from './mascot/MascotCelebrationOverlay';
import PushSoftPrompt from './notifications/PushSoftPrompt';

export default function Layout() {
  useMessages();
  const { campusId } = useCampus();
  const { pathname } = useLocation();
  // Preserve contact controls while the saved campus resolves after a reload.
  const staticPage = ['/faq', '/contact', '/terms', '/newsletter/unsubscribe'].includes(pathname);
  return (
    <div className="min-h-[100dvh] bg-background flex flex-col">
      <TopNav />
      <main className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-28 lg:pb-10 min-h-[calc(100dvh-4rem)] flex-1" style={{
        paddingTop: 'calc(1.5rem + env(safe-area-inset-top, 0px))',
        paddingBottom: 'calc(7rem + env(safe-area-inset-bottom, 0px))',
        paddingLeft: 'calc(1rem + env(safe-area-inset-left, 0px))',
        paddingRight: 'calc(1rem + env(safe-area-inset-right, 0px))',
      }}>
        <Outlet key={staticPage ? 'static' : campusId || 'global'} />
      </main>
      <Footer />
      <BottomNav />
      <MascotCelebrationOverlay />
      <PromoFlyerPopup />
      <PushSoftPrompt />
    </div>
  );
}
