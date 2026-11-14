/** Calendar dates for the storefront's Africa/Lagos business day. */
export function watDateKey(now = new Date()): string {
  return new Date(now.getTime() + 60 * 60 * 1000).toISOString().slice(0, 10);
}
export function watCalendarDay(offset = 0, now = new Date()): string {
  const day = new Date(watDateKey(now) + 'T00:00:00Z');
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}
export function watDaysUntil(dateKey: string, now = new Date()): number {
  return Math.round((Date.parse(dateKey + 'T00:00:00Z') - Date.parse(watDateKey(now) + 'T00:00:00Z')) / 86400000);
}
