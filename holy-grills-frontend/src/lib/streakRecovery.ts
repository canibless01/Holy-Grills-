/**
 * Attendance can commit a weekly pending-HP payout. Read both views only after
 * that mutation finishes; parallel attendance/balance requests can otherwise
 * leave HP showing the pre-payout amount while history already contains it.
 */
export async function recoverStreakAndHp<TStreak, THp>(
  recordActivity: () => Promise<unknown>,
  getStreak: () => Promise<TStreak>,
  getHpBalance: () => Promise<THp>,
): Promise<{
  streak: PromiseSettledResult<TStreak>;
  balance: PromiseSettledResult<THp>;
}> {
  await recordActivity();
  // These reads are independent: an HP outage must not hide a valid streak.
  const [streak, balance] = await Promise.allSettled([getStreak(), getHpBalance()]);
  return { streak, balance };
}
