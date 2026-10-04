import React, { useState } from 'react';
import { Navigation, Phone, MapPin, Check, Clock, AlertCircle, Flag } from 'lucide-react';
import { formatNaira, ORDER_STATUS_LABELS } from '@/lib/hgUtils';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const STATUS_STYLES = {
  assigned: 'bg-violet-500 text-white',
  out_for_delivery: 'bg-cyan-500 text-white',
  delivered: 'bg-green-700 text-white',
  delivery_attempted: 'bg-red-500 text-white',
  unclaimed: 'bg-gray-400 text-white',
};

// A single delivery in the rider's batch. Orders arrive pre-sorted
// closest-first by the backend (haversine from zone gate). The rider walks
// each order through assigned → out_for_delivery → delivered (or attempted).
// Phone numbers are NEVER shown raw — the Call button fetches a secure
// tel: link from /riders/call/<order_id>.
export default function RiderOrderCard({ order, onAction, onCall, onNavigate, actionLoading, calling }) {
  const [showDeliverConfirm, setShowDeliverConfirm] = useState(false);
  const isLoading = actionLoading === order.id;
  const isCalling = calling === order.id;
  const status = order.status;
  const isSquad = order.is_squad || order.squad_name;
  const totalAmount = order.total_amount ?? order.total ?? 0;
  const gateName = order.gate_name || order.gate || order.delivery_gate?.name || order.delivery_gate || '';

  const confirmDeliver = () => {
    setShowDeliverConfirm(false);
    onAction(order.id, 'deliver');
  };

  return (
    <>
      <div className="rounded-2xl bg-white border border-border shadow-card overflow-hidden">
        {/* Rank + customer header */}
        <div className="flex items-center gap-3 p-3.5 pb-2.5">
          <div className="w-9 h-9 rounded-full bg-gradient-cta flex items-center justify-center text-white text-sm font-extrabold shrink-0">
            {order.delivery_rank || '#'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="font-heading font-bold text-sm text-foreground truncate">{order.customer_name}</div>
              {isSquad && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-purple-100 text-purple-600 shrink-0">Squad</span>
              )}
            </div>
            <div className="text-[11px] text-muted-foreground font-mono">#{(order.id || '').slice(0, 8).toUpperCase()}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="flex items-center gap-1 text-xs font-bold text-primary justify-end">
              <Navigation className="w-3 h-3" />
              {order.distance_km ? `${order.distance_km}km` : '—'}
            </div>
            {totalAmount > 0 && (
              <div className="text-[11px] font-bold text-foreground tabular-nums mt-0.5">{formatNaira(totalAmount)}</div>
            )}
          </div>
        </div>

        {/* Delivery address + gate */}
        <div className="px-3.5 pb-2 space-y-1">
          <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <MapPin className="w-3 h-3 text-muted-foreground mt-0.5 shrink-0" />
            <span className="leading-relaxed">{order.delivery_address || 'Address not specified'}</span>
          </div>
          {gateName && (
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Flag className="w-3 h-3 shrink-0" />
              <span>Gate: {gateName}</span>
            </div>
          )}
        </div>

        {/* Items */}
        <div className="px-3.5 py-2 bg-muted/40 border-y border-border">
          <div className="space-y-0.5">
            {(order.items || []).map((item, i) => (
              <div key={i} className="text-xs text-foreground flex items-center gap-1.5 flex-wrap">
                <span className="font-bold text-foreground">{item.quantity}×</span>
                <span>{item.name_snapshot}</span>
                {(item.is_hof_reward || item.is_hall_of_fame_reward || item.reward_type === 'hall_of_fame') && (
                  <span className="inline-flex items-center text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-accent/30 text-accent-foreground">
                    🏅 Hall of Fame
                  </span>
                )}
              </div>
            ))}
          </div>
          {order.delivery_hint && (
            <div className="text-[11px] text-muted-foreground italic mt-1.5">{order.delivery_hint}</div>
          )}
        </div>

        {/* Status badge row */}
        {status && (
          <div className="px-3.5 pt-2.5">
            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-md inline-block ${STATUS_STYLES[status] || 'bg-secondary text-white'}`}>
              {ORDER_STATUS_LABELS[status] || (status === 'out_for_delivery' ? 'En route' : status.replace(/_/g, ' '))}
            </span>
          </div>
        )}

        {/* Action buttons — state-aware per the rider status flow */}
        <div className="p-3 flex items-center gap-2">
          <button
            onClick={() => onCall(order.id)}
            disabled={isCalling}
            className="flex items-center gap-1 px-3 py-2 rounded-xl bg-accent/20 text-accent-foreground text-xs font-bold disabled:opacity-50 hover:bg-accent/40 transition-colors"
          >
            <Phone className="w-3.5 h-3.5" /> {isCalling ? '…' : 'Call'}
          </button>
          <button
            onClick={() => onNavigate(order.delivery_address)}
            className="flex items-center gap-1 px-3 py-2 rounded-xl bg-cyan-50 text-cyan-600 text-xs font-bold hover:bg-cyan-100 transition-colors"
          >
            <MapPin className="w-3.5 h-3.5" /> Navigate
          </button>
          <div className="flex-1" />

          {(status === 'assigned' || status === 'ready') && (
            <button
              onClick={() => onAction(order.id, 'pickup')}
              disabled={isLoading}
              className="flex-1 py-2 rounded-xl bg-primary text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
            >
              {isLoading ? '…' : 'Confirm Pickup'}
            </button>
          )}
          {status === 'out_for_delivery' && (
            <>
              <button
                onClick={() => onAction(order.id, 'attempt')}
                disabled={isLoading}
                className="px-3 py-2 rounded-xl bg-red-50 border border-red-200 text-red-600 text-xs font-bold disabled:opacity-50 hover:bg-red-100 transition-colors"
              >
                {isLoading ? '…' : 'Miss'}
              </button>
              <button
                onClick={() => setShowDeliverConfirm(true)}
                disabled={isLoading}
                className="flex-1 py-2 rounded-xl bg-emerald-600 text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
              >
                {isLoading ? '…' : 'Delivered'}
              </button>
            </>
          )}
          {status === 'delivered' && (
            <div className="flex-1 py-2 rounded-xl bg-emerald-50 text-emerald-600 text-xs font-bold text-center flex items-center justify-center gap-1 border border-emerald-200">
              <Check className="w-3.5 h-3.5" /> Delivered
            </div>
          )}
          {status === 'delivery_attempted' && (
            <div className="flex-1 py-2 rounded-xl bg-amber-50 text-amber-600 text-xs font-bold text-center flex items-center justify-center gap-1 border border-amber-200">
              <AlertCircle className="w-3.5 h-3.5" /> Attempted — retry pending
            </div>
          )}
          {status === 'unclaimed' && (
            <div className="flex-1 py-2 rounded-xl bg-secondary text-muted-foreground text-xs font-bold text-center flex items-center justify-center gap-1">
              <Clock className="w-3.5 h-3.5" /> Unclaimed
            </div>
          )}
          {!['assigned', 'ready', 'out_for_delivery', 'delivered', 'delivery_attempted', 'unclaimed'].includes(status) && (
            <div className="flex-1 py-2 rounded-xl bg-muted text-muted-foreground text-xs font-bold text-center">
              {status ? status.replace(/_/g, ' ') : 'Awaiting'}
            </div>
          )}
        </div>
      </div>

      {/* Delivery confirmation dialog */}
      <AlertDialog open={showDeliverConfirm} onOpenChange={setShowDeliverConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Complete this delivery?</AlertDialogTitle>
            <AlertDialogDescription>
              'Confirm the customer received the order. HP will be awarded automatically.'
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDeliver}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Yes, complete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}