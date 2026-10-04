import React, { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Flame, Search, Mail, Phone } from 'lucide-react';

const CATS = [
  'All',
  'About Holy Grills',
  'Orders & Delivery',
  'The Food',
  'Holy Points & Rewards',
  'Payment & Wallet',
  'Account & Profile',
  'Campus & Community',
];

const FAQS = [
  // About Holy Grills
  { q: 'What is Holy Grills?', a: 'A student meal brand built on one idea: good food is better shared. You bring your people. We bring the fire. Holy Points make showing up count.', c: 'About Holy Grills' },
  { q: 'Is Holy Grills just a food brand?', a: 'Food is where we started, and it is still the heart of it. But Holy Grills is really about bringing people together. The plate gets you to the table. What grows from there is the point ❤️‍🔥.', c: 'About Holy Grills' },
  { q: 'Why food?', a: 'Because food gets people together, every day, around the same plate.', c: 'About Holy Grills' },
  { q: 'Why chicken and chips?', a: 'Because it is easy to share and easy to eat while you are talking and laughing. The plate should join the conversation, not interrupt it.', c: 'About Holy Grills' },
  { q: 'Who is Holy Grills for?', a: 'Students. Tired after lectures, busy all day, short on time for your friends. This is your reason to gather.', c: 'About Holy Grills' },
  { q: 'Who is behind Holy Grills?', a: 'A student who believed campus deserved better. Still built by students, for students.', c: 'About Holy Grills' },
  { q: 'Which campuses are you on?', a: 'One campus for now, done properly. When that changes, you will hear it from us first.', c: 'About Holy Grills' },
  { q: 'Is Holy Grills a restaurant?', a: 'No tables, no waiters. A student brand built around a grill and the people who gather because of it.', c: 'About Holy Grills' },
  { q: 'Why "Made With More Than Flame"?', a: 'Because the flame is only part of it. The rest is warmth and the people you share it with, built on Faith, Love, Energy and Flavor.', c: 'About Holy Grills' },

  // Orders & Delivery
  { q: 'How does ordering work?', a: 'We take orders in windows during the day and deliver in the evening, after the long one you have had. Chicken and a side is a night meal, so think of us as a campus night market. Delivery windows can differ, and we will tell you yours.', c: 'Orders & Delivery' },
  { q: 'Can I order with my friends?', a: 'Yes. Start a Squad Order, add your items and send the link to your people. Everyone adds theirs, and the whole crew shares the perks.', c: 'Orders & Delivery' },
  { q: 'When does the kitchen open?', a: 'Check the Kitchen Radar on Home or Menu. It shows whether the grill is live for orders.', c: 'Orders & Delivery' },
  { q: 'Where do you deliver?', a: 'School gates and campus hostels. Checkout shows what is available to you. More spots as we grow.', c: 'Orders & Delivery' },
  { q: 'How long does delivery take?', a: 'Your plate lands in your delivery window. It can differ from day to day, and we will tell you yours. You can follow your order live.', c: 'Orders & Delivery' },
  { q: 'Can someone pick it up for me?', a: 'Yes. Give them your name, order code or phone number.', c: 'Orders & Delivery' },
  { q: 'How do I track my order?', a: 'Open My Orders. It shows the preparation and transition of your order from received to delivered.', c: 'Orders & Delivery' },
  { q: 'What if I miss my order?', a: 'Every plate is made fresh, so we cannot hold or resell it. Uncollected orders are cancelled and not refundable.', c: 'Orders & Delivery' },
  { q: 'Can I cancel after paying?', a: 'Yes, until the kitchen starts preparing your order. Once it has started, it cannot be cancelled.', c: 'Orders & Delivery' },
  { q: 'Can I save an item for later?', a: 'Yes. Tap the heart on any item to save it to your favourites.', c: 'Orders & Delivery' },
  { q: 'What if my order includes a sold out item?', a: 'We will ask you to remove it before you check out. You are never charged for food that is not coming.', c: 'Orders & Delivery' },
  { q: 'What if something is wrong with my order?', a: 'Message us straight away. We will own it and make it right.', c: 'Orders & Delivery' },

  // The Food
  { q: 'What is the Holy Flame Method?', a: 'Our standard. A deep marinade, open flame, repeated basting. Nothing boiled first. A process, not a slogan.', c: 'The Food' },
  { q: 'When you say grilled, is it really grilled?', a: 'Always. If a menu item says grilled, it is grilled. If it does not, you will know it is not.', c: 'The Food' },
  { q: 'Can I customise my plate?', a: 'Yes. On most plates you can add, remove and choose your sauce and protein. Two people can order the same item and get different plates. Same fire, your plate.', c: 'The Food' },
  { q: 'How fresh is the food?', a: 'We prep daily, which is why we run ordering and delivery windows. Every plate is fresh when it reaches you.', c: 'The Food' },
  { q: 'What if I have food allergies?', a: 'Check the ingredients before you order. Our kitchen is shared, so cross contamination can happen. If your allergy is serious, message us first.', c: 'The Food' },

  // Holy Points & Rewards
  { q: 'How do Holy Points work?', a: 'Holy Points say thank you for showing up. You earn them at the table, by ordering, joining events, keeping streaks, leaving reviews and bringing friends. You spend them across Holy Grills.', c: 'Holy Points & Rewards' },
  { q: 'Are Holy Points just loyalty points?', a: 'Loyalty points reward buying food. Holy Points reward showing up, and they work across Holy Grills, not just at the kitchen.', c: 'Holy Points & Rewards' },
  { q: 'Can I redeem Holy Points for food?', a: 'Yes. Free sides, upgrades and drops. Head to Rewards.', c: 'Holy Points & Rewards' },
  { q: 'How do I earn HP by bringing a friend?', a: 'Bring a friend and earn HP. Referral HP lands straight in your Active balance.', c: 'Holy Points & Rewards' },
  { q: 'What are daily streaks?', a: 'Come back and keep the streak going. Your bonus grows.', c: 'Holy Points & Rewards' },
  { q: 'What is the difference between Active and Pending HP?', a: 'Pending is on its way. It becomes Active once your order is delivered, and Active is what you can spend.', c: 'Holy Points & Rewards' },
  { q: 'Do my Holy Points expire?', a: 'Keep showing up and they stay with you. Go quiet for a long stretch and they slowly fade 😉.', c: 'Holy Points & Rewards' },
  { q: 'How do tiers work?', a: 'You climb from Ember to Flame to Blaze to Holy. Each tier makes your points work harder. Stay active to keep your tier.', c: 'Holy Points & Rewards' },
  { q: 'Where do I spend my HP?', a: 'On event tickets, rewards, and challenges with exclusive prizes. The Marketplace joins the list soon.', c: 'Holy Points & Rewards' },
  { q: 'Can I send HP to a friend?', a: 'Yes. Send some of your active HP to a fellow student from the Holy Points page.', c: 'Holy Points & Rewards' },
  { q: 'What is the leaderboard?', a: 'It shows who is showing up most, this week, this month or all time. Top spots win real rewards, and rankings reset every month.', c: 'Holy Points & Rewards' },
  { q: 'What is the Hall of Fame?', a: 'Where students who stay at the top, month after month, are inducted. One big month is not enough. Members get exclusive rewards to match their status, and as Holy Grills grows, so does their name.', c: 'Holy Points & Rewards' },
  { q: 'What are Order Locks?', a: 'Lock a reward for a day you choose. Order that day and it applies automatically. Plans change, so you can reschedule. If the day passes, it expires.', c: 'Holy Points & Rewards' },

  // Payment & Wallet
  { q: 'How do I pay?', a: 'Card, Wallet, or both. Payments run through secure partners.', c: 'Payment & Wallet' },
  { q: 'What is the Wallet?', a: 'Fund it once and pay faster every time.', c: 'Payment & Wallet' },
  { q: 'Is my card safe?', a: 'We never store your card details.', c: 'Payment & Wallet' },
  { q: 'My payment did not go through.', a: 'Try again or switch method. Still stuck? Message us on WhatsApp and we will sort it 😂.', c: 'Payment & Wallet' },
  { q: 'Do you offer refunds?', a: 'Refunds apply when Holy Grills cancels or cannot fulfil your order. Uncollected orders are not refundable. Wallet funds are not refundable except where the law requires or where we cancel. Full detail is in our Terms.', c: 'Payment & Wallet' },

  // Account & Profile
  { q: 'Do I need an account?', a: 'You can order as a guest, but guests do not earn Holy Points. An account is the better plan ❤️‍🔥.', c: 'Account & Profile' },
  { q: 'Who can create an account?', a: 'You need to be at least 16.', c: 'Account & Profile' },
  { q: 'How do I contact Holy Grills?', a: 'WhatsApp, email or call. Details are below. We reply.', c: 'Account & Profile' },
  { q: 'How do I delete my data?', a: 'Email us and we will help. Your data is yours.', c: 'Account & Profile' },

  // Campus & Community
  { q: 'What are Events?', a: 'Everything worth showing up for, in one place. Find it, go with your people, and check in to earn HP. You can spend HP on tickets too.', c: 'Campus & Community' },
  { q: 'I am organising an event. Can Holy Grills help?', a: 'Yes. We help you reach students who actually want to hear about it, not just host a ticket page. Message us with your plans.', c: 'Campus & Community' },
  { q: 'What is the Marketplace?', a: 'Where you will buy from students and campus businesses with HP or cash. Vouchers, tickets, goodies and services. Opening soon.', c: 'Campus & Community' },
  { q: 'Can I sell on the Marketplace?', a: 'Soon enough.', c: 'Campus & Community' },
  { q: 'Do you do catering?', a: 'Yes. Tell us the date and we will handle the flame. No account needed.', c: 'Campus & Community' },
];

// The nine that show first in the All view, in this order.
const NINE_DEFAULTS = [
  'What is Holy Grills?',
  'How does ordering work?',
  'Can I order with my friends?',
  'Can I customise my plate?',
  'Where do you deliver?',
  'How do Holy Points work?',
  'Do you do catering?',
  'Do I need an account?',
  'Can I cancel after paying?',
];

const CAT_ORDER = CATS.filter((c) => c !== 'All');

function buildList(category) {
  if (category === 'All') {
    const byQ = new Map(FAQS.map((f) => [f.q, f]));
    const nine = NINE_DEFAULTS.map((q) => byQ.get(q)).filter(Boolean);
    const nineSet = new Set(NINE_DEFAULTS);
    const rest = CAT_ORDER.flatMap((c) => FAQS.filter((f) => f.c === c && !nineSet.has(f.q)));
    return [...nine, ...rest];
  }
  return FAQS.filter((f) => f.c === category);
}

function Highlight({ text, query }) {
  if (!query) return <>{text}</>;
  const safe = query.trim();
  if (!safe) return <>{text}</>;
  const re = new RegExp(`(${safe.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig');
  const parts = text.split(re);
  const low = safe.toLowerCase();
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === low ? (
          <mark key={i} className="bg-primary/15 text-foreground rounded px-0.5">{part}</mark>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}
    </>
  );
}

export default function FAQ() {
  const [open, setOpen] = useState(0);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');

  const list = useMemo(() => {
    const base = query ? FAQS : buildList(category);
    if (!query) return base;
    const q = query.toLowerCase();
    return base.filter((f) => (f.q + f.a).toLowerCase().includes(q));
  }, [category, query]);

  return (
    <div className="space-y-5 animate-fade-in max-w-3xl mx-auto">
      {/* Header */}
      <div className="text-center pt-2">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/5 text-primary text-[11px] font-extrabold uppercase tracking-wider rounded-full">
          <Flame className="w-3.5 h-3.5" /> FAQ
        </span>
        <h1 className="font-heading font-extrabold text-3xl text-foreground mt-3">Ask Away</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
          Quick answers on food, orders and Holy Points.
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the FAQs..."
          className="w-full pl-11 pr-4 py-3 rounded-full bg-card border border-border text-sm focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-colors"
        />
      </div>

      {/* Category chips */}
      <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-1 px-1 pb-1">
        {CATS.map((c) => {
          const isActive = (query ? false : category === c);
          return (
            <button
              key={c}
              onClick={() => { setCategory(c); setQuery(''); }}
              className={`shrink-0 px-3.5 py-2 rounded-full text-xs font-bold transition ${isActive ? 'bg-gradient-cta text-white' : 'bg-card border border-border text-foreground'}`}
            >
              {c}
            </button>
          );
        })}
      </div>

      {/* Questions */}
      <div className="space-y-2.5">
        {list.length === 0 && (
          <p className="text-center text-sm text-muted-foreground py-8">Nothing found. Ask us.</p>
        )}
        {list.map((f, i) => {
          const isOpen = open === i;
          return (
            <div key={f.q} className="rounded-2xl bg-card border border-border overflow-hidden">
              <button
                onClick={() => setOpen(isOpen ? -1 : i)}
                className="w-full flex items-center justify-between p-4 text-left"
              >
                <span className="font-bold text-sm text-foreground pr-3"><Highlight text={f.q} query={query} /></span>
                <Plus className={`w-4 h-4 text-muted-foreground shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-45' : ''}`} />
              </button>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4 text-sm text-muted-foreground leading-relaxed"><Highlight text={f.a} query={query} /></div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {/* Closing card */}
      <div className="rounded-3xl bg-gradient-dark p-6 text-center text-white shadow-card">
        <h3 className="font-heading font-extrabold text-lg mb-1">Still not seeing it?</h3>
        <p className="text-sm text-white/70 mb-4">Talk to us. We reply.</p>
        <div className="flex flex-wrap items-center justify-center gap-2.5 text-sm">
          <a href="mailto:grillthevibe@gmail.com" className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-white/10 border border-white/15 hover:bg-white/15 transition-colors font-semibold">
            <Mail className="w-4 h-4" /> Email us
          </a>
          <a href="tel:07053263931" className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full bg-white/10 border border-white/15 hover:bg-white/15 transition-colors font-semibold">
            <Phone className="w-4 h-4" /> Call us
          </a>
          <Link to="/menu" className="px-5 py-2.5 rounded-full bg-gradient-cta font-bold active:scale-95 transition">Order now →</Link>
        </div>
      </div>
    </div>
  );
}