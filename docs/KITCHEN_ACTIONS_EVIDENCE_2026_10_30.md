# Kitchen actions — current run, 30 October 2026

This run closes the listed prep-window and stock-control defects. It does not certify every kitchen/delivery variant or the whole admin audit.

## Fixed behavior

- Selecting another preparation window immediately clears the previous summary/actions. Request generations reject late responses for older selections. Failed summary reads show an explicit Retry and no advance controls.
- Batch advance requires the currently loaded window, prevents same-tick repeat submission and locks window navigation while saving. The queue and prep summary refresh afterwards; a failed/ambiguous action also refreshes before another attempt. Background queue responses cannot overwrite a newer refresh.
- Kitchen sold-out/restock controls now use the existing staff-authorized `PATCH /menu/items/:id/availability` endpoint, with explicit selected-campus scope for super-admins. Previously they called the admin-only catalog editor.
- Stock state changes only after a successful save. Repeated actions on the same item are blocked across all tickets. A successful change updates all those tickets; queue reads rehydrate it after reload. An older poll cannot overwrite a newly saved stock state.
- Stock switches affect new orders, not the preparation obligation for existing paid tickets. Paid ticket items are no longer struck through after a sell-out; the page explains the distinction.
- Availability writes reject non-object JSON, invalid boolean values and invalid campus IDs explicitly. New/changed response copy is centralized in `app/messages.py`.

## Verification

- `scripts/test-kitchen-actions-browser.py`: real native React/Chromium with controlled HTTP, covering failed stock save, duplicate/shared pending state, saved reload state, delayed old queue response, late wrong-window summary, failed summary Retry, one campus-scoped batch advance, disabled navigation while writing and summary refresh after success.
- Existing campus/settings and handoff/map browser regressions remain passing.
- `tests/test_kitchen_stock_snapshot.py`: seven backend tests for bounded scoped read, all-ticket rehydration, empty/no-campus handling, kitchen own-campus write despite a supplied foreign campus, super-admin explicit target, foreign parent refusal and malformed inputs.
- Real Supabase `tests/sql/kitchen_stock_availability.sql`: kitchen save/read/restock succeeds in its own campus; foreign stock and student writes are refused; the parent catalog price/availability and foreign stock remain unchanged. Every fixture and temporary role edit rolled back.
- Complete backend suite: **778 passed**. Frontend typecheck, lint, registry checks and production build pass.

The first final browser rerun on 30 October hit the resumed environment's socket restrictions before Chromium could start. It was rerun after session network permission was restored; this was an environment failure, not an application assertion.

No schema migration, new table, grant change, production setting mutation, cleanup or provider message send was introduced. Full menu field-level role cases, wider handoff/delivery exceptions, reward combinations, durable email dispatch and remaining admin pages remain open in the current remaining-work list.
