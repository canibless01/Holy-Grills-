import React from 'react';
import { Leaf, Flame, Clock, Truck } from 'lucide-react';
import FlameMark from '@/components/FlameMark';

// "How your meal is made" — a companion to the Holy Points banner, placed
// below the quick-links grid. Same 4-tile shape, but a dark-brown gradient
// (vs. the orange CTA banner) so the two read as a pair, not a repeat.
const STEPS = [
  { icon: Leaf, title: 'Fresh daily', body: 'Proteins and produce sourced fresh every morning — never frozen.' },
  { icon: Flame, title: 'Holy Flame method', body: 'Signature marinade, grilled live over open flame.' },
  { icon: Clock, title: 'Made to order', body: 'Nothing pre-cooked. Your order starts the grill.' },
  { icon: Truck, title: 'Delivered hot', body: 'Sealed warm and rushed straight to your door.' },
];

export default function HowItsMade() {
  return (
    <div className="rounded-3xl bg-gradient-dark p-6 sm:p-8 text-white relative overflow-hidden shadow-card">
      <FlameMark className="absolute -right-6 -top-6 w-28 h-28 opacity-15" />
      <div className="relative">
        <span className="text-[10px] font-extrabold uppercase tracking-wider text-accent">Behind the grill</span>
        <h2 className="font-heading font-extrabold text-xl mt-1 mb-2">How your meal is made</h2>
        <p className="text-sm text-white/80 max-w-md mb-5">Four steps from raw to your door — no shortcuts, no reheats.</p>
        <div className="grid grid-cols-2 gap-3">
          {STEPS.map((s) => {
            const Icon = s.icon;
            return (
              <div key={s.title} className="rounded-xl bg-white/10 border border-white/15 p-4 backdrop-blur-sm">
                <Icon className="w-5 h-5 text-accent mb-1.5" />
                <div className="font-bold text-sm mb-0.5">{s.title}</div>
                <div className="text-xs text-white/70 leading-relaxed">{s.body}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}