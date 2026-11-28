# Review follow-up and public rating proof — 5 November 2026

The existing is_flagged field now has native staff controls: expand a review, flag it for follow-up or clear the flag. It does not censor the score, delete a review, or modify awarded HP. Filters and review reload reflect the saved value.

PATCH /admin/reviews/:id/flag accepts only desired/expected flag state and the displayed updated_at timestamp. It resolves the row using the user's RLS client, checks campus modification rights, and conditionally updates only is_flagged/updated_at. Matching response-loss retries return the existing row without another write; a stale conditional write returns 409. A newer update therefore cannot be silently overwritten by an old opposite action. The existing best-effort admin audit helper records changed flags and campus, not customer review text. Audit logging retains that helper's existing non-transactional failure behavior; no stronger durability is claimed.

Verification:

- **1,067 backend tests passed**, including eleven new mutation/validation/scope/replay/conflict cases.
- **Native Chromium passed:** set/clear reflection, immediate duplicate-click latch, committed-response-loss replay, stale conflict display and recovery, plus the prior campus/filter/page/search/detail/read-failure suite.
- **Fresh Supabase fixtures in BEGIN/ROLLBACK passed:** own-campus admin may flag, another campus cannot clear, super admin may clear, the owner cannot set a staff flag, and flagging leaves HP and scores intact. No actual customer account, order or review was changed; no provider message was sent.
- The actual public get_menu_item_review_stats function returned a 3-star average and two reviews for 1- and 5-star reviews despite repeated menu lines in the first order. It retained that result after staff flag/clear. This verifies the real SQL aggregate; the compatibility fallback and shared menu output attachment have separate prior handler evidence.
- TypeScript/ESLint and the complete production build passed, including client/SSR compilation and seven-route prerender.

No new table, column, migration or grant was required. Review promotion remains separate storefront testimonial editing; no nonexistent promotion endpoint is claimed. Full public menu browser presentation and exceptional high-volume reporting remain separate from these recorded cases.
