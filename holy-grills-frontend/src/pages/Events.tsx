import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, RefreshCw } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import EventsSkeleton from '@/components/skeletons/EventsSkeleton';
import SEO from '@/components/SEO';
import { metaForPath } from '@/seo/routeMeta';
import EventCard from '@/components/events/EventCard';
import MyEvents from '@/components/events/MyEvents';
import CateringRequestModal from '@/components/events/CateringRequestModal';
import MascotStandee from '@/components/mascot/MascotStandee';
import { useHolyGrill } from '@/lib/HolyGrillContext';

/** Head data for /events — the same object the pre-render writes. */
const META = metaForPath('/events');

const CATEGORIES = [
  { id: 'all', label: 'All' },
  { id: 'party', label: 'Parties' },
  { id: 'food_fest', label: 'Food Fest' },
  { id: 'workshop', label: 'Workshops' },
  { id: 'catering', label: 'Catering' },
];

const unwrap = (res) => {
  if (Array.isArray(res)) return res;
  if (res?.data && Array.isArray(res.data)) return res.data;
  if (res?.events && Array.isArray(res.events)) return res.events;
  return [];
};

export default function Events() {
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [showCatering, setShowCatering] = useState(false);
  const [filter, setFilter] = useState('all');
  const [tab, setTab] = useState('discover');
  const { isAuthenticated } = useHolyGrill();

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setEvents(unwrap(await liveApi.events.list()));
    } catch (e) {
      console.error(e);
      setLoadError(e?.message || 'Could not load events');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = events.filter((e) => {
    if (filter === 'all') return true;
    return e.metadata?.category === filter || e.category === filter;
  });

  if (loading) return <EventsSkeleton />;

  return (
    <div className="space-y-5 animate-fade-in max-w-2xl mx-auto">
      <SEO title={META.title} description={META.description} path={META.path} />

      <div className="flex items-center justify-between">
        <div>
          <span className="hg-eyebrow">Events</span>
          <h1 className="font-heading font-extrabold text-2xl text-foreground mt-0.5">Somewhere to be.</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Go with your people.</p>
        </div>
        <button
          onClick={() => setShowCatering(true)}
          className="flex items-center gap-1 px-3 py-2 rounded-full bg-gradient-cta text-white text-xs font-bold transition-all active:scale-95"
        >
          <Plus className="w-3.5 h-3.5" /> Catering
        </button>
      </div>

      {isAuthenticated && (
        <div className="flex gap-2 bg-secondary/60 rounded-full p-1">
          <button onClick={() => setTab('discover')} className={`flex-1 py-2 rounded-full text-xs font-bold transition-all ${tab === 'discover' ? 'bg-gradient-cta text-white shadow-glow' : 'text-muted-foreground'}`}>Discover</button>
          <button onClick={() => setTab('mine')} className={`flex-1 py-2 rounded-full text-xs font-bold transition-all ${tab === 'mine' ? 'bg-gradient-cta text-white shadow-glow' : 'text-muted-foreground'}`}>My Events</button>
        </div>
      )}

      {tab === 'mine' ? (
        <MyEvents />
      ) : (
        <>
          <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-1 px-1">
            {CATEGORIES.map((c) => (
              <button
                key={c.id}
                onClick={() => setFilter(c.id)}
                className={`px-4 py-2 rounded-full text-xs font-bold whitespace-nowrap transition-all ${filter === c.id ? 'bg-gradient-cta text-white shadow-glow' : 'bg-card text-foreground border border-border hover:border-primary/20'}`}
              >
                {c.label}
              </button>
            ))}
          </div>

          {loadError ? (
            <div className="text-center py-12">
              <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto mb-3" alt="Could not load events" />
              <p className="text-sm font-semibold text-foreground">Something slipped. Try again.</p>
              <button onClick={load} className="mt-3 inline-flex items-center gap-1.5 px-5 py-2.5 rounded-full bg-gradient-cta text-white text-xs font-bold active:scale-95 transition">
                <RefreshCw className="w-3.5 h-3.5" /> Try again
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12">
              <MascotStandee mascot="thinking" className="w-28 h-28 mx-auto mb-3" alt="No events listed" />
              <p className="text-sm font-semibold text-foreground">Nothing on yet. Check back.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filtered.map((event) => (
                <EventCard key={event.id} event={event} onClick={() => navigate(`/events/${event.id}`)} />
              ))}
            </div>
          )}
        </>
      )}

      <CateringRequestModal open={showCatering} onClose={() => setShowCatering(false)} />
    </div>
  );
}