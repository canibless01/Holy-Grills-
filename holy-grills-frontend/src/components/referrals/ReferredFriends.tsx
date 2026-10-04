import React from 'react';
import { motion } from 'framer-motion';
import { UserCheck, Clock, User } from 'lucide-react';
import { timeAgo } from '@/lib/hgUtils';
import MascotStandee from '@/components/mascot/MascotStandee';

// One referred friend row. `friend` is a raw backend referral record — we read
// whichever display fields it carries and never invent a name. If the backend
// returns only an id, we label it honestly as a referred friend.
function FriendRow({ friend, index }) {
  const status = (friend.status || 'pending').toLowerCase();
  const completed = status === 'completed' || status === 'active';
  const name =
    friend.referred_name || friend.name || friend.friend_name ||
    (friend.referred_user && (friend.referred_user.full_name || friend.referred_user.name)) ||
    '';
  const hp = friend.hp_awarded ?? friend.hp ?? 0;
  const when = friend.completed_at || friend.created_at;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className="flex items-center gap-3 p-3 rounded-2xl bg-card border border-border"
    >
      <div
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
          completed ? 'bg-success/15 text-success' : 'bg-secondary text-muted-foreground'
        }`}
      >
        {completed ? <UserCheck className="w-5 h-5" /> : <User className="w-5 h-5" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-bold text-sm text-foreground truncate">
          {name || 'Referred friend'}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {when ? timeAgo(when) : '—'}
        </div>
      </div>
      <span
        className={`flex items-center gap-1 text-[10px] font-extrabold px-2.5 py-1 rounded-full ${
          completed
            ? 'text-success bg-success/10'
            : 'text-amber-700 bg-amber-100'
        }`}
      >
        {completed ? <UserCheck className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
        {completed ? 'Completed' : 'Pending'}
      </span>
      {hp > 0 && (
        <span className="text-xs font-extrabold text-primary">+{hp}</span>
      )}
    </motion.div>
  );
}

export default function ReferredFriends({ friends = [], loading }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading font-extrabold text-base text-foreground">Your referrals</h2>
        {!loading && friends.length > 0 && (
          <span className="text-[11px] text-muted-foreground">{friends.length} total</span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-2xl bg-card border border-border">
              <div className="w-10 h-10 rounded-full bg-secondary animate-pulse" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3.5 w-28 rounded bg-secondary animate-pulse" />
                <div className="h-2.5 w-16 rounded bg-secondary animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      ) : friends.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-6 text-center">
          <MascotStandee mascot="waving" className="w-28 h-28 mx-auto mb-1" alt="No referrals yet" />
          <p className="text-sm font-bold text-foreground">No referrals yet</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Share your code above — friends who order earn you 75 HP each.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {friends.map((f, i) => (
            <FriendRow key={f.id || i} friend={f} index={i} />
          ))}
        </div>
      )}
    </section>
  );
}