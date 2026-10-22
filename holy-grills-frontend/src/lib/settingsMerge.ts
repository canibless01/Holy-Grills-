// src/lib/settingsMerge.ts
//
// How a privileged system_settings row is allowed to extend the values a
// normal user receives. Deliberately import-free so it can be exercised by
// scripts/test-settings-merge.mjs with no bundler, the same way valueText.ts
// is (and for the same reason: this is the seam where a wrong value silently
// reaches every screen).

/**
 * Fold the admin settings list into an existing key→value map.
 *
 * The admin list must EXTEND what users receive, never overwrite it.
 *
 * GET /admin/settings returns every system_settings row — all campuses,
 * is_public = false included, ordered by key. A naive
 * `target[s.key] = s.value` merge therefore had three ways to show a
 * signed-in admin a value no user can ever get, which is exactly the
 * "the number in the table isn't the number that opens" report:
 *
 *   1. a private row overwrote the public one — the public endpoint filters
 *      on is_public = TRUE, the admin list does not;
 *   2. with a global row AND per-campus rows for one key, the winner was
 *      whichever row the database happened to return last, not the
 *      campus-scoped one the backend would pick;
 *   3. a null value wiped a good public value — the public read skips nulls.
 *
 * Campus scope follows the backend exactly: rows for another campus are
 * dropped, and with no campus selected only global rows apply (a guest sees
 * the global storefront until they choose a campus).
 *
 * So: drop other campuses' rows, let a campus row beat the global row for the
 * same key, skip nulls, and never replace a key already resolved.
 *
 * Mutates and returns `target`.
 */
export function mergeAdminSettings(
  target: Record<string, any>,
  adminSettings: any,
  campusId: string | null,
): Record<string, any> {
  const rows = Array.isArray(adminSettings) ? adminSettings : [];
  const byKey = new Map<string, any>();

  rows.forEach((row) => {
    if (!row || !row.key) return;
    if (row.value === null || row.value === undefined) return;          // never blank out a value
    const rowCampus = row.campus_id ?? null;
    // With no campus selected the backend serves global rows only — "a guest
    // sees the global storefront until they pick a campus" — so any
    // campus-scoped row must be dropped here too, not merely deprioritised.
    if (!campusId) {
      if (rowCampus) return;
    } else if (rowCampus && rowCampus !== campusId) {
      return;                                                           // another campus's row
    }
    const prev = byKey.get(row.key);
    if (!prev || (prev.campus_id == null && rowCampus != null)) byKey.set(row.key, row);
  });

  byKey.forEach((row, key) => {
    if (!(key in target)) target[key] = row.value;                      // what users already resolved wins
  });

  return target;
}
