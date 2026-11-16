# Community-manager recipient lookup — 16 November 2026

Owner report: flyers are visible but the community manager cannot share to recipients.

Confirmed production schema mismatch: `promo_assignments` applied `.eq('campus_id', scope)` to `ambassador_promo_assignments`, which has no campus column. Its ambassador foreign key points to `ambassadors(profile_id)`, where campus ownership already exists. This affects scoped community managers/admins and scoped super admins; an unscoped super-admin read can avoid that broken predicate.

Replaced the nonexistent-column predicate with an inner PostgREST join through the existing ambassador FK and an embedded campus filter. It filters before fetching recipients, removes the internal join payload from output and retains the route's independent attached-profile campus check. No new column, policy, role authority or migration.

Verification:

- Read-only live Supabase catalog confirms the real columns and FK. No missing recipient profile/referral/phone among the current 36 assignments.
- Actual read-only service-client PostgREST request with the new join/filter succeeds and returns **36 assignments**, all in the active manager's campus. Zero mutations and no personal contact values printed.
- **89 ambassador backend tests pass**. Corrected the prior scope test, which had incorrectly invented a `campus_id` field on assignment fixtures and therefore missed the schema defect; it now asserts the existing FK join and embedded filter.

This closes the reproduced recipient-read blocker. Browser/WhatsApp/device sharing and narrow manager upload-folder controls are separate follow-up checks in the same request. No real message or assignment status was sent/changed during verification.
