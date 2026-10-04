import { motion } from 'framer-motion';
import { Copy, Check, Share2, Sparkles } from 'lucide-react';
import { referralHp } from '@/lib/appConfig';

// Hero card holding the user's referral code + the copy/share actions.
// Reads only real values: `code` and `link` come from the backend stats
// endpoint (or the auth profile) — nothing is invented here.
export default function ReferralCodeCard({ code, link, copied, onCopy, onShare, loading }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 220, damping: 24 }}
      className="relative overflow-hidden rounded-3xl bg-gradient-dark text-white p-5 shadow-glow"
    >
      {/* ambient glow */}
      <div className="absolute -top-16 -right-10 w-44 h-44 rounded-full bg-accent/25 blur-3xl pointer-events-none" />
      <div className="absolute -bottom-16 -left-10 w-44 h-44 rounded-full bg-primary/30 blur-3xl pointer-events-none" />

      <div className="relative">
        <div className="flex items-center gap-2 text-accent">
          <Sparkles className="w-4 h-4" />
          <span className="text-[11px] font-extrabold uppercase tracking-wider">Refer &amp; Earn</span>
        </div>
        <h2 className="font-heading font-extrabold text-xl mt-1.5 leading-tight">
          Invite friends, earn {referralHp()} HP
        </h2>
        <p className="text-[12px] text-white/70 mt-1 leading-relaxed">
          You pocket <span className="text-accent font-bold">{referralHp()} Holy Points</span> the moment a friend
          you referred completes their first delivered order.
        </p>

        {/* Code */}
        <div className="mt-4 rounded-2xl bg-white/10 border border-white/15 p-3.5 backdrop-blur-sm">
          <div className="text-[10px] uppercase tracking-wider font-bold text-white/60">Your code</div>
          {loading ? (
            <div className="h-7 w-32 mt-1.5 rounded-lg bg-white/15 animate-pulse" />
          ) : (
            <div className="font-heading font-extrabold text-2xl tracking-[0.18em] mt-0.5 break-all">
              {code || '—'}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2.5 mt-3">
          <button
            onClick={onCopy}
            disabled={!link || loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-3 rounded-full bg-white text-brand-brown font-bold text-sm active:scale-[0.98] transition-transform disabled:opacity-50"
          >
            {copied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
            {copied ? 'Copied!' : 'Copy link'}
          </button>
          <button
            onClick={onShare}
            disabled={!code || loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-3 rounded-full bg-white/10 border border-white/25 text-white font-bold text-sm active:scale-[0.98] transition-transform disabled:opacity-50"
          >
            <Share2 className="w-4 h-4" /> Share
          </button>
        </div>

        {!code && !loading && (
          <p className="text-[10px] text-white/60 mt-2.5 text-center">
            Your referral code will appear here once your profile is ready.
          </p>
        )}
      </div>
    </motion.div>
  );
}