/** Show one unclaimed step per related challenge ladder, keeping independent
 * activities and weekly/monthly periods visible together. Claiming remains a
 * server-verified action; this helper only controls presentation. */
export function nextChallengeSteps<T extends Record<string, any>>(available: T[], completed: T[]): T[] {
  const claimed = new Set(completed.map(row => row.id));
  const aliases: Record<string,string> = { first_referral:'referral_count', first_order:'order_count', first_review:'review_count', first_event:'event_checkins', first_squad:'squad_orders' };
  const next = new Map<string, T>();
  for (const row of available) {
    if (claimed.has(row.id)) continue;
    const trigger = aliases[row.trigger_type] || row.trigger_type;
    const key = trigger ? JSON.stringify([trigger,row.time_window || 'lifetime',row.campus_id || 'global',row.metadata?.series_id || '',trigger === 'social_follow' ? row.social_link || row.id : '']) : `single:${row.id}`;
    const target = Number(row.trigger_value ?? row.target ?? row.target_count ?? 1);
    const current = next.get(key);
    const previous = Number(current?.trigger_value ?? current?.target ?? current?.target_count ?? 1);
    if (!current || target < previous || (target === previous && String(row.id) < String(current.id))) next.set(key,row);
  }
  return [...next.values()];
}
