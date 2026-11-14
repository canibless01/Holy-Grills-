// Reward-system helpers for the student panel — rank medals and expiry countdowns. One source of truth so the Rewards
// Dashboard, Exclusive Spin screen, Leaderboard, and Hall of Fame never
// disagree on prize/medal/expiry wording.

// Leaderboard rank medals — #1 🥇, #2 🥈, #3 🥉, #4–10 ⭐, beyond that blank.
export const RANK_MEDALS = { 1: '🥇', 2: '🥈', 3: '🥉' };
export const rankMedal = (rank) => {
  if (!rank) return '';
  if (rank <= 3) return RANK_MEDALS[rank];
  if (rank <= 10) return '⭐';
  return '';
};

// Whole-day expiry countdown used by credit/spin expiry displays.
export const daysUntil = (dateStr) => {
  if (!dateStr) return null;
  const diff = new Date(dateStr).getTime() - Date.now();
  if (diff <= 0) return 0;
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
};

export const expiryLabel = (dateStr) => {
  const d = daysUntil(dateStr);
  if (d === null) return '';
  if (d <= 0) return 'Expired';
  if (d === 1) return 'Expires tomorrow';
  return `Expires in ${d} days`;
};