import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Flame, ChevronRight } from 'lucide-react';
import EarlySupportersSlider from '@/components/storefront/EarlySupportersSlider';
import TestimonialSlider from '@/components/TestimonialSlider';
import SEO from '@/components/SEO';
import { liveApi } from '@/lib/liveApi';
import { getStorefrontSections } from '@/lib/storefrontMockData';

// Last-resort artwork only — the real image comes from the admin panel's
// storefront section of type `our_story`.
const FALLBACK_IMAGE = 'https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=1200&q=80';

// Real student reviews reused from the homepage marketing set — static
// content, not invented data.
const FALLBACK_REVIEWS = [
  { text: "It was wonderful 😭 I was even so full I couldn't finish my chips. I enjoyed the sausage so much with the sauce.", name: 'Omoayena A' },
  { text: "The fries were honestly the best I've had this year. The chicken was so well seasoned and well grilled.", name: 'Owoeye I.B' },
  { text: "Best grill on campus, hands down. The HP rewards make it even sweeter.", name: 'Adewale T' },
];

const STORY_CARDS = [
  { title: 'Done properly', body: 'Marinated deep, grilled on real flame, basted again and again. Nothing boiled first.' },
  { title: 'Predictable windows', body: 'Kitchen Radar tells you when the grill is live and when your food lands. No guessing.' },
  { title: 'Built for students', body: 'Squad Orders, Holy Points and rewards, designed around how students actually eat and gather.' },
];

const METHOD_POINTS = [
  { title: 'Deep marinade.', body: 'Every protein soaks in flavour before the flame ever touches it.' },
  { title: 'Open flame.', body: 'Real fire does the work from start to finish. Nothing boiled first.' },
  { title: 'Repeated basting.', body: 'We baste again and again, so the flavour builds in layers you can taste.' },
  { title: 'Made fresh.', body: 'Prepped daily for every ordering window, so it is fresh when it reaches you.' },
];

const PILLARS = [
  { label: 'Faith', body: 'We believe in what we are building and in the students we serve. Every order gets the same intention, big or small.' },
  { label: 'Love', body: 'The kind that shows up without being asked. In the food, the replies, the little things.' },
  { label: 'Energy', body: 'Fuel for early mornings, late nights and everything between.' },
  { label: 'Flavor', body: 'The craft is real. We do not cut corners, because you do not deserve corners.' },
];

const fade = (delay = 0) => ({
  initial: { opacity: 0, y: 16 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.2 },
  transition: { duration: 0.5, delay },
});

export default function OurStory() {
  const [hero, setHero] = useState({ image: FALLBACK_IMAGE, title: 'The Holy Flame Method', caption: 'Real fire. Real time. Real flavour.' });
  const [testimonials, setTestimonials] = useState(FALLBACK_REVIEWS);

  useEffect(() => {
    let live = true;
    // Reviews pull from the same storefront 'testimonial' source the homepage
    // uses, so both pages show identical, admin-managed reviews.
    getStorefrontSections('testimonial')
      .then((list) => {
        if (!live) return;
        if (Array.isArray(list) && list.length) {
          setTestimonials(list.map((s) => ({
            text: s.content?.review || s.subtitle || s.title || '',
            name: s.content?.name || s.title || 'Student',
          })));
        }
      })
      .catch(() => { /* keep fallback reviews */ });
    liveApi.storefront.getSections({ section_type: 'our_story' })
      .then((list) => {
        if (!live) return;
        const s = (Array.isArray(list) ? list : [])
          .filter((x) => x.is_active !== false)
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))[0];
        if (!s) return;
        setHero({
          image: s.image_url || s.content?.image_url || FALLBACK_IMAGE,
          title: s.title || s.content?.title || 'The Holy Flame Method',
          caption: s.subtitle || s.content?.line || s.content?.subtitle || 'Real fire. Real time. Real flavour.',
        });
      })
      .catch(() => { /* keep the fallback artwork */ });
    return () => { live = false; };
  }, []);

  return (
    <div className="animate-fade-in">
      <SEO
        title="Holy Grills: The Student Flame Grill Built at FUTA, Akure"
        description="Holy Grills is FUTA's student focused flame grill in Akure. Real open flame, campus delivery, Holy Points and a community that shows up together."
      />

      {/* Top of page */}
      <div className="text-center pt-2 max-w-2xl mx-auto">
        <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-primary/5 text-primary text-[11px] font-extrabold uppercase tracking-wider rounded-full">
          <Flame className="w-3.5 h-3.5" /> Our Story
        </span>
        <h1 className="font-heading font-extrabold text-3xl text-foreground mt-3 leading-tight">It started with one grill.</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
          Holy Grills started with one grill outside a hostel and one belief: campus should feel warmer than it does. Food was how we got people together.
        </p>
      </div>

      {/* Hero image with caption chip */}
      <motion.div {...fade()} className="relative rounded-3xl overflow-hidden aspect-[16/9] bg-secondary shadow-card mt-5">
        <img
          src={hero.image}
          alt="Holy Grills flame-grilled food"
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-foreground/85 via-foreground/20 to-transparent" />
        <div className="absolute bottom-4 left-4 right-4 text-white">
          <div className="font-heading font-extrabold text-lg">{hero.title}</div>
          {hero.caption && <div className="text-xs text-white/70">{hero.caption}</div>}
        </div>
      </motion.div>

      {/* The story card */}
      <motion.div
        {...fade()}
        className="rounded-3xl bg-card border border-border p-6 space-y-4 text-sm text-muted-foreground leading-relaxed max-w-2xl mx-auto mt-6"
      >
        <p>
          Not a plan. A table, an umbrella and a grill, set up outside Adeboye Hostel every night. We carried everything out, grilled, then carried it all home.
        </p>
        <p>
          At first we did not know what we were. A grilled meal brand, maybe. Grilled chicken one day, grilled potatoes the next, suya cut after that. We tested everything and watched what brought students back. Next session, had to do things differently. Went deep in learning the art of grilling. Everyone said the secret was in the baste, so we basted boldly. Turns out the secret was consistency. Marinated deep, grilled on real flame, basted again and again. Every single order.
        </p>
        <p>
          The community showed up. But students could not leave where they were to come to us. So we moved fully online, and now the grill comes to you, wherever you are.
        </p>
        <p className="text-foreground font-semibold text-base font-heading">
          And it was never only about the food.
        </p>
        <p>
          Chicken and chips was a choice. It is easy to share and easy to eat while the conversation keeps going. Food is how people end up at the same table, and connection at the table is dear to us.
        </p>
        <p>
          So Holy Grills grew. Windows you can count on. Holy Points for showing up. Events, squads and more that put you closer to what is happening around you. The plate opens the door. What happens next is the point.
        </p>
        <p className="text-foreground font-semibold text-base font-heading">
          We are not trying to be the biggest name in town. We are trying to be the most honest one. The same care as the very first plate. And after this campus? Every campus that deserves better.
        </p>
      </motion.div>

      {/* Three cards */}
      <div className="flex gap-3 overflow-x-auto scrollbar-hide snap-x snap-mandatory -mx-1 px-1 mt-6 md:grid md:grid-cols-3 md:overflow-visible">
        {STORY_CARDS.map((c, i) => (
          <motion.div
            key={c.title}
            {...fade(i * 0.05)}
            className="shrink-0 snap-start w-[78%] sm:w-[60%] md:w-auto rounded-2xl bg-card border border-border p-5"
          >
            <div className="font-heading font-bold text-base text-foreground mb-1.5">{c.title}</div>
            <p className="text-xs text-muted-foreground leading-relaxed">{c.body}</p>
          </motion.div>
        ))}
      </div>

      {/* Student reviews strip */}
      <section className="space-y-3 mt-8">
        <div>
          <span className="hg-eyebrow">Student reviews</span>
          <h2 className="font-heading font-extrabold text-lg text-foreground">The table talks.</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Word for word, unedited.</p>
        </div>
        <TestimonialSlider testimonials={testimonials} />
      </section>

      {/* The First Believers */}
      <div className="mt-8">
        <EarlySupportersSlider />
      </div>

      {/* The Holy Flame Method */}
      <motion.section {...fade()} className="mt-9 space-y-4">
        <div>
          <span className="hg-eyebrow">How we grill</span>
          <h2 className="font-heading font-extrabold text-xl text-foreground">Not a slogan. A process.</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Every plate, every time.</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {METHOD_POINTS.map((p, i) => (
            <motion.div key={p.title} {...fade(i * 0.05)} className="rounded-2xl bg-card border border-border p-4">
              <div className="font-heading font-bold text-sm text-foreground mb-1">{p.title}</div>
              <p className="text-xs text-muted-foreground leading-relaxed">{p.body}</p>
            </motion.div>
          ))}
        </div>
        <p className="font-heading italic font-bold text-base text-foreground text-center px-2">We soak it long. We baste it strong 🔥.</p>
        <p className="text-sm text-muted-foreground text-center">When we say grilled, it is grilled. Ask how it got there 😉.</p>
      </motion.section>

      {/* Four pillars */}
      <motion.section {...fade()} className="mt-9 space-y-4">
        <div>
          <span className="hg-eyebrow">Our pillars</span>
          <h2 className="font-heading font-extrabold text-xl text-foreground">Four words. One standard.</h2>
          <p className="text-sm text-muted-foreground mt-1.5 max-w-lg">Not decoration. A daily standard, in the marinade and in how we reply to your message.</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {PILLARS.map((p, i) => (
            <motion.div key={p.label} {...fade(i * 0.05)} className="rounded-2xl bg-card border border-border p-4">
              <div className="font-heading font-extrabold text-base text-primary mb-1">{p.label}</div>
              <p className="text-xs text-muted-foreground leading-relaxed">{p.body}</p>
            </motion.div>
          ))}
        </div>
      </motion.section>

      {/* Who it's for */}
      <motion.section {...fade()} className="mt-9 text-center max-w-xl mx-auto">
        <span className="hg-eyebrow">Who it is for</span>
        <h2 className="font-heading font-extrabold text-xl text-foreground mt-1">Built for students.</h2>
        <p className="text-sm text-muted-foreground leading-relaxed mt-3">
          After a long day of lectures. After the test you did or did not study enough for. After a week with no time for your friends. Holy Grills is for the moment you want something better, and people to share it with. Game night. Movie night. A random Tuesday that turned into a memory. The food gets you there. The bonding is the point.
        </p>
      </motion.section>

      {/* Mission and vision */}
      <motion.section {...fade()} className="mt-9 space-y-3">
        <div className="text-center">
          <span className="hg-eyebrow">Where we are going</span>
          <h2 className="font-heading font-extrabold text-xl text-foreground mt-1">More than a plate.</h2>
          <p className="text-xs text-muted-foreground mt-0.5">One mission. One vision.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-2xl bg-card border border-border p-5">
            <div className="font-heading font-bold text-sm text-foreground mb-1.5">Our Mission</div>
            <p className="text-xs text-muted-foreground leading-relaxed">To strengthen student connection on campus, starting with food and growing into everything that makes campus life worth showing up for.</p>
          </div>
          <div className="rounded-2xl bg-card border border-border p-5">
            <div className="font-heading font-bold text-sm text-foreground mb-1.5">Our Vision</div>
            <p className="text-xs text-muted-foreground leading-relaxed">A campus where it is easy to find what is happening, easy to be part of it, and rewarding to show up. Food is where it starts. It is just not where it ends.</p>
          </div>
        </div>
      </motion.section>

      {/* Closing card */}
      <motion.div {...fade()} className="rounded-3xl bg-gradient-cta p-7 text-white text-center shadow-glow mt-9">
        <h3 className="font-heading font-extrabold text-2xl leading-tight">Bring your people.</h3>
        <h3 className="font-heading font-extrabold text-2xl leading-tight">We bring the fire.</h3>
        <Link to="/menu" className="inline-flex items-center gap-1.5 px-5 py-3 rounded-full bg-white text-primary font-bold text-sm active:scale-95 transition mt-5">
          View the menu <ChevronRight className="w-4 h-4" />
        </Link>
      </motion.div>
    </div>
  );
}