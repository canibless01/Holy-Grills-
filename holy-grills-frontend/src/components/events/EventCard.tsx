import { Calendar, MapPin, Flame, Star } from 'lucide-react';
import { formatDateTime, formatNaira } from '@/lib/hgUtils';

export default function EventCard({ event, onClick }) {
  // list_events returns a lightweight column set (no is_paid/ticket_price/image_url),
  // so the card only renders fields the list actually provides. Price shows only when
  // the backend includes it; otherwise the detail page carries full pricing.
  const price = event.ticket_price ?? null;
  const hasPrice = event.is_paid != null && price != null;
  const isFree = hasPrice ? (!event.is_paid || price === 0) : true;
  const hpReward = event.hp_reward ?? 0;

  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-2xl bg-card border border-border overflow-hidden hover:shadow-card hover:border-primary/20 transition-all duration-300 active:scale-[0.99]"
    >
      <div className="relative aspect-[16/9] bg-secondary">
        {event.image_url ? (
          <img src={event.image_url} alt={event.title} loading="lazy" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Calendar className="w-8 h-8 text-muted-foreground/30" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-foreground/70 to-transparent" />
        <div className="absolute bottom-2 left-3 right-3">
          <h3 className="font-heading font-bold text-white text-base leading-tight line-clamp-2">{event.title}</h3>
          <div className="flex items-center gap-1.5 mt-1 text-xs text-white/80">
            <Calendar className="w-3 h-3" />
            {formatDateTime(event.starts_at)}
          </div>
        </div>
        {event.is_featured && (
          <span className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-full bg-gradient-cta text-white text-[10px] font-bold shadow-sm">
            <Star className="w-2.5 h-2.5" /> Featured
          </span>
        )}
      </div>
      <div className="p-3">
        {event.description && <p className="text-xs text-muted-foreground line-clamp-2 mb-2">{event.description}</p>}
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1 text-xs text-muted-foreground min-w-0">
            <MapPin className="w-3 h-3 shrink-0" />
            <span className="truncate">{event.location}</span>
          </span>
          <div className="flex items-center gap-1.5 shrink-0">
            {hasPrice && (
              <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${isFree ? 'bg-success/15 text-success' : 'bg-secondary text-foreground'}`}>
                {isFree ? 'FREE' : formatNaira(price)}
              </span>
            )}
            {hpReward > 0 && (
              <span className="flex items-center gap-0.5 px-2 py-1 rounded-full bg-primary/5 text-primary text-[10px] font-bold">
                <Flame className="w-2.5 h-2.5" />+{hpReward}
              </span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}