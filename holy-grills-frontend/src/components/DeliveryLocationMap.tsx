import { useEffect, useState, type ComponentProps } from 'react';
import OffCampusMap from '@/components/OffCampusMap';

/** Reuse saved coordinates without creating a Google map or Places session. */
export default function DeliveryLocationMap({ savedAddressId, ...props }: ComponentProps<typeof OffCampusMap> & { savedAddressId?: string | null }) {
  const [editing, setEditing] = useState(false);
  useEffect(() => { setEditing(false); }, [savedAddressId]);
  if (savedAddressId && props.pin && !editing) {
    return <div className="rounded-xl border border-border bg-muted/30 p-3 space-y-2">
      <p className="text-sm font-semibold">Saved delivery pin selected</p>
      <p className="text-xs text-muted-foreground">We’ll use this saved location. No need to open the map again.</p>
      <button type="button" onClick={() => setEditing(true)} className="text-sm font-bold text-primary underline">Change delivery pin</button>
    </div>;
  }
  return <OffCampusMap {...props} />;
}
