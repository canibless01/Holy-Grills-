/** Hide explicitly labelled audit fixtures; preserve genuine names/results. */
export function publicHallEntries(rows: any[]): any[] {
  return rows.filter(entry => {
    const winner = entry.winner || entry;
    const name = String(winner.full_name || winner.name || '').trim();
    return !/^\[(?:TEST\]|AUDIT)/i.test(name);
  });
}
