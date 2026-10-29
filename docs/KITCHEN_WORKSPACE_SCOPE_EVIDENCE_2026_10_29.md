# Kitchen workspace scope and settings truthfulness — 29 October 2026

This batch repairs the kitchen workspace's campus selection, settings presentation and failed-read behavior. It is not whole-kitchen or whole-admin sign-off.

## Findings and resulting behavior

- Kitchen endpoints require an explicit `campus_id` query for super-admins. The workspace previously omitted it. Super-admins now select a campus before loading; queue, scheduled date, windows, metrics, settings, preparation summary, batch advance and handoff calls carry that campus. Capacity and public ordering-status reads receive the same explicit campus header. Switching campus remounts the workspace, clearing the previous campus's orders and selections. Ordinary staff use their verified profile campus; the backend retains its own authorization checks.
- The former header switch wrote `kitchen_settings.is_accepting_orders`, but backend admission does not consume that key. Kitchen staff also could not PATCH settings. Removed the ineffective switch and its misleading success messages; admins/super-admins get a direct link to Delivery's ordering-window controls. No new emergency-pause feature is claimed. Opening/closure still uses the existing ordering windows, dated overrides and capacity rules.
- Settings no longer advertise unused auto-accept, legacy opening/closing-time or preparation-target keys as operative controls. Read-only capacity and availability come from the same server responses used by checkout. An absent daily cap is distinct from zero capacity.
- Background failures no longer silently leave an apparently current operational screen. The page displays a stale-data warning and hides operational actions until a successful refresh or Retry. Refresh also reloads settings/capacity/status so a saved admin change is not frozen until a full page reload.
- All new user-facing copy resolves through `app/messages.py`.

## Executed evidence

- `holy-grills-frontend/scripts/test-kitchen-campus-browser.py`: real React page, Chromium and controlled HTTP; super-admin All Campuses blocks unscoped reads; select B despite profile A; query scope; switch back to A clears B; handoff scope; no ineffective switch; true server availability overrides legacy false setting; admin scheduling link; queue outage hides actions; automatic recovery; kitchen-only read-only view despite a foreign stored admin selection.
- Existing `test-kitchen-handoff-map-browser.py`: future date cannot prepare, native kitchen rider assignment, rider saved-pin directions, blocked map tiles and GPS fallback remain passing.
- Backend suite: **769 passed**. No backend admission, schema, grants, scheduling, financial or order-state logic changed in this batch. Existing delivery-area role/scope tests remain passing.
- Frontend typecheck, lint, message-registry check and full production build pass. Registry check reports six existing unrelated fallback-copy differences; no missing new key.

No production orders, campus settings, uploaded content, test profiles or provider messages were created/changed/deleted by these browser fixtures. Provider dispatch, remaining feature-flag consumers, broader kitchen action races, and the remaining admin page matrix stay separate open audit work.
