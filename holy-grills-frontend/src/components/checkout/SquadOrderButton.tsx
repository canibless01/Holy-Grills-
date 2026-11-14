import { useState } from 'react';
import { Users, ChevronDown } from 'lucide-react';
import { squadOrderMinItems, squadOrderMaxItems, squadOrdersEnabled } from '@/lib/appConfig';
import SquadOrderSection from '@/components/checkout/SquadOrderSection';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

/**
 * SquadOrderButton — the always-visible squad entry point on checkout.
 *
 * Shows the shopper how close their cart is to a valid squad order. When the
 * item count is in range, tapping it expands the full SquadOrderSection so
 * they can tag a squad; when it's out of range, the tap surfaces a toast that
 * tells them exactly how many items to add (or remove) to qualify.
 */
export default function SquadOrderButton({ itemCount, value, onChange }) {
  const [expanded, setExpanded] = useState(!!value?.squad_id);
  if (!squadOrdersEnabled()) return null;

  const min = squadOrderMinItems();
  const max = squadOrderMaxItems();
  const eligible = itemCount >= min && itemCount <= max;
  const toGo = Math.max(0, min - itemCount);
  const over = Math.max(0, itemCount - max);

  const handleClick = () => {
    if (!eligible) {
      if (toGo > 0) {
        toast({
          title: msg('FE_SQUAD_ORDER_BUTTON_YOUR_ORDER_IS_NOT_VALID_FOR_SQUAD_ORDER', 'Your order is not valid for Squad Order'),
          description: toGo === 1
            ? msg('FE_SQUAD_ORDER_BUTTON_ADD_ONE_MORE_ITEM', 'Add 1 more item to reach the {min}-item squad minimum.', { min })
            : msg('FE_SQUAD_ORDER_BUTTON_ADD_MORE_ITEMS', 'Add {count} more items to reach the {min}-item squad minimum.', { count: toGo, min }),
        });
      } else {
        toast({
          title: msg('FE_SQUAD_ORDER_BUTTON_SQUAD_ORDERS_ARE_CAPPED_AT_MAX_ITEMS', 'Squad orders are capped at {max} items', { max: max }),
          description: over === 1
            ? msg('FE_SQUAD_ORDER_BUTTON_REMOVE_ONE_ITEM', 'Remove 1 item to keep your squad order within the {max}-item limit.', { max })
            : msg('FE_SQUAD_ORDER_BUTTON_REMOVE_ITEMS', 'Remove {count} items to keep your squad order within the {max}-item limit.', { count: over, max }),
        });
      }
      return;
    }
    setExpanded((e) => !e);
  };

  return (
    <div className="space-y-3">
      <button
        onClick={handleClick}
        className={`w-full flex items-center gap-3 p-3.5 rounded-2xl border hg-press transition-all ${eligible ? 'border-transparent bg-brand-brown shadow-card' : 'border-border bg-card'}`}
      >
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${eligible ? 'bg-white/20' : 'bg-primary/10'}`}>
          <Users className={`w-5 h-5 ${eligible ? 'text-white' : 'text-primary'}`} />
        </div>
        <div className="flex-1 text-left min-w-0">
          <div className={`text-sm font-bold ${eligible ? 'text-white' : 'text-foreground'}`}>Squad Order</div>
          {eligible ? (
            <div className="text-xs text-white/80 font-semibold">Ready — tag your squad & split HP</div>
          ) : toGo > 0 ? (
            <div className="text-xs text-muted-foreground">Add <span className="font-bold text-primary">{toGo}</span> more item{toGo !== 1 ? 's' : ''} to unlock</div>
          ) : (
            <div className="text-xs text-muted-foreground">Remove <span className="font-bold text-primary">{over}</span> — squad capped at {max}</div>
          )}
        </div>
        {eligible && <ChevronDown className={`w-4 h-4 text-white/70 transition-transform shrink-0 ${expanded ? 'rotate-180' : ''}`} />}
      </button>
      {eligible && expanded && (
        <SquadOrderSection value={value} onChange={onChange} />
      )}
    </div>
  );
}