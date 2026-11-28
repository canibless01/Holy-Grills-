import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Shield, Flame, Mail, FileText, Lock, ArrowUp } from 'lucide-react';
import SEO from '@/components/SEO';
import { metaForPath } from '@/seo/routeMeta';

/** Head data for /terms — same object the pre-render writes (src/seo/routeMeta.ts). */
const META = metaForPath('/terms');

const TERMS = [
  { n: 1, title: 'Welcome to Holy Grills', body: 'These Terms are the ground rules for using the Holy Grills app and website. By creating an account, placing an order or otherwise using Holy Grills, you agree to them. If you do not agree, please do not use the app. Holy Grills is built for students and staff on and around campus, and runs as a campus food service and community. We are glad you are here.' },
  { n: 2, title: 'Your account', body: 'You need to be at least 16 to create an account. You can order as a guest, but guests do not earn Holy Points, rewards or tiers. An account is the better plan. Keep your login details safe. You are responsible for what happens on your account, so tell us straight away if you think someone else has used it. Give us accurate information and keep it up to date.' },
  { n: 3, title: 'Ordering windows and delivery', body: 'We take orders during ordering windows and deliver during delivery windows. Windows can differ from day to day, and we will tell you yours. Check the Kitchen Radar to see whether the grill is live. Delivery times are estimates and can shift with location and things outside our control. Please give us accurate delivery details and be reachable when your order arrives. If we cannot reach you after reasonable attempts, the order is treated as unpicked under section 7.' },
  { n: 4, title: 'Orders, pricing and availability', body: 'Prices are shown in Naira and include applicable taxes where required. Items are subject to availability. If something sells out, we will ask you to remove it from your cart, so you are never charged for food we cannot deliver. If a price or description is clearly wrong, we may correct it or cancel the order and refund you. Squad Orders follow the minimums and perks shown in the app when you order, and Holy Points from a squad order are shared across the squad.' },
  { n: 5, title: 'Holy Points and rewards', body: 'Holy Points (HP) are earned through orders, streaks, events, challenges, reviews and referrals. Pending HP becomes Active after your order is delivered. HP has no cash value outside the app and cannot be transferred except where we explicitly allow it, like sending HP to a friend. Tiers, the leaderboard, spins, challenges, Order Locks and the Hall of Fame work by the rules shown in the app. Rewards and prizes may change over time. We may adjust HP balances to correct errors or remove points earned through fraud.' },
  { n: 6, title: 'Wallet and payments', body: 'You can fund your in app Wallet or pay with a card, and you can split a payment between the two. Wallet funds are not refundable except where the law requires or where we cancel an order on our side. If an order is cancelled before the kitchen starts, any Wallet portion goes back to your balance. Payment details are handled by secure payment partners, and Holy Grills does not store your card details.' },
  { n: 7, title: 'Unpicked orders and cancellations', body: 'Every plate is made fresh for you. You can cancel until the kitchen starts preparing your order. Once preparation has started, it cannot be cancelled. Orders not collected in time are returned to the kitchen, and no refunds are issued for unpicked orders. If you cannot make it, you may send a rider to collect it at your own arrangement and cost.' },
  { n: 8, title: 'Food and allergens', body: 'We work hard to keep menu descriptions accurate, but ingredients and allergen information can change. You are responsible for checking ingredients if you have allergies or dietary restrictions. Our kitchen is a shared space, so cross contamination may occur.' },
  { n: 9, title: 'Reviews and what you post', body: 'Reviews and anything else you post must be honest and your own. You give Holy Grills permission to show them on the site and in our channels, and a review may appear in more than one place. We may remove content that is abusive, misleading or unlawful.' },
  { n: 10, title: 'Marketplace and events', body: 'The Marketplace lets students and campus businesses list vouchers, tickets, goodies and services. Sellers are responsible for what they list. We may remove listings that are misleading or unsafe. Events shown on Holy Grills are run by their organisers, and HP for events follows the rules shown with each event.' },
  { n: 11, title: 'Conduct on the platform', body: 'Do not abuse, harass or mislead Holy Grills staff, riders or other students. Do not try to game Holy Points, refer yourself, or place fraudulent orders. Do not misuse the app or try to break it.' },
  { n: 12, title: 'Suspension and ending your account', body: 'We may suspend or close accounts that break these Terms, void points earned unfairly, or refuse service. You can stop using Holy Grills at any time and ask us to delete your account.' },
  { n: 13, title: 'Third party services', body: 'Payments, delivery tools and messaging may involve third party services. Their own terms apply to those services.' },
  { n: 14, title: 'Things outside our control', body: 'We are not responsible for delays or failures caused by things beyond our control, like weather, power or network outages, campus closures, or payment partner downtime.' },
  { n: 15, title: 'Our brand', body: 'Everything on the site, including logos, graphics, images, text and designs, belongs to Holy Grills. Please do not copy, reproduce, distribute or build on our content without our written permission.' },
  { n: 16, title: 'Our limits', body: 'Holy Grills is not liable for indirect, incidental or consequential damages. You use the site and services at your own risk.' },
  { n: 17, title: 'Governing law', body: 'These Terms are governed by the laws of the Federal Republic of Nigeria. Disputes may be resolved in the courts of Ondo State.' },
  { n: 18, title: 'Changes to these Terms', body: 'We may update these Terms as Holy Grills grows. Material changes will be highlighted in the app and on this page. Continuing to use Holy Grills after a change means you accept the updated Terms.' },
  { n: 19, title: 'Contact', body: 'Questions? Email grillthevibe@gmail.com or call 07053263931. We are real people. Reach out and we will answer.' },
];

const PRIVACY = [
  { n: 1, title: 'Who we are', body: 'Holy Grills is a student focused meal and campus community brand. In this policy, we and us mean Holy Grills. If you have questions about your data, contact us using the details at the end.' },
  {
    n: 2,
    title: 'What we collect',
    items: [
      { lead: 'What you give us.', text: 'When you create an account or place an order: your name, phone number, email address, delivery or pickup location and order history. If you order as a guest, we collect what we need to complete that order.' },
      { lead: 'What we pick up as you use the app.', text: 'Your IP address, device and browser details, the pages you visit, time spent on the site, and cookies and similar tools. Your activity in the app also counts here: orders, Holy Points, event check ins, Marketplace activity and leaderboard activity.' },
      { lead: 'Your location.', text: 'Only if you allow it, to complete orders or suggest delivery options.' },
      { lead: 'What you post and tell us.', text: 'Reviews, catering requests, messages to us, and anything else you send.' },
      { lead: 'From our partners.', text: 'Our payment partners confirm whether a payment went through. We never receive your full card details.' },
    ],
  },
  {
    n: 3,
    title: 'Why we use it',
    items: [
      'To process and manage your orders.',
      'To deliver or prepare your order for pickup.',
      'To tell you about your order status.',
      'To run Holy Points, rewards, the leaderboard and events.',
      'To personalise your experience and improve the app.',
      'To answer your messages.',
      'To send promotional messages, only with your consent.',
      'To prevent fraud and meet our legal obligations.',
    ],
    close: 'We rely on your consent, on needing your data to fulfil your order, on legal duties, and on our legitimate interest in running and improving Holy Grills.',
  },
  { n: 4, title: 'Cookies', body: 'We use cookies to keep you signed in, remember your cart, speed up the site, understand how it is used, and make helpful suggestions. You can block cookies in your browser settings, but some features may stop working.' },
  { n: 5, title: 'Who we share it with', body: 'We do not sell your personal information. We share data only with service providers, like payment processors, delivery partners, notification services and hosting providers, who follow strict privacy standards. We may share information if Nigerian law requires us to. Your display name and rank may be visible to other students on the leaderboard, and your reviews may be shown on the site.' },
  { n: 6, title: 'Anonymised insights', body: 'We may use anonymised, aggregated information to understand how students use Holy Grills and to improve it. We may share these insights with partners. They never identify you.' },
  { n: 7, title: 'Where your data is kept', body: 'Some of our service providers may store or process data outside Nigeria. Where that happens, we make sure appropriate protections are in place.' },
  { n: 8, title: 'How long we keep it', body: 'We keep your data only as long as we need it for the reasons above, or as the law requires. When we no longer need it, we delete or anonymise it.' },
  { n: 9, title: 'Keeping it safe', body: 'We use industry standard protection: encrypted communication, secure payment gateways and limited access to data. No system is perfectly secure, so please keep your account details private too.' },
  { n: 10, title: 'Your rights', body: 'You can ask to see, correct or delete your personal data. You can object to how we use it, ask us to restrict it, or withdraw your consent at any time. You can also complain to the Nigeria Data Protection Commission. To do any of this, contact us using the details below.' },
  { n: 11, title: 'Marketing and notifications', body: 'We only send promotional messages with your consent, and you can turn notifications off or unsubscribe at any time. Order updates are different. We need to send those so you get your food.' },
  { n: 12, title: 'Children', body: 'Holy Grills does not knowingly collect personal data from anyone under 16. If you believe a child has given us their data, contact us straight away and we will deal with it.' },
  { n: 13, title: 'Changes to this policy', body: 'We may update this policy from time to time. Material changes will be highlighted in the app and on this page. Using Holy Grills after a change means you accept it.' },
  { n: 14, title: 'Contact', body: 'grillthevibe@gmail.com or 07053263931. We are real people. Reach out and we will answer.' },
];

const TABS = [
  { id: 'terms', label: 'Terms of Service', icon: FileText, sections: TERMS },
  { id: 'privacy', label: 'Privacy Policy', icon: Lock, sections: PRIVACY, intro: 'Your information is yours. This page explains what we collect, why we collect it, how we look after it, and what you can do about it. Last updated August 2026.' },
];

export default function TermsPrivacy() {
  const [tab, setTab] = useState('terms');
  const [showTop, setShowTop] = useState(false);
  const active = TABS.find((t) => t.id === tab);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 700);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const jumpTo = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="animate-fade-in max-w-5xl mx-auto">
      <SEO title={META.title} description={META.description} path={META.path} />

      {/* Header */}
      <div className="text-center pt-2">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/5 text-primary text-[11px] font-extrabold uppercase tracking-wider rounded-full">
          <Shield className="w-3.5 h-3.5" /> Your Trust
        </span>
        <h1 className="font-heading font-extrabold text-3xl text-foreground mt-3">Terms & Privacy</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">Plain English. Last updated August 2026.</p>
      </div>

      {/* Tab selector */}
      <div className="grid grid-cols-2 gap-1.5 p-1 rounded-full bg-secondary mt-5 max-w-md mx-auto">
        {TABS.map((t) => {
          const Icon = t.icon;
          const isActive = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`relative flex items-center justify-center gap-1.5 py-2.5 rounded-full text-sm font-bold transition ${isActive ? 'text-white' : 'text-muted-foreground'}`}
            >
              {isActive && (
                <motion.div layoutId="terms-tab" className="absolute inset-0 rounded-full bg-gradient-cta" transition={{ type: 'spring', stiffness: 400, damping: 32 }} />
              )}
              <span className="relative flex items-center gap-1.5"><Icon className="w-4 h-4" /> {t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Body: jump-to sidebar + sections */}
      <div className="mt-6 flex gap-6">
        {/* Jump to list — desktop only */}
        <nav className="hidden lg:block w-56 shrink-0">
          <div className="sticky top-4 space-y-1">
            <div className="text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground px-2 mb-1">Jump to</div>
            {active.sections.map((s) => (
              <button
                key={`${tab}-${s.n}`}
                onClick={() => jumpTo(`sec-${tab}-${s.n}`)}
                className="block w-full text-left text-xs text-muted-foreground hover:text-foreground px-2 py-1.5 rounded-lg hover:bg-secondary transition-colors leading-snug"
              >
                {s.n}. {s.title}
              </button>
            ))}
          </div>
        </nav>

        {/* Sections */}
        <div className="flex-1 min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
              className="space-y-3"
            >
              {active.intro && (
                <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">{active.intro}</p>
              )}
              {active.sections.map((s) => (
                <div key={`${tab}-${s.n}`} id={`sec-${tab}-${s.n}`} className="rounded-2xl bg-card border border-border p-5 scroll-mt-4">
                  <div className="flex items-baseline gap-2.5 mb-2">
                    <span className="font-heading font-extrabold text-primary text-sm">{s.n}</span>
                    <h3 className="font-heading font-bold text-base text-foreground">{s.title}</h3>
                  </div>
                  {s.body && <p className="text-sm text-muted-foreground leading-relaxed">{s.body}</p>}
                  {s.items && (
                    <div className="space-y-2">
                      {s.items.map((it, idx) => {
                        const isLeadItem = typeof it === 'object';
                        return (
                          <div key={idx} className="text-sm text-muted-foreground leading-relaxed">
                            {isLeadItem ? (
                              <>
                                <span className="font-bold text-foreground">{it.lead}</span> {it.text}
                              </>
                            ) : (
                              <span className="flex gap-2"><span className="text-primary mt-1 w-1.5 h-1.5 rounded-full bg-primary shrink-0" />{it}</span>
                            )}
                          </div>
                        );
                      })}
                      {s.close && <p className="text-sm text-muted-foreground leading-relaxed pt-1">{s.close}</p>}
                    </div>
                  )}
                </div>
              ))}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Closing card */}
      <div className="rounded-3xl bg-gradient-dark p-6 text-center text-white shadow-card mt-6 max-w-2xl mx-auto">
        <Flame className="w-6 h-6 mx-auto mb-2 text-accent" />
        <h3 className="font-heading font-extrabold text-lg mb-1">Questions about your data?</h3>
        <p className="text-sm text-white/70 mb-4">Ask us. We will answer.</p>
        <div className="flex flex-wrap items-center justify-center gap-2.5 text-sm">
          <a href="mailto:grillthevibe@gmail.com" className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-white/10 border border-white/15 hover:bg-white/15 transition-colors font-semibold">
            <Mail className="w-4 h-4" /> Email us
          </a>
          <Link to="/faq" className="px-5 py-2.5 rounded-full bg-gradient-cta font-bold active:scale-95 transition">Read the FAQs →</Link>
        </div>
      </div>

      {/* Back to top */}
      {showTop && (
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-5 right-5 z-40 w-11 h-11 rounded-full bg-gradient-cta text-white shadow-glow flex items-center justify-center active:scale-90 transition"
          aria-label="Back to top"
        >
          <ArrowUp className="w-5 h-5" />
        </button>
      )}
    </div>
  );
}