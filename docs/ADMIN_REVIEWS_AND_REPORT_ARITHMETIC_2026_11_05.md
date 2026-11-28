# Reviews and report arithmetic — 5 November 2026

## Fixed

- Tier economics now scopes its orders, HP activity and redemption-cost queries to the selected campus, in addition to scoping current tier members. A student with activity at another campus previously caused that activity to appear in a campus-specific tier report. All Campuses still includes both.
- The native Reviews panel now sends the effective campus. Super admins can select a campus or All Campuses; ordinary admins use their profile campus. Switching campuses resets page/filter/search/expanded state and discards late replies from the previous workspace.
- Reviews order by created_at and id descending, giving equal-timestamp rows a stable pagination order. The displayed average explicitly describes the current page, rather than implying it is an all-review aggregate. Rating/flag/search/refresh controls have accessible names, with new copy in the central registry.
- The menu-rating fallback deduplicates reviews by review ID before averaging. Repeated lines of the same item in one order previously weighted that order's review multiple times while reporting a distinct review count. Two reviews of 1 and 5 stars now average 3 even when the first order repeats the item.

## Verification

**1,056 backend tests passed**, including seven new actual-service/handler cases:

1. Programme overview revenue, HP issuance/redemption versus transfers, active/pending liability and redemption-cost ratios against controlled rows.
2. Redemption totals, cost categories and cost per HP against controlled rows.
3. Campus-specific versus global tier arithmetic with the same student's other-campus activity present.
4. More than 200 tier members, exercising multiple user-ID chunks.
5. Campus-admin, selected-campus super-admin and global review handler scope; rating/flag filters, total counts and stable page ordering.
6. Repeated menu lines and distinct-review averages, plus shared rating attachment and unrated defaults.

**Native Chromium passed**: global/selected-campus Reviews; ordinary admin profile scope despite stale selected campus; page summary; expansion and written review; pagination; rating and flag filters; page-local search; campus state reset; late reply isolation; read failure shown as failure rather than an empty list; Retry recovery. Controlled HTTP only; no real reviews, customer accounts or orders were changed. The initial cold browser run timed out before content appeared; the diagnostic rerun had no page errors and passed, and a subsequent run with a longer assertion deadline also passed. This is functional evidence, not a returning-user performance sign-off.

TypeScript, ESLint and the complete production build passed, including client/SSR compilation, prerequisite checks and seven-route prerender. No migration or new database object was needed; role grants and existing review-submission/payment behavior were unchanged.

## Remaining

The current Reviews panel is a read/filter/detail page. There is no review promotion endpoint or native manual flag/unflag workflow; this batch does not claim those write workflows exist or are complete. Homepage testimonials remain separate storefront content. The public SQL rating aggregator was not changed; the duplicate weighting fix applies to the compatibility fallback and shared output attachment.

Wider reporting still includes refund/net-revenue semantics, historic versus current-tier attribution, every chart/export, and exports during concurrent database changes. Complete moderation policy/flag handling and live public rating aggregation/reflection remain in the general-site audit. Broader user/staff/profile/campus role/action pages follow. Launch acceptance remains with the other chat.
