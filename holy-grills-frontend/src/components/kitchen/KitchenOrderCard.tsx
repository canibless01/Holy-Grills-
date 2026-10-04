import React, { useState } from 'react';
import { Check, Users, Trophy, MapPin, Ban, RotateCcw } from 'lucide-react';
import { ORDER_STATUS_LABELS } from '@/lib/hgUtils';
import KitchenTimer from '@/components/kitchen/KitchenTimer';

const STATUS_STYLES = {
  received: 'bg-amber-500 text-white',
  preparing: 'bg-blue-500 text-white',
  ready: 'bg-emerald-500 text-white',
  assigned: 'bg-violet-500 text-white',
  out_for_delivery: 'bg-cyan-500 text-white',
};

const STATUS_DOT = {
  received: 'bg-amber-500',
  preparing: 'bg-blue-500',
  ready: 'bg-emerald-500',
};

// A single order ticket in the KDS board. Kitchen staff see the ordering
// student's name + items only — no phone numbers, no financials (spec).
// Each item line has a compact "86" toggle to mark the menu item sold out
// (PATCH /menu/items/:id via kitchen.markItemUnavailable/Available).
// isNew drives the flash ring for freshly arrived orders.
export default function KitchenOrderCard({ order, onStatusUpdate, onMarkUnavailable, onMarkAvailable, actionLoading, targetMinutes, isNew }) {
  const [soldOut, setSoldOut] = useState(new Set());
  const items = order.order_items || [];
  const isLoading = actionLoading === order.id;

  const toggleSoldOut = (e, item) => {
    e.stopPropagation();
    if (!item.menu_item_id) return;
    if (soldOut.has(item.menu_item_id)) {
      onMarkAvailable?.(item.menu_item_id);
      setSoldOut(prev => { const n = new Set(prev); n.delete(item.menu_item_id); return n; });
    } else {
      onMarkUnavailable?.(item.menu_item_id);
      setSoldOut(prev => new Set(prev).add(item.menu_item_id));
    }
  };

  return (
    <div className={`rounded-2xl bg-white border p-3.5 shadow-card transition-all duration-300 ${isNew ? 'border-red-400 ring-2 ring-red-400/50 animate-pulse' : 'border-border'}`}>
      {/* Header row — status + order id + timer */}
      <div className="flex items-center justify-between mb-2.5 gap-2">
        <div className="flex items-center gap-1.5 flex-wrap min-w-0">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${STATUS_STYLES[order.status] || 'bg-muted text-white'}`}>
            {ORDER_STATUS_LABELS[order.status] || order.status}
          </span>
          <span className="text-[10px] text-muted-foreground font-mono truncate">#{(order.id || '').slice(0, 8).toUpperCase()}</span>
        </div>
        <KitchenTimer receivedAt={order.received_at} targetMinutes={targetMinutes} />
      </div>

      {/* Customer + delivery type */}
      <div className="flex items-center gap-2 mb-2 text-xs">
        <span className="flex items-center gap-1 text-foreground font-semibold min-w-0">
          <Users className="w-3 h-3 text-primary shrink-0" />
          <span className="truncate">{order.customer_name || 'Walk-in'}</span>
        </span>
        <span className="flex items-center gap-1 text-muted-foreground ml-auto shrink-0">
          <MapPin className="w-3 h-3" />
          {order.delivery_type === 'off_campus' ? 'Off-campus' : 'On-campus'}
        </span>
      </div>

      {/* Badges — free side, squad */}
      {(order.has_free_side || order.is_squad || order.squad_name) && (
        <div className="flex flex-wrap gap-1 mb-2">
          {order.has_free_side && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-600 flex items-center gap-0.5">
              <Trophy className="w-2.5 h-2.5" /> Reward Side
            </span>
          )}
          {(order.is_squad || order.squad_name) && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-purple-100 text-purple-600 flex items-center gap-0.5">
              <Users className="w-2.5 h-2.5" /> Squad{order.squad_name ? ` · ${order.squad_name}` : ''}
            </span>
          )}
        </div>
      )}

      {/* Items with sold-out toggle */}
      <div className="space-y-1 mb-2">
        {items.map((item, i) => {
          const isOut = soldOut.has(item.menu_item_id);
          return (
            <div key={i} className="flex items-center gap-1.5 text-sm text-foreground">
              <span className="font-bold shrink-0">{item.quantity}×</span>
              <span className={`flex-1 min-w-0 ${isOut ? 'line-through text-muted-foreground' : ''}`}>{item.name_snapshot}</span>
              {item.is_free_side && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-600 shrink-0">🏆</span>
              )}
              {item.menu_item_id && (
                <button
                  onClick={(e) => toggleSoldOut(e, item)}
                  className={`w-5 h-5 rounded-md flex items-center justify-center transition-colors shrink-0 ${
                    isOut ? 'bg-emerald-100 text-emerald-600 hover:bg-emerald-200' : 'bg-red-50 text-red-500 hover:bg-red-100'
                  }`}
                  title={isOut ? 'Restock item' : 'Mark sold out (86)'}
                >
                  {isOut ? <RotateCcw className="w-3 h-3" /> : <Ban className="w-3 h-3" />}
                </button>
              )}
            </div>
          );
        })}
        {order.is_squad && (
          <p className="text-[10px] text-purple-500">Squad order — all items grouped into one ticket.</p>
        )}
      </div>

      {/* Notes */}
      {order.notes && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5 mb-2">
          📝 {order.notes}
        </p>
      )}

      {/* Delivery window */}
      {order.delivery_windows?.label && (
        <div className="text-[11px] text-muted-foreground mb-2.5 flex items-center gap-1">
          <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[order.status] || 'bg-muted'}`} />
          {order.delivery_windows.label}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {order.status === 'received' && (
          <button
            onClick={() => onStatusUpdate(order.id, 'preparing')}
            disabled={isLoading}
            className="flex-1 py-2.5 rounded-xl bg-primary text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
          >
            {isLoading ? 'Updating…' : 'Start Preparing'}
          </button>
        )}
        {order.status === 'preparing' && (
          <button
            onClick={() => onStatusUpdate(order.id, 'ready')}
            disabled={isLoading}
            className="flex-1 py-2.5 rounded-xl bg-emerald-500 text-white text-xs font-bold disabled:opacity-50 active:scale-[0.98] transition-all"
          >
            {isLoading ? 'Updating…' : 'Mark Ready'}
          </button>
        )}
        {order.status === 'ready' && (
          <div className="flex-1 py-2.5 rounded-xl bg-emerald-50 text-emerald-600 text-xs font-bold text-center flex items-center justify-center gap-1 border border-emerald-200">
            <Check className="w-3.5 h-3.5" /> Ready — awaiting rider
          </div>
        )}
      </div>
    </div>
  );
}