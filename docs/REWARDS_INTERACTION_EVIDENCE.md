# Rewards interaction verification — 20 October 2026

Implementation commit: `d851e23cd4abe5630acf547902ee398d06c20e81` (based on the shared audit working tree). This batch preserves the current brand colors. It removes badge artwork/inventories and the large graduation/free-side banners while retaining plain HP milestone progress, recurring challenges, tier progress, and balance. Graduation eligibility and automatic redemption are separate batches.

## Verified locally

- `/workspace/.venvs/holy-grills/bin/python -m unittest tests.test_rewards_interactions tests.test_user_search_scope tests.test_badges_and_address_fields`: **30 passed**. Nine new tests cover read-only bonus status, both prerequisite actions, explicit/repeated claim, generic completion bypass prevention, unavailable-claim error, student email privacy/admin Gmail matching, delivered-order threshold, and scoped HP milestone progress without badge artwork.
- `node scripts/test-push-registration.mjs`: **passed** against the actual bundled OneSignal module with controlled dependencies. Opening the prompt does not finish the flow; permission alone does not finish it; permission plus subscription/player ID and successful API registration do. Denial and registration failure cannot claim. Event listeners are removed after completion. A 45-second timeout and one-second subscription checks prevent a permanently busy card.
- Frontend `npm run typecheck`, `npm run build:client`, and ESLint over this batch's frontend files: **passed**. Client build emits existing chunk-size/dynamic-import notices.
- `git diff --check`: **passed** before the implementation commit.

## Native browser checks with controlled local API fixtures

Harness: `/workspace/work/ecosystem-audit/rewards-20261020/browser_local.py`, local Vite port **5177**, Chromium viewport **390 × 844**. The parent agent ran Chromium with its approved local network profile because this agent's restricted sandbox rejected Chromium's socket setup. Results: `/workspace/work/ecosystem-audit/rewards-20261020/browser-local-results.json`.

The harness uses actual application pages/components and intercepts every `/api/` request. These are browser/UI contract checks, **not Supabase persistence or real-account proof**. It performs no remote writes.

Verified browser outcomes:

1. Confirm Redemption renders directly under `document.body`; its scrim bounds are exactly `x=0, y=0, width=390, height=844`, escaping transformed ancestors. Backdrop click closes it.
2. Opening Challenges reads bonus status without POST. Claim sends one explicit POST; reload retains the completed fixture state without a second claim.
3. A plain lifetime HP milestone shows its real fixture progress (`1/3`) after badge inventory removal.
4. Podium users appear once each, with remaining rankings following them; the first three are not duplicated in the list.
5. Typing successive recipient queries sends only the final debounced email query. Suggestions are selectable; the visible `2/3 delivered orders` state keeps Send disabled.

Screenshots: `redemption-local-mobile.png` and `leaderboard-local-mobile.png` beside the harness.

## Still open for live verification

- Genuine installed-app/browser permission behavior and a real OneSignal subscribed device, followed by HP persistence/retry against the database. Browser installation is confirmed client-side by standalone mode or `appinstalled`; it is not remotely attested by the server. The server verifies bonus eligibility from stored milestone completions and requires a registered web token for the push milestone.
- Native administrator challenge creation followed by an eligible student's real claim and HP ledger verification.
- Live transfer success/insufficient eligibility, admin credit grant, and configured spin outcomes against isolated database fixtures. Existing isolated setup script was not rerun or used to mutate users in this batch.
- Graduation gating and pending-redemption delivery/automatic fulfillment belong to their separate implementation/evidence batches; this UI does not invent a fulfilled response.
