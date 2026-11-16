# Order-lock filters and abandoned-cart controls — 15 November 2026

Order-lock status/date controls remain visible during reads. Request generations prevent an older status/date result from replacing the latest selection, including cleanup on workspace exit. Failed reads still expose Retry and do not imply an empty list.

The abandoned-cart page had three nonfunctional status choices: its API always excluded recovered rows, and exhausted/cleared were not modeled recovery states. The API now accepts explicit all/pending/recovered filters, preserving pending as the default for existing callers. The screen requests the selected state; recovered history is visible and cannot be nudged. Unsupported choices were removed. Scope resolution and the existing reporting view/reminder metrics remain authoritative. Search and Refresh have accessible labels. A synchronous reminder lock disables competing actions until the request finishes; the backend still enforces due/preference/payment/preparation checks.

Evidence:

- `scripts/test-admin-lock-cart-browser.py`: four actual-app cases pass, both pages at 393px/1280px. Lock failure/Retry, simultaneous date/status changes and reversed response order, all status options, date clearing and HP/contact/order fields. Cart failure/refresh, all/pending/recovered changes, name/email no-match/search, phone/WhatsApp URLs, pending lock, rejected reminder retaining the row, successful retry and exact request counts. Controlled HTTP only; no real reminder or customer write.
- 37 targeted backend cases pass, including 15 new handler cases for all three recovery filters/default, regular-admin campus pinning, selected/global super-admin scope, invalid filters and unchanged per-row reminder metrics. No SQL migration or grant change.
- Full merged backend suite: **1,895 passed**.
- TypeScript, edited-component lint and full production build pass. The lib API file is ignored by existing lint configuration and remains checked by TypeScript/build/native integration.

The existing endpoint's bounded page arguments remain; this does not certify browsing/search beyond its returned page. Full historical cart pagination is an explicit remaining control, not hidden behind a false all-records claim. The pre-existing durable reminder/provider evidence remains applicable; native queuing is not inbox/device delivery.
