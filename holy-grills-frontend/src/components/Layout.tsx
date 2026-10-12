import { msg, useMessages } from '@/lib/messages';
import { Outlet, Link } from 'react-router-dom';
import TopNav from './TopNav';
import BottomNav from './BottomNav';
import Footer from './Footer';
import { useCampus } from '@/lib/campusContext';
import MascotCelebrationOverlay from './mascot/MascotCelebrationOverlay';

export default function Layout() {
  useMessages();
  const { campusId } = useCampus();
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <TopNav />
      <main className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-28 lg:pb-10 min-h-[calc(100vh-4rem)] flex-1">
        <Outlet key={campusId || 'global'} />
      </main>
      <div className="md:hidden px-4 pb-24 text-center">
        <Link to="/contact" className="text-sm font-bold text-primary underline">{msg('FE_LAYOUT_CONTACT_US', "Contact us")}</Link>
      </div>
      <Footer />
      <BottomNav />
      <MascotCelebrationOverlay />
    </div>
  );
}
