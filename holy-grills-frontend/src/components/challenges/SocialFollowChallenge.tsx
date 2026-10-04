import { useState } from 'react';
import { ExternalLink, Flame, Loader2 } from 'lucide-react';
import { liveApi } from '@/lib/liveApi';
import { toast } from '@/components/ui/use-toast';
import { msg } from '@/lib/messages';

// POST /challenges/social-follow — the dedicated social-follow milestone
// endpoint. Unlike the generic /challenges/<id>/complete route, this one looks
// up the social_follow milestone internally and surfaces the brand's
// social_link so the student knows WHERE to follow before claiming.
//
// This is a functional UI, not a repetition of the generic claim button: it
// renders the follow link (opens in a new tab) and a separate "I've followed"
// claim action that hits the dedicated endpoint, then calls `onClaimed` so the
// parent refreshes its challenge + HP state.
export default function SocialFollowChallenge({ challenge, onClaimed }) {
  const [claiming, setClaiming] = useState(false);
  const link = challenge?.social_link;

  const handleClaim = async () => {
    setClaiming(true);
    try {
      const res = await liveApi.challenges.socialFollow({ social_link: link || undefined });
      const hp = res?.hp_awarded ?? challenge?.hp_awarded ?? 0;
      toast({ title: msg('FE_SOCIAL_FOLLOW_CHALLENGE_FOLLOW_CLAIMED', '🎉 Follow claimed!'), description: `+${hp} HP added.` });
      onClaimed?.(challenge);
    } catch (e) {
      toast({ title: msg('FE_SOCIAL_FOLLOW_CHALLENGE_COULD_NOT_CLAIM', 'Could not claim'), description: e.message, variant: 'destructive' });
    } finally {
      setClaiming(false);
    }
  };

  return (
    <div className="mt-3 space-y-2">
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 w-full py-2 rounded-full bg-secondary text-foreground text-xs font-bold border border-border active:scale-95 transition"
        >
          <ExternalLink className="w-3.5 h-3.5" /> Follow us
        </a>
      )}
      <div className="flex justify-end">
        <button
          onClick={handleClaim}
          disabled={claiming}
          className="px-4 py-1.5 rounded-full bg-primary text-white text-xs font-bold flex items-center gap-1.5 active:scale-95 disabled:opacity-50"
        >
          {claiming ? (
            <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Claiming…</>
          ) : (
            <><Flame className="w-3.5 h-3.5" /> I've followed — Claim HP</>
          )}
        </button>
      </div>
    </div>
  );
}