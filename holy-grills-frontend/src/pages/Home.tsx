import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ChevronRight, TrendingUp, Gift, Mail, Check, Trophy, Zap, Loader2, Flame } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { useHolyGrill } from '@/lib/HolyGrillContext';
import { getLaunchWindowEndDate, getFirstOrderGiftItemName } from '@/lib/featureConfig';
import { toast } from '@/components/ui/use-toast';
import MenuItemCard from '@/components/MenuItemCard';
import HeroCarousel from '@/components/HeroCarousel';
import AutoScrollCarousel from '@/components/AutoScrollCarousel';
import TestimonialSlider from '@/components/TestimonialSlider';
import KitchenClosedPopup from '@/components/KitchenClosedPopup';
import KitchenStatusBox from '@/components/KitchenStatusBox';
import OrderSuggestionCard from '@/components/OrderSuggestionCard';
import ActiveOrderCard from '@/components/ActiveOrderCard';
import SquadOrderEducation from '@/components/SquadOrderEducation';
import StorefrontSlider from '@/components/storefront/StorefrontSlider';
import EarlySupportersSlider from '@/components/storefront/EarlySupportersSlider';
import CateringCard from '@/components/CateringCard';
import SEO from '@/components/SEO';
import CountUp from '@/components/CountUp';
import MascotStandee from '@/components/mascot/MascotStandee';
import FlameMark from '@/components/FlameMark';
import ModalPortal from '@/components/ModalPortal';
import PromoFlyerPopup from '@/components/storefront/PromoFlyerPopup';
import { getStorefrontSections } from '@/lib/storefrontMockData';

const HOLY_POINTS_FEATURES = [
  { icon: Flame, title: 'Earn on orders', body: 'Every plate counts.', to: '/menu' },
  { icon: Trophy, title: 'Leaderboard', body: 'Climb the ranks.', to: '/leaderboard' },
  { icon: Gift, title: 'Redeem rewards', body: 'Free sides, drops.', to: '/rewards' },
  { icon: Zap, title: 'Streak bonus', body: 'Keep showing up.', popup: 'streak' },
];

export default function Home() {
  const navigate = useNavigate();
  const { user, hpBalance, addToCart, isAuthenticated, streak } = useHolyGrill();
  const [kitchenStatus, setKitchenStatus] = useState(null);
  const [featuredItems, setFeaturedItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [subscribed, setSubscribed] = useState(false);
  const [subscribing, setSubscribing] = useState(false);
  const [showStreakPopup, setShowStreakPopup] = useState(false);
  const [myRank, setMyRank] = useState(null);
  const [testimonials, setTestimonials] = useState([]);
  const launchWindowEnd = getLaunchWindowEndDate();
  const giftItemName = getFirstOrderGiftItemName();

  // The backend may return the rank under different keys — normalise it so the
  // tile shows the real number whenever the user has one.
  // Holy Points banner — ONLY the large banner card carries the CTA gradient
  // (red → yellow). The four feature tiles inside are outline-only (no fill),
  // so the gradient stays on one surface instead of repeating per card.
  const rankRaw = myRank?.rank ?? myRank?.position ?? myRank?.my_rank ?? myRank?.current_rank ?? myRank?.user_rank;
  const rankNo = rankRaw && typeof rankRaw === 'object' ? (rankRaw.rank ?? rankRaw.position ?? null) : rankRaw;
  const myRankValue = typeof rankNo === 'number' && rankNo > 0 ? rankNo : null;

  useEffect(() => {
    const load = async () => {
      try {
        const items = await liveApi.menu.getItems({});
        // Filter for featured items client-side, fallback to any available
        // items so the carousel always has content.
        const all = items.items || [];
        let featured = all.filter((i) => i.is_featured && i.is_available !== false);
        if (!featured.length) featured = all.filter((i) => i.is_available !== false).slice(0, 8);
        setFeaturedItems(featured);
        if (isAuthenticated) {
          try { setMyRank(await liveApi.leaderboard.getMyRank()); } catch { /* ignore */ }
        }
        try {
          const sections = await getStorefrontSections('testimonial');
          if (Array.isArray(sections)) {
            setTestimonials(sections.map((s) => ({
              text: s.content?.review || s.subtitle || s.title || '',
              name: s.content?.name || s.title || 'Student',
            })));
          }
        } catch { /* empty testimonials — backend unavailable */ }
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
    // Safety net — the storefront must never be trapped behind the spinner if
    // a backend call is slow or unresponsive.
    const deadline = setTimeout(() => setLoading(false), 6000);
    return () => clearTimeout(deadline);
  }, []);

  const handleQuickAdd = async (item) => {
    const detail = await liveApi.menu.getItem(item.id);
    const addons = await liveApi.menu.getAddons(item.id);
    const hasRequired = (detail.variation_groups || []).some((vg) => vg.is_required) || (addons.addon_groups || []).some((ag) => ag.is_required);
    if (!hasRequired) {
      await addToCart({ menu_item_id: item.id, quantity: 1 });
      toast({ title: 'Added to your cart', description: `${item.name} is ready to checkout.`, sound: 'cart_add' });
    } else {
      navigate(`/menu/${item.id}`);
    }
  };

  const handleCta = () => navigate('/menu');

  // Real backend newsletter subscribe — POST /api/storefront/newsletter.
  const handleNewsletter = async (e) => {
    e.preventDefault();
    if (!email) return;
    setSubscribing(true);
    try {
      await liveApi.storefront.subscribeNewsletter({ email, source: 'website' });
      setSubscribed(true);
      toast({ title: "You're in ❤️‍🔥", description: 'Watch your inbox.' });
    } catch (e) {
      toast({ title: 'Newsletter subscription failed.', variant: 'destructive' });
    }
    setSubscribing(false);
  };

  return (
    <>
      <SEO />
      <PromoFlyerPopup />

      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: 'easeOut' }} className="space-y-7">

      <HeroCarousel onCta={handleCta} />

      <OrderSuggestionCard />

      {launchWindowEnd && (
        <div className="rounded-2xl bg-gradient-dark p-4 text-white flex items-center gap-3 shadow-card">
          <span className="text-2xl">🎁</span>
          <div className="flex-1 min-w-0">
            <div className="font-bold text-sm">Free {giftItemName} on your first order!</div>
            <div className="text-xs text-white/75">First-order gift ends {new Date(launchWindowEnd).toLocaleDateString()}</div>
          </div>
        </div>
      )}

      {/* 2. Kitchen Radar — live box shared with the menu page */}
      <KitchenStatusBox onStatus={setKitchenStatus} />

      {isAuthenticated && (
      <div className="grid grid-cols-3 gap-2">
        <Link to="/dashboard" className="flex flex-col items-start gap-1 rounded-xl bg-card border border-border px-2.5 py-2.5 hover:border-primary/40 active:scale-95 transition">
          <Flame className="w-3.5 h-3.5 text-primary" />
          <div className="font-heading font-extrabold text-base text-foreground leading-none tabular-nums"><CountUp value={hpBalance?.active || 0} /></div>
          <div className="text-[10px] text-muted-foreground font-medium leading-tight truncate w-full">Holy Points</div>
        </Link>
        <Link to="/leaderboard" className="flex flex-col items-start gap-1 rounded-xl bg-card border border-border px-2.5 py-2.5 hover:border-primary/40 active:scale-95 transition">
          <TrendingUp className="w-3.5 h-3.5 text-accent" />
          <div className="font-heading font-extrabold text-base text-foreground leading-none tabular-nums">{myRankValue != null ? <>#{<CountUp value={myRankValue} />}</> : '—'}</div>
          <div className="text-[10px] text-muted-foreground font-medium leading-tight truncate w-full">Your Rank</div>
        </Link>
        <ActiveOrderCard />
      </div>
      )}

      {/* 3. Featured menu */}
      {featuredItems.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="hg-eyebrow">Menu</span>
              <h2 className="font-heading font-extrabold text-lg text-foreground flex items-center gap-1.5">Made for sharing</h2>
              <p className="text-xs text-muted-foreground mt-0.5">Fan favourites from the fire.</p>
            </div>
            <Link to="/menu" className="text-xs font-bold text-primary flex items-center gap-0.5">
              Full menu <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
          <AutoScrollCarousel speed={30}>
            {[...featuredItems, ...featuredItems].map((item, i) => (
              <div key={`${item.id}-${i}`} className="w-44 flex-shrink-0 snap-start flex">
                <MenuItemCard item={item} onAdd={handleQuickAdd} />
              </div>
            ))}
          </AutoScrollCarousel>
        </div>
      )}

      {/* 4. Squad Orders — right after the menu */}
      <SquadOrderEducation />

      {/* 5. How it's made — process-stage slider (backend-driven) */}
      <StorefrontSlider sectionType="how_its_made" variant="landscape" eyebrow="How it's made" headline="Made the long way." subline="The care behind every plate." />

      {/* 6. Holy Points banner — gradient on the large card only; the inner
          feature tiles are outline-only, per the reference design */}
      <div className="rounded-3xl relative overflow-hidden shadow-card bg-gradient-cta">
        <div className="relative p-6 sm:p-8">
          <FlameMark className="absolute -right-6 -top-6 w-28 h-28 opacity-10" />
          <div className="relative">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-white/90">Holy Points</span>
            <h2 className="font-heading font-extrabold text-xl mt-1 mb-2 flex items-center gap-1.5 text-white">Eat. Earn. Come Back ❤️‍🔥.</h2>
            <p className="text-sm text-white/80 max-w-md mb-5">
              Earned by eating. Spent everywhere.
            </p>
            <div className="grid grid-cols-2 gap-3">
              {HOLY_POINTS_FEATURES.map((f) => {
                const streakDays = streak?.streak_count ?? streak?.current_streak ?? streak?.days ?? streak?.count ?? 0;
                const content = (
                  <>
                    <div className="flex items-center justify-between mb-1.5">
                      <f.icon className={`w-5 h-5 text-white ${f.popup === 'streak' ? 'animate-flame-flicker' : ''}`} />
                      {f.popup === 'streak' && isAuthenticated && (
                      <span className="text-lg font-heading font-extrabold text-white"><CountUp value={streakDays} /></span>
                    )}
                  </div>
                  <div className="font-bold text-sm mb-0.5 text-white">{f.title}</div>
                  <div className="text-xs text-white/75 leading-relaxed">{f.body}</div>
                </>
                );
                if (f.popup === 'streak') {
                  return (
                    <button key={f.title} onClick={() => setShowStreakPopup(true)} className="text-left rounded-xl bg-transparent border border-white/40 p-4 hover:bg-white/5 active:scale-95 transition-all">
                      {content}
                    </button>
                  );
                }
                return (
                  <Link key={f.title} to={f.to} className="rounded-xl bg-transparent border border-white/40 p-4 hover:bg-white/5 active:scale-95 transition-all">
                    {content}
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* 7. What's inside — logged-out feature slider only */}
      {!isAuthenticated && (
        <StorefrontSlider sectionType="whats_inside" variant="portrait" loggedInOnly eyebrow="What's inside" headline="A lot to show up for." subline="The perks behind the login." />
      )}

      {/* 8. The First Believers — early supporters slider */}
      <EarlySupportersSlider />

      {/* 9. Catering — single backend-driven card (image + text + CTA) */}
      <CateringCard />

      {/* 10. Reviews */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <span className="hg-eyebrow">Reviews</span>
            <h2 className="font-heading font-extrabold text-lg text-foreground flex items-center gap-1.5">Straight from students.</h2>
            <p className="text-xs text-muted-foreground mt-0.5">From the people we cook for.</p>
          </div>
        </div>
        <TestimonialSlider testimonials={testimonials} />
      </div>

      {/* 11. Fire Feast Squad — newsletter */}
      {/* Newsletter — compact 2-row layout: icon + text on one line, input + button on the next */}
      <div className="rounded-3xl bg-gradient-dark p-5 text-white shadow-card">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-9 h-9 rounded-xl bg-white/10 border border-white/15 flex items-center justify-center shrink-0">
            <Mail className="w-4 h-4 text-accent" />
          </div>
          <div className="leading-tight">
            <span className="text-[10px] font-bold uppercase tracking-wider text-accent block">Fire Feast Squad</span>
            <span className="text-sm font-semibold">Get the drops first.</span>
            <span className="text-xs text-muted-foreground block mt-0.5">The squad hears everything early.</span>
          </div>
        </div>
        {subscribed ? (
          <div className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-success/20 border border-success/40 text-success text-xs font-bold w-full justify-center">
            <Check className="w-3.5 h-3.5" /> You're in ❤️‍🔥.
          </div>
        ) : (
          <form onSubmit={handleNewsletter} className="flex gap-2">
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Your email"
              className="flex-1 px-4 py-2.5 rounded-full text-foreground text-sm bg-card border-0 focus:outline-none focus:ring-2 focus:ring-accent/50"
            />
            <button type="submit" disabled={subscribing} className="px-5 py-2.5 rounded-full bg-gradient-cta text-white font-bold text-sm whitespace-nowrap disabled:opacity-60 active:scale-95 transition">
              {subscribing ? <Loader2 className="w-4 h-4 animate-spin" /> : "I'm In"}
            </button>
          </form>
        )}
      </div>

      {/* Waving mascot — last thing before the footer */}
      <div className="flex justify-center py-8">
        <MascotStandee mascot="waving" className="w-36 h-36" alt="Holy Grills mascot waving" />
      </div>
      </motion.div>

      {showStreakPopup && (
        <ModalPortal>
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-lg flex items-end sm:items-center justify-center p-4" onClick={() => setShowStreakPopup(false)}>
          <motion.div
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="bg-card rounded-3xl p-6 w-full max-w-sm text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-end mb-1">
              <button onClick={() => setShowStreakPopup(false)} className="text-muted-foreground text-xs font-bold">✕</button>
            </div>
            <motion.div
              animate={{ scale: [1, 1.1, 1], rotate: [0, -3, 3, 0] }}
              transition={{ duration: 1.5, repeat: Infinity }}
              className="w-16 h-16 rounded-full bg-gradient-cta flex items-center justify-center mx-auto mb-3 shadow-glow"
            >
              <FlameMark className="w-9 h-9" />
            </motion.div>
            <h3 className="font-heading font-extrabold text-base text-foreground flex items-center justify-center gap-1.5">Your Streak 🔥</h3>
            <motion.div
              key={streak?.streak_count ?? streak?.current_streak ?? 0}
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', stiffness: 200 }}
              className="font-heading font-extrabold text-4xl text-primary my-2"
            >
              <CountUp value={streak?.streak_count ?? streak?.current_streak ?? streak?.days ?? streak?.count ?? 0} />
            </motion.div>
            <p className="text-xs text-muted-foreground">Keep showing up. Your HP multiplier grows with every order.</p>
            <button onClick={() => { setShowStreakPopup(false); navigate('/menu'); }} className="mt-4 w-full py-3 rounded-full bg-gradient-cta text-white font-bold text-sm active:scale-95 transition">Keep it burning →</button>
          </motion.div>
        </div>
        </ModalPortal>
      )}

      <KitchenClosedPopup status={kitchenStatus} scheduledWindows={kitchenStatus?.scheduled_windows || []} />
    </>
  );
}