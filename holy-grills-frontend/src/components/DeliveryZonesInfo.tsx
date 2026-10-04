import { useState, useEffect } from 'react';
import { MapPin, ChevronDown, Clock } from 'lucide-react';
import { mockApi } from '@/lib/mockApi';
import { formatNaira } from '@/lib/hgUtils';

// GET /orders/delivery-zones (public) → zones with fees + estimated delivery times.
// Shown as a collapsible info card inside the Checkout delivery-location card so
// students can see all zones and fees at a glance beyond the hostel/gate pickers.
export default function DeliveryZonesInfo() {
  const [zones, setZones] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const load = async () => {
      try {
        const z = await mockApi.orders.getDeliveryZones();
        if (!cancelled) setZones(Array.isArray(z) ? z : []);
      } catch { if (!cancelled) setZones([]); }
    };
    load();
    return () => { cancelled = true; };
  }, [open]);

  return (
    <div className="mt-3">
      <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-1.5 text-xs font-semibold text-primary">
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
        {open ? 'Hide delivery zones' : 'View delivery zones & fees'}
      </button>
      {open && (
        <div className="mt-2 space-y-1.5 animate-fade-in">
          {zones.length === 0 && <p className="text-xs text-muted-foreground">No delivery zones configured.</p>}
          {zones.map((z) => (
            <div key={z.id} className="flex items-center justify-between p-2.5 rounded-xl bg-card border border-border text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <MapPin className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                <span className="font-semibold text-foreground truncate">{z.name}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {z.estimated_delivery_time && (
                  <span className="text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> {z.estimated_delivery_time}</span>
                )}
                <span className="font-bold text-primary">{formatNaira(z.delivery_fee ?? z.fee ?? 0)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}