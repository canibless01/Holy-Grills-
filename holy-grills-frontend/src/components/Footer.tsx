import React from 'react';
import { Link } from 'react-router-dom';
import { Flame, Mail, Phone, MapPin } from 'lucide-react';
import APP_CONFIG from '@/config/app.config';
import BrandLogo from '@/components/BrandLogo';

/**
 * Marketing footer — desktop only (hidden on mobile, where the app works
 * via bottom nav). Rendered on every Layout-wrapped page.
 *
 * Brand system (per design spec): gradient-dark background, beige text,
 * accent-yellow icons.
 */
export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="hidden md:block bg-gradient-dark text-beige-soft">
      <div className="max-w-6xl mx-auto px-6 pt-14 pb-10 grid grid-cols-1 md:grid-cols-12 gap-y-10 gap-x-12">
        {/* Brand */}
        <div className="md:col-span-5">
          <div className="mb-4">
            <BrandLogo size="footer" variant="lockup" />
          </div>
          <p className="text-sm text-beige-soft leading-relaxed max-w-xs">
            {APP_CONFIG.tagline} ❤️‍🔥
          </p>
          <p className="text-xs text-beige/70 leading-relaxed max-w-xs mt-4">
            Started with one grill outside a hostel. Still growing one plate, one student and one gathering at a time.
          </p>
        </div>

        {/* Explore */}
        <div className="md:col-span-3">
          <h4 className="font-heading font-bold text-white text-xs mb-4 uppercase tracking-[0.14em]">Around the grill</h4>
          <ul className="space-y-3 text-sm">
            <li><Link to="/menu" className="text-beige-soft hover:text-accent transition-colors">Menu</Link></li>
            <li><Link to="/events" className="text-beige-soft hover:text-accent transition-colors">Events</Link></li>
            <li><Link to="/marketplace" className="text-beige-soft hover:text-accent transition-colors">Marketplace</Link></li>
            <li><Link to="/leaderboard" className="text-beige-soft hover:text-accent transition-colors">Leaderboard</Link></li>
            <li><Link to="/rewards" className="text-beige-soft hover:text-accent transition-colors">Rewards</Link></li>
          </ul>
        </div>

        {/* Get in touch */}
        <div className="md:col-span-4">
          <h4 className="font-heading font-bold text-white text-xs mb-4 uppercase tracking-[0.14em]">Get in touch</h4>
          <ul className="space-y-3.5 text-sm text-beige-soft">
            <li className="flex items-center gap-2.5">
              <Mail className="w-4 h-4 text-accent shrink-0" />
              <a href="mailto:grillthevibe@gmail.com" className="hover:text-accent transition-colors">grillthevibe@gmail.com</a>
            </li>
            <li className="flex items-center gap-2.5">
              <Phone className="w-4 h-4 text-accent shrink-0" />
              <a href="tel:07053263931" className="hover:text-accent transition-colors">07053263931</a>
            </li>
            <li className="flex items-start gap-2.5">
              <MapPin className="w-4 h-4 text-accent shrink-0 mt-0.5" />
              <span>FUTA Campus, Akure, Ondo State</span>
            </li>
          </ul>
          <p className="text-xs text-beige/70 mt-4">Instagram and TikTok: @grillthevibe</p>
        </div>
      </div>

      {/* Bottom bar */}
      <div className="border-t border-white/10">
        <div className="max-w-6xl mx-auto px-6 py-5 flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left">
          <div className="flex items-center gap-6">
            <Link to="/our-story" className="text-xs text-beige hover:text-accent transition-colors">Our Story</Link>
            <Link to="/faq" className="text-xs text-beige hover:text-accent transition-colors">FAQ</Link>
            <Link to="/terms" className="text-xs text-beige hover:text-accent transition-colors">Terms & Privacy</Link>
          </div>
          <span className="text-xs text-beige/70">© {year} {APP_CONFIG.name}. Marinated. Basted. Made for you ❤️‍🔥</span>
        </div>
      </div>
    </footer>
  );
}