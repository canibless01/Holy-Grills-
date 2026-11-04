// Business-day rules use WAT, regardless of the visitor's device timezone.
export function closureDay(now = Date.now()) {
  const wat = new Date(now + 60 * 60 * 1000);
  const tomorrow = new Date(wat.getTime() + 86400000);
  return { date: wat.toISOString().slice(0, 10), sunday: wat.getUTCDay() === 0,
    monday: tomorrow.toISOString().slice(0, 10) };
}
export const sundayDismissKey = (campusId: string, day: string) => `hg_sunday_closed:${campusId}:${day}`;
export function sundayOffer(nextDate?: string, now = Date.now()) {
  const day = closureDay(now);
  return { ...day, mondayNext: day.sunday && nextDate === day.monday };
}
