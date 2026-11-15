# Settings/System recovery — 15 November 2026

This closes the reproduced editor/diagnostic defects under A4, without running any live manual job or changing production configuration values.

- Existing JSON objects and arrays round-trip as JSON; text remains text, including comma-separated addresses and digit-only strings. Finite numbers and exact booleans retain their types. Invalid JSON/type input is caught inside the save lifecycle and leaves the draft intact. New object/list keys use explicit JSON instead of guessing that every comma means a list.
- Generic settings editors submit their row's `updated_at`; the API compares that version and includes it in the atomic update predicate. A concurrent update or deleted row returns 409 and cannot broadcast a multiplier announcement. Older callers also guard against changes after the handler's read. Global/campus permissions remain unchanged. Drafts survive rejection; explicit reload allows review before saving again. Pending saves disable conflicting edits and modal closure.
- A failed settings refresh remains visible and blocks another write until reload. A confirmed save followed by a failed read is distinguished from a rejected save. Unmounted/stale reads cannot replace newer settings.
- The live API wrapper no longer swallows cron-status read errors or fabricates "never run" from an unavailable endpoint. Missing known jobs are labelled "Not reported". Cron/audit failures have Retry and do not masquerade as empty history. Concurrent manual Run submissions are guarded while the request is pending; only super admins have the action. A 202 response is reported as started, not completed.
- Health reads the actual nested `checks` payload, including Supabase Auth. Audit reads discard stale page responses, and an empty later page retains Previous navigation.

Verification: 1,891 complete backend tests; 47 initial focused settings/validator/config regressions plus the final full suite; native 393/1280 px Settings/System flows with controlled HTTP; real parser type/invalid-input checks now included in frontend build; full lint/typecheck/client/SSR/prerender checks pass. The native test covers malformed JSON, 409 draft/reload, typed payloads, cron failure/retry/pending-run guard, three nested connection statuses, audit failure/retry and empty-page return. No actual customer message, payment, production setting write or manual cron was executed.

A4's remaining setting-to-consumer reconciliation and the historical A7 inventory are tracked independently; this evidence is not a whole-site sign-off.
