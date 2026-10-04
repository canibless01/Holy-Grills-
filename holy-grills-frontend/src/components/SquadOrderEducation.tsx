import React from 'react';
import { Link } from 'react-router-dom';
import { Users, ArrowRight, Tag, Truck, Gift } from 'lucide-react';

/**
 * SquadOrderEducation — promotional section that sells the Squad Order benefit.
 * Visible to guests + authenticated users. Every figure (min/max items,
 * discount %, delivery discount %) is read live from backend config, so an
 * admin change is reflected here with no redeploy.
 */
export default function SquadOrderEducation() {
  const perks = [
    { icon: Tag, label: 'Squad deal' },
    { icon: Truck, label: 'Delivery perk' },
    { icon: Gift, label: 'Shared rewards' },
  ];

  return (
    <section className="relative rounded-2xl overflow-hidden border border-accent/25 shadow-card">
      <div className="absolute inset-0 bg-gradient-dark" />

      <div className="relative p-5 text-white">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-11 h-11 rounded-2xl bg-white/15 backdrop-blur-sm flex items-center justify-center shrink-0 ring-1 ring-white/25">
            <Users className="w-5 h-5 text-white" />
          </div>
          <div className="min-w-0">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/15 text-[9px] font-bold uppercase tracking-wider">Squad Orders</span>
            <h2 className="font-heading font-extrabold text-xl text-white mt-0.5 leading-tight">Feast together. Earn together.</h2>
          </div>
        </div>

        <p className="text-sm text-white/85 leading-relaxed mb-4 max-w-sm">
          Your people. One order.
        </p>

        {/* Perks — one compact row */}
        <div className="flex flex-wrap gap-1.5 mb-4">
          {perks.map((p) => (
            <span key={p.label} className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-white/12 backdrop-blur-sm border border-white/20 text-[11px] font-bold text-white">
              <p.icon className="w-3.5 h-3.5 text-accent" />
              {p.label}
            </span>
          ))}
        </div>

        {/* Steps — one tight progression */}
        <div className="flex items-center gap-1.5 mb-4 text-[10px] text-white/75 font-semibold">
          <span className="inline-flex items-center gap-1">
            <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center font-bold text-[9px]">1</span>
            Start a squad
          </span>
          <span className="text-white/30">›</span>
          <span className="inline-flex items-center gap-1">
            <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center font-bold text-[9px]">2</span>
            Fill the plates
          </span>
          <span className="text-white/30">›</span>
          <span className="inline-flex items-center gap-1">
            <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center font-bold text-[9px]">3</span>
            Share and earn
          </span>
        </div>

        <Link to="/menu" className="w-full flex items-center justify-center gap-2 py-3 rounded-button bg-accent text-accent-foreground text-sm font-bold hover:bg-accent/90 active:scale-[0.98] transition-all shadow-glow">
          Start a squad order <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </section>
  );
}