// Reward-system helpers for the student panel — exclusive-spin prize table,
// rank medals, and expiry countdowns. One source of truth so the Rewards
// Dashboard, Exclusive Spin screen, Leaderboard, and Hall of Fame never
// disagree on prize/medal/expiry wording.

// Exclusive Spin prize table — matches the spec's prize types & effects.
// `type` drives how a prize is applied: 'next_order' (free item token added to
// the next order), 'hp' (HP added to balance), 'status' (e.g. Double HP badge).
export const EXCLUSIVE_SPIN_PRIZES = [
  { id: 'free_sausage_x2', label: 'Free Sausage ×2', type: 'next_order', icon: '🌭', color: '#F72B13', token: 'Free Sausage ×2' },
  { id: 'hp_bolt', label: 'HP Bolt +300', type: 'hp', hp: 300, icon: '⚡', color: '#FFC251' },
  { id: 'free_side', label: 'Free Side', type: 'next_order', icon: '🍟', color: '#FF6B1A', token: 'Free Side' },
  { id: 'hp_boost', label: 'HP Boost +150', type: 'hp', hp: 150, icon: '🔥', color: '#FFDD9F' },
  { id: 'free_gizzard_x3', label: 'Free Gizzard ×3', type: 'next_order', icon: '🍗', color: '#D4200C', token: 'Free Gizzard ×3' },
  { id: 'double_hp', label: 'Double HP next order', type: 'status', icon: '✨', color: '#ECA829', token: 'Double HP' },
  { id: 'free_coleslaw', label: 'Free Coleslaw', type: 'next_order', icon: '🥗', color: '#FF7070', token: 'Free Coleslaw' },
  { id: 'hp_jackpot', label: 'HP Jackpot +750', type: 'hp', hp: 750, icon: '💎', color: '#C4A57D' },
];

// Map an arbitrary exclusive-spin API result back onto a prize definition so
// the wheel can land on the right segment regardless of how the backend names
// the field (prize_id / id / prize_label / hp_won …).
export const getExclusivePrize = (result) => {
  if (!result) return null;
  // The live backend returns `prize` as a bare name string ("HP Jackpot +750",
  // "Free Sausage ×2", "Double HP next order"). Handle that before treating
  // result as an object.
  if (typeof result === 'string') {
    const match = EXCLUSIVE_SPIN_PRIZES.find((p) => p.label === result || p.token === result);
    return match || { id: 'hp_boost', label: result || 'HP Boost +150', type: 'hp', hp: 150, icon: '🔥', color: '#FFDD9F' };
  }
  const id = result.prize_id || result.id;
  const label = result.prize_label || result.prize || result.label;
  let match = id ? EXCLUSIVE_SPIN_PRIZES.find((p) => p.id === id) : null;
  if (!match && label) match = EXCLUSIVE_SPIN_PRIZES.find((p) => p.label === label || p.token === label);
  if (!match && result.hp_won) match = EXCLUSIVE_SPIN_PRIZES.find((p) => p.hp === result.hp_won && p.type === 'hp');
  return match || { id: 'hp_boost', label: label || 'HP Boost +150', type: 'hp', hp: result.hp_won || 150, icon: '🔥', color: '#FFDD9F' };
};

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