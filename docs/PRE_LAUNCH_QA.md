# Pre-launch QA — every action to carry out

**What this is.** One pass over every interaction the app ships, written as a
checklist you can run before launch. Admin first (it creates the data the
student side needs), then the student journey, then the flows that cross roles
(student → kitchen → rider → admin), then the two things that only exist in this
release (the settings seed and the pinned CORS list).

**How to read it.** `- [ ]` = one action. `→` = what must happen. If the arrow
does not happen, it is a bug: capture the four facts at the bottom of this file.

**Where to test.** On the deployed pair (frontend on
`https://holy-grills.vercel.app`, backend on the Render URL it calls), not
localhost — CORS, cookies, service workers and push only behave there. Use the
**test 2** Supabase project; production is not to be touched.

**The rule that decides disputes.** The backend is the source of truth. The
frontend may hide, warn or explain, but it must never allow what the API will
refuse, and never refuse what the API will allow. If the two disagree, the API
wins and the frontend is the bug.

---

## 0. Prepare the accounts and the data (once)

| Account | Role | Why it is needed |
|---|---|---|
| `super@…` | super_admin | global settings, feature flags, cross-campus admin |
| `admin@…` | admin | one campus's operations (permission split is tested here) |
| `kitchen@…` | kitchen | order lifecycle, capacity, prep list |
| `rider@…` | rider | dispatch, delivery, unclaimed |
| `student.a@…` | student | the main journey |
| `student.b@…` | student | squads, HP transfer, referrals (two logins needed) |

- [ ] All six accounts exist and are **active**, each with campus, department and level set.
- [ ] Two campuses exist in the DB if you want to test the campus split (optional); otherwise one campus for everything.
- [ ] Menu: at least 5 available items with prices; at least one with variations and one with addons.
- [ ] Delivery: at least 2 hostels (on-campus) and 1 gate + fee (off-campus).
- [ ] **Ordering windows**: today has an open window with capacity — most student flows below cannot run while the kitchen is closed.
- [ ] Feature flags ON: `squad_orders`, `free_side_credits`, `exclusive_spin`, `spin_and_win`, `hall_of_fame`, `badge_system`, `leaderboard_prizes`, `scheduled_orders`, `daily_checkin`, `event_ticket_tiers`, `birthday_hp`, `referral_milestones`, `hp_expiry_warnings`.
- [ ] Feature flags OFF (turn on only to test that feature): `marketplace_general`, `flash_redemptions`, `subscription_codes`, `abandoned_cart_nudge`. `hp_transfer` — turn ON to run §3.6, the default is off.
- [ ] Settings seed SQL has been run (§4.1) so the settings table is the authority, not just the env file.
- [ ] One student has 0 wallet balance and 0 HP (the "new user" path), one has both (the "existing user" path).

---

## 1. Admin actions — by sidebar panel

Sidebar groups: **Dashboard/Analytics/HP Economics**, **Menu**, **HP & Rewards**,
**Commerce**, **People & Ops**, **Config**. Every item below is a panel; the
permission note at the end of this section matters for two of them.

### Dashboard · Analytics · HP Economics (read-only, verify the numbers move)
- [ ] Dashboard: after a student order today, the counters include it → numbers match the orders list, not zero/stale.
- [ ] Analytics → **Sales & Revenue / Customers & Engagement / Operations & Logistics**: each tab loads, filters apply, export (if offered) downloads a file with the rows currently shown.
- [ ] HP Economics: the cost breakdown loads with today's HP awards (compare with the student's HP history).

### Menu
- [ ] **Menu Items** → create an item: name, price, category, image (upload), availability ON → it appears on the student menu within a reload.
- [ ] Edit that item's price → the student cart/checkout shows the new price.
- [ ] Toggle it **sold out** → the student side shows it sold out and cannot add it to the cart.
- [ ] Set kitchen capacity (daily) → the student side reflects it in the "orders left" line.
- [ ] Delete the item → it disappears from the student menu; any past order that used it still renders in order history.
- [ ] **Addons & Variations** → create a variation group + options, attach to the item → the student's item page offers them and the price changes in the cart.

### HP & Rewards
- [ ] **HP & Multipliers** → set a campus multiplier (>1) and an expiry → students on that campus see the live banner; the admin action notifies them once, not repeatedly.
- [ ] Set it back to 1.0 → the banner disappears.
- [ ] **Rewards** → create a reward (cost, stock) → it appears on the student rewards page; redeem it as a student, then fulfil the redemption here → status changes to fulfilled.
- [ ] **Free Credits** → grant a free-side credit to student A → the credit and its expiry appear on A's rewards and at checkout.
- [ ] **Exclusive Spin** → edit the prize pool; run a spin for a leaderboard-eligible student → the prize lands in that student's account and is visible to them.
- [ ] **Challenges** → create a challenge (target, reward) → it appears to students; activate/pause → the student sees live/paused; when a student completes it, the grant arrives and the challenge shows the winner.

### Commerce
- [ ] **Orders** → filter by status/campus; open one order; move its status through the legal steps (the panel offers only the legal next step) → the student sees each change and gets the notification.
- [ ] Cancel/refund an order from here → the student's order and wallet/HP reflect it.
- [ ] **Wallet** (transactions) → credit a student's wallet with a reason, then debit → both rows appear in the ledger and the student's balance moves by exactly those amounts.
- [ ] **Events** → create an event with a free tier and a paid tier; publish → students see it; register a student from the admin side → their ticket shows in My Events.
- [ ] **Catering** → a student submits a catering request; open it here, quote/accept/decline → the student's request status follows.
- [ ] **Marketplace** → Listings / Vendor Requests / Purchases / Reports: approve a vendor request, take a listing down → students see the listing disappear; a purchase shows in Purchases.
- [ ] **Promo Codes** → create a code (percentage, min order, expiry, usage limit) → a student applies it at checkout and the discount matches; reusing past the limit is refused by the API.
- [ ] **Abandoned Carts** → after leaving items in a cart, the cart appears here; send a nudge → the student gets an in-app/push notification whose link opens the cart.
- [ ] **Reviews** → leave a review as a student; moderate it here (hide/publish, promote to testimonial) → the student side and the storefront follow.

### People & Ops
- [ ] **Users** → search a student; open the profile; tabs **HP History / Wallet / Orders** show that user's real rows.
- [ ] Grant HP from the user panel (amount + reason) → the student's balance changes and a notification arrives.
- [ ] Change a user's role (make a test account kitchen, then rider) → that account's menu/access changes after re-login; access to the admin panel is refused for non-admins.
- [ ] Deactivate a test account → login is refused with a clear message; reactivate.
- [ ] **Delivery → Windows**: create a window (start/end, capacity, delivery times) → students see it in the schedule sheet.
- [ ] **Delivery → Ordering**: close ordering for today → the student side shows closed with the next opening, and checkout refuses placing with the backend's own message.
- [ ] **Delivery → Batches**: assign a batch to a rider → the rider sees it in their list.
- [ ] **Delivery → Zones & Fees**: change a delivery fee → the student's checkout total changes before payment.
- [ ] **Delivery → Riders**: roster + payments tabs load; mark a rider payment → the row persists.
- [ ] **Delivery → Abandoned**: same list as the Abandoned Carts panel (either entry point works).
- [ ] **Order Locks** → view locks; reschedule one within the limit → the student's lock shows the new date; try to exceed the max reschedules → the API refuses and the UI explains.
- [ ] **Store / Stock** → add an ingredient, log a purchase, log usage/waste, correct a count → the stock balance and the low-stock line follow the arithmetic.
- [ ] **Campaigns** (notifications) → send a blast to one segment/tier/channel → student A receives exactly one, in the chosen channel; schedule one for +2 minutes → it does not arrive early.
- [ ] **Leaderboard** → Leaderboard Rewards: set the prize/pool → the student leaderboard shows it; Hall of Fame: an entry appears for the eligible student.

### Config
- [ ] **Departments** → Departments / Academic Levels: add one of each → they appear in the student's profile/registration pickers.
- [ ] **Storefront** → each sub-tab (Hero, Banners, Promos, Testimonials, Share Templates, Catering, Our Story, Popup Flyer, Tier Icons, Early Supporters, Newsletter, Hours): make one change → it appears on the student home page (and the popup only while `first_order_gift`/flyer is on, if that is how it is configured).
- [ ] **Onboarding** → first-order gift: set the item name and the launch window; toggle it → a first order either includes the gift or does not (see the known conflict in §5).
- [ ] **Feature Flags** → turn `marketplace_general` ON → the student nav gains the marketplace; OFF → it disappears. Repeat once for `hp_transfer`.
- [ ] **Settings** (system settings) → open it: the values seeded by §4.1 are listed; edit one (e.g. `wallet_min_card_topup` → 200) → the student's top-up screen enforces the new minimum **without a deploy**; change it back.
- [ ] **Settings** as a **campus admin** (not super admin): a global row is read-only/refused; a row for your own campus can be written. The API must refuse the global write even if the UI is bypassed.
- [ ] **Academic Calendar** → add a term/holiday → ordering windows/capacity for that day follow it; remove it.
- [ ] **Webhook Events** → the delivery log shows Paystack/other events with status; a failed one is retryable (or clearly marked non-retryable).
- [ ] **System** → Cron Jobs tab lists the jobs with last-run times (no red/failed job); Audit Log shows the actions you just did, with your admin id; Health is green.

---

## 2. Student actions — the journey, in order

### Guest (no account)
- [ ] Open the site fresh (private window): the campus picker appears; pick a campus → the menu loads that campus's items.
- [ ] Reload → **the campus choice persists** (no second picker, no global view).
- [ ] Open a deep link (`/menu/<item>`, `/events/<id>`) in the same window → the link opens with the chosen campus, not a global/blank view.
- [ ] Add items to the cart → cart survives a reload (guest cart).
- [ ] Change campus → the cart/menu switch campuses coherently (no cross-campus item leakage).

### Account
- [ ] Register with phone/email/department/level → the welcome bonus (if enabled) arrives and the profile shows campus/department/level.
- [ ] Log out, log back in → session restores, no double HP award.
- [ ] Forgot password → email arrives, reset link opens `/reset-password`, new password works, old one does not.
- [ ] Profile: edit name/phone/photo (upload) → saves; sound-effects toggle works; **Delete Account** is available and clearly confirmed (only run this on a throwaway account).
- [ ] Addresses: add an off-campus address with a pin and a gate, set it default → it is pre-selected at checkout; edit and delete work.

### Browse → cart → checkout
- [ ] Menu: search/filter/categories work; sold-out and closed-kitchen states are visible.
- [ ] Item page: variations and addons select, quantity limits hold, notes save → the cart line matches the price shown.
- [ ] Cart: quantity +/-, remove, clear all, "saved items → move to cart" behave.
- [ ] Checkout: choose on-campus (hostel) and off-campus (gate or pin) → the fee and the address block match the choice.
- [ ] Off-campus beyond the delivery radius → the API refuses with its own message (and the UI does not pretend it worked).
- [ ] Promo code: valid code discounts, invalid/expired code is refused, discount never exceeds the total.
- [ ] Free-side credit, if held: the credit is attached at ₦0 and consumed on placement (it does not stay available afterwards).
- [ ] Squad order (with student B in a squad): the squad discount applies when the item lines reach the minimum, and not before.
- [ ] Wallet: top up by card (minimum enforced, HP awarded per the configured rate); pay a whole order from the wallet; **split** payment (wallet + card) for a partial amount → both legs are recorded and the order is placed once.
- [ ] Schedule an order while the kitchen is closed → it is placed against the next window (§5 explains the "open ⇒ order now" rule).
- [ ] Place the same order twice quickly (double-tap) → exactly one order is created (the API's guard, not the button's).

### After the order
- [ ] Confirmation screen: order id, total, delivery point; share button awards HP once.
- [ ] Orders list: Active vs Past are correct; open the order → items, discounts, HP earned/redeemed, window, rider.
- [ ] Track Orders: live status follows the kitchen/rider changes within a reload; a guest order tracks with its claim token.
- [ ] Cancel while still cancellable → status/refund reflect it; cancel after the cutoff → refused with the API's message.
- [ ] Reorder → the same items land in the cart at current prices.
- [ ] Review (overall, kitchen, rider ratings + text) → saved once, HP awarded once, visible to the admin panel.

### HP, rewards, streak
- [ ] Rewards: balance, "HP story", unlock history load; redeem a reward → HP is spent and the redemption appears (then fulfil it as admin).
- [ ] Spin & Win: spin available/used states, prize credited, "no spins right now" when exhausted.
- [ ] Free sides: the credit list shows expiry; using one at checkout consumes it.
- [ ] Graduation reward: at/above the level, the claim works once; below it, it is not offered.
- [ ] Flash redemption (if enabled): discount and quantity cap apply.
- [ ] HP transfer (if enabled): send HP to student B above the minimum → both balances move, both get notified; below the minimum or with too few orders → refused.
- [ ] Streak: daily check-in awards HP once for the day; a second check-in does not double-award; the weekly bonus lands at the end of the week; the monthly pending cap holds.
- [ ] Tier detail: progress, perks and the multiplier match the tier table.

### Social & discovery
- [ ] Squads: create, invite student B (join), order together, leave/remove a member, HP split visible after the order.
- [ ] Referrals: copy/share the code; student B signs up with it and places a first order → the referrer's HP lands and the win shows in the dashboard.
- [ ] Leaderboard: your rank moves with HP; prizes visible; Hall of Fame entries open for the eligible.
- [ ] Marketplace: browse, listing detail (cash vs HP), purchase with HP, My Purchases, Sell → vendor request submitted.
- [ ] Events: browse, register (free and paid tier), My Events, ticket QR + **Download ticket PDF**, cancel/refund if allowed.
- [ ] Notifications: the bell shows unread count; clicking a notification opens the right screen (order → that order, wallet → wallet, squad → squad, event → event); "Mark all" clears; Preferences toggles stop a channel (verify by triggering that type again).
- [ ] Static pages: FAQ, Our Story, Terms, HP Education render (these are the pre-rendered pages — check they are not blank if JavaScript is slow).
- [ ] Offline/refresh mid-flow: refresh on checkout/order detail → the page recovers with the same data, no duplicate order.

### Kitchen account
- [ ] Today's Capacity shows the real remaining count; the accepting toggle changes whether students can order.
- [ ] Start Preparing → Mark Ready on a live order → the student's status follows and the notification arrives.
- [ ] Consolidated Prep List lists today's items with quantities matching the placed orders.
- [ ] Marking a status twice / out of order is refused or idempotent (no double transitions).

### Rider account
- [ ] Batch assigned by the admin appears; start delivery → paths/status update.
- [ ] Delivered → the student's order closes and earns HP if applicable.
- [ ] Unclaimed / delivery-attempted flows are offered only where the backend allows them.
- [ ] Completed batches list shows the finished deliveries with COD/amount where relevant.

---

## 3. Cross-role flows (the ones that prove the wiring)

| # | Flow | Do this | Must be true at the end |
|---|---|---|---|
| 3.1 | **Order lifecycle** | Student places → kitchen Start Preparing → Mark Ready → admin assigns batch to rider → rider Delivered | Each step visible to the student; exactly one notification per step; HP awarded once on delivery |
| 3.2 | **Scheduled order** | Close ordering → student schedules → window opens → kitchen prepares | The order lands in the window the student was shown, not a different one |
| 3.3 | **Capacity full** | Fill a window to capacity, then order | API refuses with capacity + next available date; the UI retries once with the accepted next date only when the user confirms |
| 3.4 | **Squad order** | Student B joins A's squad; A orders ≥ minimum item lines incl. B's items | Squad delivery/order discount applied per settings; HP split per the flag; both parties can see the squad |
| 3.5 | **Free sides** | Admin grants a credit → student uses it at checkout | ₦0 line on the order, credit consumed, expiry respected |
| 3.6 | **HP transfer** | A sends HP to B (flag on, minimum met) | Balances move, both notified, ledger rows exist |
| 3.7 | **Order lock** | Student locks a price → admin reschedules within the limit → student claims | Discount/HP per settings; reschedule count enforced |
| 3.8 | **Event check-in** | Student registers → shows QR → staff scans | Check-in recorded once, check-in HP awarded once, duplicate scan does not double-award |
| 3.9 | **Top-up → HP** | Student tops up the wallet | HP awarded per ₦ on the configured rate; no HP for a top-up below the minimum |
| 3.10 | **Abandoned cart** | Student leaves items → admin sends nudge | Notification arrives with a working deep link to the cart |
| 3.11 | **Graduation** | Student reaches the level → claims | Grant once, status shows in admin Onboarding |
| 3.12 | **First-order gift** | New student places a first order (gift ON, inside the launch window) | Gift line at ₦0 only while enabled and inside the window (§5 has the flag conflict to settle first) |
| 3.13 | **Settings change** | Admin edits a business number in Settings | The student side reflects it on the next load, with no deploy (§4) |
| 3.14 | **Campus isolation** | Campus admin changes their campus's number; student on that campus sees it, other campus unchanged | Per-campus row wins over global; other campus keeps the global value |

---

## 4. This release's two infrastructure checks

### 4.1 Settings seed — `holy-grills-backend/migrations/2026-10-04_seed_system_settings.sql`
- [ ] Run it in the Supabase SQL editor → the NOTICE lists the rows inserted (43 on a clean table) and skips any key that already had a value.
- [ ] Run it a second time → nothing is inserted (idempotent), and any value you edited by hand is untouched.
- [ ] Verify: `SELECT key, value, is_public FROM public.system_settings WHERE campus_id IS NULL ORDER BY key;`
- [ ] Change `squad_order_min_items` from 3 to 4 in the admin Settings panel → add items to a student cart and watch the squad-order threshold move without a deploy; set it back to 3.
- [ ] Confirm no secret is in the table: nothing matching `SUPABASE_*`, `PAYSTACK_*`, `CLOUDINARY_*`, `SECRET_KEY`, `RESEND_*`, `ONESIGNAL_*`, and `is_public = true` only on business values.

### 4.2 CORS — the wildcard is gone
`app/__init__.py` now passes `Config.CORS_ORIGINS` (env-overridable) instead of `"*"`.

- [ ] From a terminal:
      `curl -s -o /dev/null -D - -H "Origin: https://holy-grills.vercel.app" https://<backend-host>/api/messages?prefix=FE_ | grep -i access-control`
      → `access-control-allow-origin: https://holy-grills.vercel.app`
- [ ] Same command with `Origin: https://example.com` → **no** `access-control-allow-origin` header.
- [ ] Preflight for a campus-scoped call:
      `curl -s -o /dev/null -D - -X OPTIONS -H "Origin: https://holy-grills.vercel.app" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: X-Campus-ID,Authorization" https://<backend-host>/api/messages`
      → `204` with the origin echoed and `X-Campus-ID` allowed.
- [ ] Browse the live site with devtools open: **no CORS errors** on any request (menu, checkout, wallet, notifications).
- [ ] Local dev still works (`localhost:5173`) — the default list includes it.
- [ ] Preview deployments: the default list does **not** include `holy-grills-<hash>.vercel.app`; if you test on a preview URL, add it via `CORS_ORIGINS` on that environment.

---

## 5. Known open items — expected behaviour, not new bugs

These are deliberate or already-reported; do not re-file them, but do say if the
behaviour is worse than described.

| Item | Current behaviour | Why |
|---|---|---|
| Checkout scheduling while the kitchen is **open** | A stored scheduled window is ignored: the order goes through as an immediate order | The schedule flow is offered while closed; the API decides placement. Changing this is a decision, not a fix |
| `daily_checkin_hp`, `streak_cycle_days`, `wallet_min_withdrawal`, `order_lock_max_discount_pct`, `birthday_hp`, `graduation_hp`, `signup_bonus_enabled` | Shown to the frontend but **not read by the backend** | Deliberately left out of the seed; `birthday_hp`/`graduation_hp` come from tiers/levels, the rest are dead or unbuilt. Seeding them would create values that an edit cannot move |
| First-order gift | The gift service defaults to OFF when no settings row exists, while the env default is ON | A real conflict to settle before enabling the gift |
| `hp_transfer`, `marketplace_general`, `flash_redemptions`, `subscription_codes`, `abandoned_cart_nudge` | Default OFF | Product decision; flags are in Feature Flags |
| React Router advisories | Not addressed | Closed as accepted risk |
| HP bundle sizes (bundle weight) | Not addressed | Deferred |
| CSP enforcement flip | The policy is report-only until the browser pass is clean | A separate pass; the console must be free of CSP violations for the real flows before enforcing |

---

## 6. When something fails — capture these four facts

1. **Role + account** (student A, campus admin, super admin…), and the campus selected.
2. **The screen + the action** in the words of the UI, plus the exact time.
3. **The API call**: devtools → Network → the failing request's URL, status and response body (this is what the backend will be judged on).
4. **A screenshot** of the screen state.

Anything about *numbers* (a discount, an HP amount, a capacity) should be
cross-checked against the settings value in the admin panel — if the panel and
the behaviour disagree, the row or the wiring is the bug, and §4.1's verify query
tells you which.
