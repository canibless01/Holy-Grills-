# Holy Grills: Page-by-Page Capabilities & Retention Guide

**For:** Marketing, brand, design, community and operations teams  
**Reviewed:** 15 October 2026  
**Purpose:** Explain what the current site allows customers and staff to do, and how those capabilities support acquisition, repeat purchases, loyalty and community.

## How to use this document

This is a review of the current frontend pages, backend behaviour and existing audit records in this repository—not a proposal for a new website and not a live-production certification. No application code was changed to produce it.

“Supported” means there is implementation in the current code. It does **not** mean the feature is switched on at every campus, that a particular reward is in stock, or that a real payment, email or push provider has been independently verified in this review. Features can depend on staff permissions, campus settings, eligibility, scheduled background work and external services. Important gaps are called out below.

The retention explanations describe **how a feature can encourage behaviour**, not measured proof that it has increased retention. Example messaging is a direction for copy, not approved campaign terms. Confirm live amounts, dates, eligibility and fulfilment before publishing.

### Contents

1. The ecosystem in plain language
2. Customer pages: discovery, accounts and ordering
3. Customer pages: loyalty, community and rewards
4. Customer pages: events, marketplace and support
5. Admin: every main section and its business purpose
6. Kitchen and rider pages
7. Automated retention journeys
8. Campaign and design planning guide
9. Limitations and claims to avoid
10. Source and coverage reference

---

## 1. The ecosystem in plain language

Holy Grills combines a campus food-ordering service with a loyalty and community programme. Its central loop is:

**Discover food → order → receive the meal → earn usable HP and unlock some Pending HP → progress towards benefits → return to order or participate again.**

Several connected loops strengthen that journey:

| Loop | Features involved | Reason to return |
|---|---|---|
| Food convenience | Menu, saved items, addresses, wallet, reorder, scheduling | The next purchase takes less effort. |
| Progress | HP balances, tiers, histories and perks | Customers can see value accumulating. |
| Habit | Check-in streaks, weekly food-order streaks, recurring challenges | There is a fresh short-term goal. |
| Social growth | Referrals, squad orders, HP transfers and sharing | Friends create reasons to join and participate. |
| Recognition | Leaderboards, badges and Hall of Fame | Participation can become visible status. |
| Reward spending | Catalogue redemption, flash redemption, sides and spin prizes | HP and achievements lead to practical benefits. |
| Community | Events, ticket benefits, attendance HP and catering | The relationship extends beyond a food transaction. |
| Re-engagement | Inbox, campaigns, cart reminders and inactivity messages | Customers receive prompts to resume an unfinished or lapsed journey. |

### The most important distinction: Active HP versus Pending HP

- **Active HP** is the spendable points balance.
- **Pending HP** is points earned through qualifying activities that are not yet spendable.
- Qualifying delivered food orders unlock some Pending HP, subject to the configured earning/unlock rules and available pending balance. A delivery does **not** necessarily unlock the entire pending balance.
- Food-order earning and Pending HP unlocking are separate benefits of the same completed purchase.
- A monthly cap applies to designated free-activity Pending HP awards. It is not a universal cap on all food-order HP.
- HP is not the same as wallet money. The customer-facing balance deliberately does not present HP as a cash-out balance.

This structure gives non-purchase activities a connection back to real orders. Good messaging explains that connection rather than saying every activity immediately produces spendable points.

### Four different meanings of “promotion”

1. **Promo codes:** reduce the eligible cash cost under the code’s conditions.
2. **HP earning boosts:** change how many points eligible food purchases earn; these include per-item and broader configured multipliers.
3. **Flash reward redemption:** temporarily lowers a reward’s HP redemption cost, with a time window and limited slots.
4. **Promotional banners and campaigns:** communicate an offer; a banner alone does not create its pricing or eligibility rules.

There is no separate, general-purpose “flash-order multiplier” product to promise. Use the actual promo, earning-boost or flash-redemption mechanism appropriate to the campaign.

---

## 2. Customer pages: discovery, accounts and ordering

### 2.1 Home — `/`

**What customers can do**

- Discover the food offer, featured menu content and routes into ordering.
- See promotional hero/banner content and calls to action.
- Discover the HP programme, leaderboard, rewards and streak concept.
- See configured testimonials and early-supporter content.
- Subscribe to the newsletter and follow routes into events, catering and other site areas.

**What staff control:** Homepage content sections, ordering of sections, promotional artwork, desktop/mobile banner assets, links, scheduled banner visibility and early-supporter entries. Displayed content still depends on the page’s supported section types and campus configuration.

**Retention role:** Gives new visitors a reason to buy now and introduces reasons to come back before their first purchase.

**Design/messaging opportunity:** Make the food proposition primary, then explain one simple loyalty loop. Avoid presenting every loyalty feature as a competing first action.

### 2.2 Campus selection and shared navigation

The site scopes important browsing and ordering experiences to a selected campus. Menus, delivery coverage, events, offers and administration can vary by campus. Shared navigation connects ordering, account and loyalty areas; installation and notification prompts also appear in the broader experience.

**Retention role:** Relevant local information builds trust. An offer available at one campus must not appear to be a universal entitlement.

### 2.3 Register, Login, Forgot Password and Reset Password

**Pages:** `/register`, `/login`, `/forgot-password`, `/reset-password`.

Customers can create an account, sign in and recover access. Registration collects the identity and campus/academic information needed by the programme. Referral attribution can connect a new account to an invitation. Account-backed journeys provide HP, wallet, referral, squad and history features that guest browsing does not.

**Retention role:** Turns an anonymous purchase into a recognisable customer relationship with persistent progress.

**Important:** The current default signup HP bonus is zero. Do not advertise “free points just for signing up” without confirming a deliberately configured live offer. First-order bonuses and first-order physical gifts are separate mechanisms.

### 2.4 Menu — `/menu`

Customers can browse campus-relevant food, use the page’s category/search/filter controls, see prices and availability, inspect dishes and add eligible items to the cart. Menu presentation can include ratings and HP-earning information.

Staff can manage categories, item descriptions/images/prices, item availability, daily item limits and kitchen capacity. Item-specific earning boosts can direct attention towards selected meals.

**Retention role:** A clear menu converts intent into a purchase; reliable availability prevents disappointment that would undermine loyalty.

**Messaging direction:** “Find your next plate—and see what it earns.” Use only the actual earning preview for numerical claims.

### 2.5 Item detail — `/menu/:id`

Customers can inspect a dish, choose quantity, select supported variations or add-ons and include customisation/notes where available. Item information and review data help purchase confidence.

**Staff control:** Variation groups/options, required or optional selections, add-on groups, limits and prices.

**Retention role:** Personalisation makes the order feel appropriate to the customer and supports repeat preferences. Add-ons also provide a route to a larger basket.

**Boundary:** Do not assume every extra earns the same HP as food. The food HP calculation excludes add-on lines.

### 2.6 Cart — `/cart`

Customers can review selected food, adjust quantities, remove items and continue to checkout. Account-backed saved-for-later functionality lets customers set items aside and move them back into the active cart later. Current menu conditions are re-evaluated when ordering; a saved cart is not a permanent price or stock reservation.

**Retention role:** Preserves intent when someone is not ready to buy. Saved items and cart recovery give the brand a useful return journey rather than a generic sales message.

### 2.7 Checkout — `/checkout`

**What customers can do**

- Review the server-calculated price, delivery fees, discounts and HP preview.
- Provide delivery information using supported campus hostels/gates, saved addresses or off-campus location details, subject to coverage.
- Apply an eligible promo code.
- Pay by card, wallet, or a wallet-plus-card split where supported for signed-in customers.
- Order as a guest by card without first opening an account.
- Associate an eligible squad and its members with the order.
- Select eligible free-side benefits separately from delivery and food-HP benefits.
- Choose a specific available delivery benefit and food-HP bonus, or save those benefits for later.
- Schedule an order through the supported future-opening/delivery flow when available.
- Recover an uncertain checkout using the saved original request rather than starting a different order blindly.

**How reward choice works:** An explicitly chosen food-HP bonus is reserved for that order and applied when the order is delivered. It is not spent merely because the customer viewed a quote. A qualifying early cancellation releases the reservation. Explicitly choosing to save the benefit prevents another order from taking that reservation. The current chooser starts with save-for-later rather than forcing benefit use.

**Retention role:** This is where earned value becomes tangible. Customers also get control over when to use benefits, which can increase their reason to return.

**Important limits:** Card payment needs real provider setup and verification. Saving an order is not the same as successful payment. Delivery benefits can be capped; do not promise unlimited free delivery. Full combinations of every discount, reward and refund scenario remain an open audit area.

### 2.8 Order confirmation — `/order-confirmation/:id`

The confirmation page acts as a receipt and next-step guide. It shows order/payment information and the applicable order reward summary. Customers can continue tracking and take supported payment actions where payment remains outstanding. The selected food-HP reward can be shown as reserved, applied or released.

Order sharing is also a retention/acquisition mechanism: a recorded confirmation share can earn Pending HP under the configured daily limit. The current share default is 25 Pending HP, at most once per day across orders—not an unlimited award per share or proof of a public social post.

**Retention role:** Reassures the buyer, explains the value of the purchase and turns the post-purchase moment into a possible invitation to friends.

### 2.9 Orders — `/orders`

Customers can revisit their order history and inspect individual orders. Reorder support retrieves a previous order’s items at **current menu prices** rather than copying an old price promise.

**Retention role:** Makes repeat purchasing easier and preserves the customer’s relationship history.

### 2.10 Order detail — `/orders/:id`

Customers can inspect items, payment and fulfilment information, status history and reward details. Eligible orders can expose payment continuation, cancellation, rider contact or review actions as appropriate to their state. Delivered orders can receive an overall review and separate kitchen/rider ratings, with supported review images.

**Retention role:** Transparency and feedback protect trust. Review awards can turn useful feedback into another step in the loyalty journey.

**Boundary:** Customer cancellation is limited to the allowed pre-preparation state; it is not an anytime cancellation guarantee. Account owners and guest-token holders have different access paths.

### 2.11 Track Orders — `/track-orders`

Provides a customer-facing tracking journey, including the guest order access flow using the order’s protected reference/token information. Active-order cards elsewhere in the site also help signed-in users return to an ongoing order.

**Retention role:** Reduces uncertainty and repeated support contacts.

**Do not overclaim:** Rider location updates exist behind the scenes, but that is not sufficient evidence of an always-live customer map or a guaranteed minute-by-minute arrival time.

### 2.12 Dashboard — `/dashboard`

The signed-in hub brings together HP/tier information, active or recent orders and shortcuts into ordering and ecosystem activities. It helps customers discover benefits without finding every page independently.

**Retention role:** Makes progress visible and supplies a useful next action each time someone returns.

### 2.13 Wallet — `/wallet`

Customers can see their wallet balance and transaction history, start card funding and request the supported dedicated bank-transfer account. Wallet funds can be used in supported purchases, including split payments.

**Retention role:** Stored value and easier repeat payment reduce checkout friction.

**Important:** This is a closed-loop spending wallet, not a promised withdrawal or cash-out account. Refund flows generally return collected cash portions to the wallet rather than automatically reversing a card charge. Real bank-account provisioning and payment-provider delivery need environment verification.

### 2.14 Profile — `/profile`

Customers can manage supported personal details, profile photo, nickname, academic information and account-security settings. Public-ranking name preferences help customers choose how they are represented. Account deletion is also exposed through the profile journey.

**Retention role:** Personal identity, relevant milestones and control over public representation support belonging and trust.

**Boundary:** A self-entered academic level is not independent proof of graduation. Graduation campaign eligibility needs clear policy.

### 2.15 Addresses — `/addresses`

Customers can maintain saved delivery addresses and reuse supported details during checkout.

**Retention role:** Makes the second and subsequent order easier than the first. Coverage and fees still depend on the actual delivery location and campus rules.

---

## 3. Customer pages: loyalty, community and rewards

### 3.1 HP Education — `/hp-education`

Explains earning, Active versus Pending HP, tier progression and places to use points. It also provides access to HP gifting/transfer where enabled.

**Rules the teams should understand**

- Food earning defaults to 1 HP per ₦10 of eligible food value, before applicable boosts. Live settings can change this.
- Pending unlocking is tied to the configured food earning/unlock rates. With the default rates, an eligible ₦1,000 food spend corresponds to 100 base food HP and up to 30 Pending HP unlocked, assuming sufficient pending balance. This is an illustration, not a universal checkout quote.
- Tier progress uses HP earned over a rolling 120-day period, not simply today’s spendable balance.
- Spending points should not be described as automatically lowering the customer’s tier.
- Inactivity rules and tier-maintenance rules are separate. Scheduled work recalculates tier eligibility and manages downgrade grace periods.

**Retention role:** Helps customers understand how to make progress and why the next order matters.

### 3.2 Rewards — `/rewards`: reward catalogue

Customers can browse available rewards, see HP costs and applicable tier/stock restrictions, confirm an eligible redemption and revisit redemption history. Admins maintain the catalogue and review fulfilment.

**Retention role:** Gives earning a concrete destination. A points balance is more motivating when the customer knows what it can unlock.

**Boundary:** Redeeming a reward is not the same as immediate physical delivery. The catalogue has fulfilment types and status handling. Physical delivery/next-order attachment flows still have open end-to-end audit work.

### 3.3 Rewards: flash redemption

Admins can open a flash window on a selected reward with:

- A start and end time.
- A limited number of redemption slots.
- A configured HP discount percentage.

Customers see the active flash price, time remaining and slots where supplied, and can redeem while eligible and while slots remain. The claim process coordinates the points deduction and limited slot claim to avoid treating unlimited clicks as unlimited stock.

**Retention role:** Creates a time-sensitive reason to check the site and a useful moment for a notification campaign.

**Messaging direction:** “Use fewer HP on this reward until [time], while [quantity] slots last.”

**Important:** Some older descriptions call flash offers “50% off for 24 hours.” The current creator supports configurable windows and discounts. Do not treat those old defaults as compulsory live terms or describe this as a cash discount on food.

### 3.4 Rewards: challenges and badges

The current programme distinguishes:

- **Badges:** lifetime/one-time achievements.
- **Challenges:** recurring weekly or monthly targets.

Supported achievement subjects include first delivered order, first review, first completed referral, first event check-in, first squad activity, first HP gift, total earned HP, membership age and graduation. Recurring targets include delivered-order count, review count, completed referrals, event check-ins, squad activity and streak milestones. Department/faculty recognition can be staff-awarded.

Customers can see progress and attempt to claim/complete eligible milestones. Most supported activity targets are checked against actual site records, not awarded simply for clicking Complete.

**Retention role:** Breaks a large loyalty goal into achievable steps and creates weekly/monthly reasons to return.

**Important qualifications**

- Social follow is self-declared and one-time; it is not independently verified through a social network.
- App-install and push-subscription bonuses have their own supported eligibility checks/settings.
- A birthday HP award exists separately from the milestone catalogue. A generic birthday badge verification branch is not implemented.
- Do not promise arbitrary new challenge types. Staff select from supported triggers.

### 3.5 Rewards: free sides

Eligible customers can see free-side credits and choose from the staff-curated side options. Credits have balances and expiry dates. Checkout has a separate selection path for the chosen side benefit.

**Staff control:** Side catalogue, images, active options and manual credit grants, plus programme settings and qualifying tier/leaderboard awards.

**Retention role:** A tangible food benefit provides a clear reason for a subsequent order.

**Messaging direction:** “You have a side credit—choose an eligible side on your next qualifying order.” Confirm expiry and checkout conditions.

### 3.6 Rewards: exclusive spin

Customers with valid spin credits can use the wheel and see their saved prize history. The result is chosen by the backend; the animation is the presentation of an awarded result, not the source of the entitlement.

Staff configure prize names, active status, relative selection weights and the **actual effect** of each prize. Supported effects are HP, capped delivery benefits, food-HP multipliers and physical prizes. Staff can also grant spin credits directly with validity and reason.

**Retention role:** Adds surprise to recognition and can produce a benefit that encourages the next purchase.

**Important:** A prize label does not implement its effect by itself. Renaming something “free delivery” is not a substitute for configuring the delivery benefit. Multiple food-HP wins are kept as separate benefits, and selected benefits can be saved or reserved at checkout. Physical prizes require staff fulfilment; do not promise instant delivery from a winning animation.

### 3.7 Rewards: graduation and history

Eligible customers can make a one-time graduation bonus claim under the configured minimum academic-level rule. Rewards also surfaces histories for points-related activity, unlocking, redemptions and spin outcomes, helping customers understand what happened to their benefits.

**Retention role:** Celebrates a meaningful life stage and reinforces confidence that progress is recorded.

### 3.8 Tiers: Ember → Flame → Blaze → Holy

These are the current tier names used by the implementation. Tier information appears across HP education, profile/dashboard and loyalty surfaces; the event ticket-tier page is a different concept.

Current built-in perk defaults are:

| Tier | Food HP multiplier | Birthday HP | Monthly loyalty benefit |
|---|---:|---:|---|
| Ember | 1.00× | 100 | No recurring side/delivery/HP perk by default. |
| Flame | 1.08× | 150 | 50 HP monthly bonus. |
| Blaze | 1.15× | 200 | 1 free-side credit monthly. |
| Holy | 1.25× | 250 | 1 free-side credit monthly and a monthly free-delivery benefit. |

**These are code defaults, not confirmed live promises.** Settings can override perks, tier thresholds come from programme data, and monthly issuance requires functioning scheduled work. Delivery caps and eligibility still apply. Tier defaults do not include a monthly spin allowance; leaderboard and manual spin grants are separate.

**Retention role:** Longer-term status gives customers something to maintain beyond a single coupon. A grace-period flow provides an opportunity to retain status rather than surprising customers with an immediate downgrade.

### 3.9 Streak — `/streak`

There are two independent habits:

**Check-in/login streak**

- Uses Monday–Sunday weeks.
- A daily check-in records attendance; it does not itself pay daily HP.
- Completed weeks earn Pending HP, with configurable escalating weekly rewards.
- Built-in weekly examples are 25, 40, 60 and 80 HP for successive weeks, with the final level continuing thereafter.
- Up to the permitted missed-day tolerance can be remedied by qualifying activity on the missed day itself, such as a food order or qualifying wallet top-up. It is not a blanket retroactive purchase-to-repair promise.

**Food-order streak**

- Tracks at least one delivered food order per calendar week.
- Resets when a required week is missed.
- Qualifying streak milestones award Active HP according to the programme’s configured reward schedule.

**Retention role:** Check-ins build familiarity; weekly delivered-order goals link that familiarity to repeat purchasing.

**Design requirement:** Make “checked in,” “week completed,” “Pending awarded” and “Active order-streak reward” distinct states.

### 3.10 Referrals — `/referrals`

Customers can copy/share their referral link or code, inspect referred friends, see progress and HP earned, and discover referral milestones. The core referral award is tied to the referred person completing their first qualifying order, not merely opening a link or registering.

**Retention role:** Existing customers bring new customers in; completion-based rewards encourage an actual first purchase rather than empty signups.

**Messaging direction:** “Invite a friend. Earn when they complete their first qualifying order.” Confirm current reward amount and eligibility before adding numbers.

### 3.11 Squads — `/squads`

Customers can create a named squad with member emails, view squads they belong to, inspect a squad’s roster, member HP contribution and order history, and use a saved squad during ordering. Organisers can manage the roster. The order’s selected members can be adjusted separately from the reusable roster.

**What a squad order actually does**

- One organiser places the order and pays through the usual checkout methods.
- Qualifying order HP is split among the organiser and selected distinct members.
- Registered members can receive their allocated shares.
- Unregistered invitees can have shares held against their email for later account claiming, with invitation/referral attribution support.
- A configured organiser bonus can apply when there is at least one other registered participant.
- Squad ranking provides group-level recognition.

**Retention role:** Turns one person’s meal purchase into shared participation and creates a practical recruitment loop for friends who have not registered.

**Do not confuse this with:** A collaborative cart where everyone adds items from separate devices, automatic collection of each member’s cash contribution, or independent split billing. Those are not established by the squad implementation. Wallet/card split payment is one buyer combining two payment sources, not friends splitting a bill.

### 3.12 Leaderboard — `/leaderboard`

Customers can view rankings for supported weekly, monthly and all-time periods, see their own rank and access squad ranking. The ranking experience provides a public comparison point for earned activity; historical snapshots preserve completed periods.

The monthly job includes recognition and prize issuance when the relevant features are enabled:

| Monthly placement | Implemented award pattern |
|---|---|
| #1 and #2 | 2 free-side credits each, plus 1 exclusive spin. |
| #3 | 1 free-side credit, plus 1 exclusive spin. |
| #4–#10 | 1 exclusive spin each. |

The spin and leaderboard-prize switches are separate, and issuance depends on scheduled work. Confirm actual awards before publicising a particular competition.

**Retention role:** Creates a recurring competition and a fresh monthly finish line. Squad rankings can turn personal motivation into group motivation.

### 3.13 Hall of Fame — `/hall-of-fame`

Provides lasting recognition beyond the current leaderboard. The implementation includes historical monthly #1 recognition and a separate induction path after three top-four monthly finishes. Induction/share-card data and staff reward-fulfilment records support the celebration journey.

**Retention role:** Encourages sustained participation across months rather than one short promotional burst.

**Boundary:** Public display and historical recognition are not proof that a physical recognition box has been dispatched. Staff fulfilment remains separate.

### 3.14 HP gifting / transfers

Available through the supported loyalty UI rather than a dedicated main page. Eligible customers can send Active HP to another user on their own campus. Minimum transfer and delivered-order eligibility rules apply; defaults include a 10 HP transfer minimum and three delivered orders for the sender.

**Retention role:** Makes points socially useful and gives experienced customers a way to introduce friends to the programme.

**Boundary:** This is not a cash transfer, cross-campus remittance service or unrestricted new-account giveaway.

---

## 4. Customer pages: events, marketplace and support

### 4.1 Events — `/events`

Customers can browse published upcoming events relevant to the campus, open event details, revisit their tickets and access catering/partnership enquiry options. Staff can prepare unpublished events before exposing them publicly.

**Retention role:** Gives people a reason to visit between meal purchases and positions the brand within campus life.

### 4.2 Event detail — `/events/:id`

Customers can inspect event information and available ticket options, register and make supported payment choices. Registered users can use wallet/card/split cash payment and eligible HP-assisted ticket discounts; guests use full-price card payment without HP/wallet benefits. Promo support also exists in registration.

Customers can obtain their ticket and download a PDF containing the ticket QR. Event check-in supports ticket/QR-based attendance and qualifying HP awards.

**Important:** HP-assisted registration is **HP plus discounted cash**, not an unrestricted HP-only ticket purchase. Event admission, attendance and HP are linked features, but full financial/check-in recovery and concurrency coverage remains unfinished in the audit.

### 4.3 Event ticket-tier detail — `/events/tiers/:tierId`

Explains an event’s particular admission option and its price/benefits in the event context. Staff can create multiple ticket tiers with names, descriptions, capacity, cash pricing and optional HP-assisted pricing. Tiers with sales cannot simply be deleted.

**Retention role:** Makes loyalty useful outside food, while ticket options serve different audience needs.

**Naming caution:** “Ticket tier” means an admission category such as Regular or VIP, not Ember/Flame/Blaze/Holy loyalty status.

### 4.4 Catering enquiry and status — `/catering/:requestId`

Customers can submit a catering/event partnership request with the supported event and guest information, then use their protected receipt/status journey to see the request state and a quote when provided. Staff can review, accept/reject, assign and add internal notes. The customer receipt deliberately excludes internal staff notes and assignment information.

**Retention role:** Converts an individual customer relationship into a possible group occasion, organisation relationship or larger order.

**Boundary:** An enquiry receipt is not an automatically confirmed booking, paid catering contract or guaranteed event slot.

### 4.5 Marketplace — `/marketplace`

Customers can browse active listings and availability, inspect a listing and revisit purchases. Logged-in users can submit a vendor/listing request for staff review rather than directly publishing an uncontrolled listing.

**Retention role:** Provides additional reasons to return and additional uses for ecosystem benefits beyond meals.

### 4.6 Marketplace detail and purchase — `/marketplace/:id`

Supports listing information, cash pricing, eligible HP-assisted purchase pricing, inventory/code availability and supported wallet/card/split payment paths. Digital access-code stock can be delivered through the purchase flow. Customers can report a code problem; staff can review and replace, refund or reject the report.

**Important:** The UI’s HP option is a discount opt-in with a cash payment path—not evidence of a universal HP-only purchase. Marketplace purchase/refund/report races remain an open audit area. Some older educational copy says Marketplace is “coming soon” even though purchasing code exists. Confirm the actual release switch and deployed behaviour before advertising it as available.

### 4.7 Notifications — `/notifications`

Customers can see their in-app notification history and mark individual or all messages as read. Messages can link back to the specific order, reward or other relevant action.

**Retention role:** Creates a persistent place to find benefit reminders instead of relying only on a fleeting push alert.

### 4.8 Notification Preferences — `/notification-preferences`

Customers can manage supported notification categories/channels and browser push subscription. Installation and push prompts can connect to configured bonus eligibility.

**Retention role:** Relevant, consent-aware communication is more sustainable than sending every customer every offer.

**Boundary:** Notification storage, permission to receive push and successful delivery to a real device are three different things. Browser/device support and provider setup matter.

### 4.9 FAQ — `/faq`

Provides answers about ordering and the programme. This reduces friction and support demand, but published explanations should be checked against actual current rules when campaigns change.

### 4.10 Contact — `/contact`

Presents support/contact options, including configured WhatsApp support where enabled. Contact links are a support channel, not proof of automatic WhatsApp order handling or campaign broadcasts.

### 4.11 Our Story — `/our-story`

Provides brand context and a relationship-building narrative. Its business purpose is trust and affinity rather than a separate transaction capability.

### 4.12 Terms and Privacy — `/terms`

Provides the policy context for the service, account data and programme. Campaign terms must remain consistent with actual cancellation, wallet, eligibility, notification and benefit-expiry behaviour.

### 4.13 Newsletter unsubscribe — `/newsletter/unsubscribe`

Allows recipients to opt out through the signed unsubscribe journey. Newsletter subscription is separate from a customer’s transactional order updates and in-app inbox.

### 4.14 Missing-page experience

Unknown routes have a not-found page rather than being treated as a valid product journey. Marketing links should always target an existing page and, where needed, account/campus selection should be part of the expected journey.

---

## 5. Admin: every main section and its business purpose

The admin area is available at `/admin`. Staff access is role-based. Campus administrators generally operate within their campus; super administrators have broader authority. A visible control does not mean every staff member can edit it. In particular, feature switches, sensitive global settings, some programme controls and manual job execution have elevated permission checks.

### 5.1 Dashboard

**Staff can:** Inspect today’s order pipeline, revenue snapshot and delivery-batch activity in a central overview.

**Business role:** Spots service problems early. Reliability is part of retention: loyalty messages cannot compensate for unattended orders.

### 5.2 Analytics

**Staff can inspect:** Sales/revenue, order volume, average order value, payment mix, order timing, add-on uptake, delivery locations, squad orders, academic/demographic segments, engagement, referrals, HP issuance/spending, item performance, order sources, academic-period performance, gift activity, cart recovery, marketplace activity, active users and cohort/second-order retention. Supported exports provide CSV data. Brand-partnership request records support staff record-keeping.

**Business role:** Gives marketing evidence for what people buy, when they buy and whether new customers return.

**Boundary:** A report is not a guaranteed attribution model, ad-platform integration or permission to share personal customer data with partners. Interpret metric definitions before comparing reports.

### 5.3 HP Economics

**Staff can:** Inspect programme-cost and tier/redemption economics views.

**Business role:** Helps evaluate whether loyalty value is affordable, rather than selecting promotional point amounts without considering cost.

**Boundary:** Internal valuation is not a public HP-to-cash exchange or customer cash-out promise.

### 5.4 Menu Items, including category management

**Staff can:** Create/edit dishes, descriptions, photos, prices and categories; change campus availability; bulk-update availability; archive items; manage daily item limits and kitchen capacity. Category controls may appear within the menu workflow rather than as their own main sidebar section.

**Business role:** Supports seasonal launches, targeted product discovery and honest sold-out/capacity communication.

### 5.5 Addons & Variations

**Staff can:** Manage extras and item option groups, including names, pricing, required selections and allowed choice counts where supported.

**Business role:** Personalisation, upselling and clearer expectations about what arrives.

### 5.6 HP & Multipliers

**Staff can:** View HP reports, customer point history and unclaimed squad HP; grant or expire HP under permissions; perform controlled bulk grants; manage supported food/item earning rates and multipliers. The per-item controls include ½×, 1× and 2×. Broader HP multiplier settings can support an earning campaign; raising a supported global boost can trigger an announcement.

**Business role:** Directs demand, rewards selected customers and supports recovery/recognition programmes.

**Boundary:** Bulk grants are not the same as automated personalised offers. Full boost stacking remains an audit area; base copy on the actual quote rather than multiplying every advertised boost yourself.

### 5.7 Rewards

**Staff can:** Create/edit/deactivate rewards, set HP cost and stock, maintain imagery and fulfilment-related details, inspect redemption records and fulfil or reject requests. The flash-sale creator selects a reward, time window, limited slots and HP discount.

**Business role:** Controls the destination of loyalty earning and the urgency of limited drops.

**Marketing handoff:** Supply the exact reward, stock/slot count, HP price, eligibility, opening/closing time and fulfilment promise—not just a poster headline.

### 5.8 Free Credits

**Staff can:** Maintain the eligible free-side catalogue and manually grant credits using the supported credit workflow. Credits track remaining use and validity.

**Business role:** A tangible return incentive for recognition, service recovery or programme benefits.

### 5.9 Exclusive Spin

**Staff can:** Manage the prize pool and its weighted likelihoods, actual prize effects and active state; grant spins with validity/reason; review physical-prize fulfilment records.

**Business role:** Adds controlled surprise to a loyalty/recognition campaign.

**Boundary:** Do not communicate equal odds when weights differ, or say every winner receives the same class of prize.

### 5.10 Challenges

**Staff can:** Create/edit/deactivate supported weekly/monthly challenges and one-time badges; set titles, descriptions, targets, HP awards, icons and relevant social links; manually grant eligible recognition milestones.

**Business role:** Builds a repeatable activity calendar around real behaviours such as delivered orders, reviews and referrals.

**Boundary:** It is a configured set of supported behaviours, not a no-code system for any imaginable external task.

### 5.11 Orders

**Staff can:** Find and inspect orders, review status/history, advance permitted fulfilment states and issue supported refunds. Role and payment checks constrain which actions are allowed. Paid and unpaid orders must not be presented as equivalent.

**Business role:** Resolves customer problems and keeps the service promise connected to actual fulfilment.

**Refund caution:** Supported collected cash refunds credit the closed-loop wallet. Partial refunds and full closure differ. Guest refunds, later-stage cancellation/reversal policies and late provider payments after cancellation need special attention; never advertise automatic refunds to the original card.

### 5.12 Wallet

**Staff can:** Inspect wallet transactions, funding, payments and refunds within their authorised scope.

**Business role:** Helps explain missing/returned funds and resolve payment questions using a ledger rather than guesses.

### 5.13 Events

**Staff can:** Create and edit events, control publication, maintain event imagery, create/edit admission tiers and capacity/pricing, inspect registrants and tier sales, export registrants, generate/regenerate check-in QR tokens and request registrant delivery to the host by email. Ticket tiers with sales have deletion restrictions.

**Business role:** Supports community occasions and gives HP another relevant benefit/use case.

**Boundaries:** Host email delivery needs a working email service. Regenerating an event check-in token invalidates the old one. Do not distribute an old poster QR after regeneration. Funded event cancellation/refund and fully atomic admission/HP handling remain open audit items.

### 5.14 Catering

**Staff can:** Review incoming catering/partnership enquiries, update status, record quotes/notes and manage assignment through supported controls.

**Business role:** Converts consumer engagement into group and institutional opportunities. Customer-facing status keeps the enquiry from feeling lost.

### 5.15 Marketplace

**Staff can:** Create/edit/manage listings, review vendor requests, approve/reject submissions, control availability, upload access-code inventory, inspect purchases, manage permitted completion/refund/cancellation actions and resolve reported codes by replacement/refund/rejection.

**Business role:** Extends the ecosystem’s utility and manages trust when a digital product fails.

**Boundary:** This is not evidence of a fully self-service vendor payout platform. Sold listings/history have deletion safeguards; financial/report concurrency still requires further audit.

### 5.16 Promo Codes

**Staff can:** Create/edit percentage or fixed-naira discounts, set minimum order value, start/end dates, overall usage limits and per-customer limits, activate/deactivate codes and inspect actual usage/discount amounts.

**Business role:** Acquisition offers, time-limited conversion and controlled repeat-purchase incentives.

**Design requirement:** State the cash discount, minimum spend, expiry and use limit. A visible promo banner does not bypass backend validation.

### 5.17 Abandoned Carts

**Staff can:** Inspect abandoned carts and recovery information and send supported cart nudges. A scheduled scan also supports cart detection/reminders.

**Business role:** Recovers existing purchase intent rather than paying to create new intent from scratch.

**Boundary:** A nudge is not an automatically granted coupon unless a real promo has separately been created and included.

### 5.18 Reviews

**Staff can:** Read and filter customer reviews, inspect overall and kitchen/rider ratings and use feedback to identify service issues.

**Business role:** Feedback closes the service loop and provides evidence for product/operations improvements.

**Important gap:** One-click “promote this review to the homepage” is not a supported current action. The frontend explicitly removed the button because its backend route does not exist. Homepage testimonials can be maintained separately through storefront content; do not promise automatic review promotion.

### 5.19 Users

**Staff can:** Search/view customer and staff records, inspect order/HP/wallet history and use permitted role/activation controls. Privileged role changes remain subject to access rules.

**Business role:** Enables support, staff administration and investigation of suspected programme abuse.

### 5.20 Delivery, including riders and delivery-area controls

**Staff can:** Manage supported zones, hostels, gates, fees, campus centre/coverage and delivery windows; create/manage delivery batches and rider assignments; inspect rider availability/location; set batch rider pay; inspect earned/paid/outstanding totals and record batches as paid or unpaid.

Ordering windows and delivery windows are distinct operational controls: one determines when orders can be admitted, the other structures fulfilment.

**Business role:** Makes geographic campaign promises deliverable and protects customer confidence through reliable operations.

**Boundary:** Marking a rider as paid records an external payment; the site does not itself send rider wages. Rider pay is batch-based in the implemented workflow, not a public per-order earnings promise.

### 5.21 Order Locks

**Staff can:** Inspect customer lock records and manage supported programme settings under the relevant permission level.

Customers commit to a future date within the supported seven-day window and choose a configured discount or HP incentive. Only one active lock is allowed; the supported reschedule allowance is once. Reminders and expiry handling support the commitment, and qualifying checkout/delivery applies the relevant benefit.

**Business role:** Creates a specific future occasion to order.

**Boundary:** An order lock is not already a paid or prepared scheduled order, and “price lock” should not imply every future menu price is frozen. The implemented incentive is the configured discount/HP benefit.

### 5.22 Store / Stock

**Staff can:** Create ingredient/stock records, use measurement units, log purchases and consumption, record waste/corrections and inspect stock ledgers and low-stock states.

**Business role:** Reduces avoidable sell-outs and supports cost discipline.

**Boundary:** Stock logging does not establish automatic recipe-based deduction for every menu sale. Do not describe it as a complete automatic procurement system.

### 5.23 Campaigns

**Staff can:** Compose notification blasts, select supported channels, target by supported role/tier audience controls, preview recipient counts, send immediately or schedule, inspect campaign history/details and use supported cancel/retry actions.

**Business role:** Connects the right audience to a relevant offer or next action.

**Boundary:** The visible audience builder is not evidence of arbitrary behavioural segmentation such as “everyone who bought rice twice but never attended an event.” Verify supported filters before briefing a campaign. Actual email/push arrival requires working external delivery and customer consent/preferences.

### 5.24 Leaderboard

**Staff can:** Inspect rankings and supported monthly prize, Hall of Fame and fulfilment records; mark relevant physical/recognition rewards fulfilled and retain supported notes.

**Business role:** Turns competitive recognition into an operationally tracked promise.

**Boundary:** Marking a record fulfilled does not physically dispatch an item. Monthly ranking jobs also need to run successfully before awards are assumed issued.

### 5.25 Campuses

**Staff can:** Create/edit campus configuration and active state under the appropriate role; maintain campus information relevant to local availability and delivery.

**Business role:** Allows local expansion and campus-specific communication without assuming all locations share the same offer.

### 5.26 Departments and academic levels

**Staff can:** Maintain supported faculty/department and academic-level reference data, including deactivation/restoration where supported.

**Business role:** Supports relevant onboarding, graduation eligibility and academic/department reporting. Inactive reference options can be hidden without erasing existing customer history.

### 5.27 Storefront, banners, early supporters and newsletter

**Staff can:** Maintain homepage sections and their copy/images/links/order/visibility; create scheduled banners and carousel content; manage early-supporter profiles/photos; maintain configured testimonial content; inspect newsletter subscribers; queue newsletters, send a test to the calling administrator, inspect delivery counts and cancel queued/sending campaigns.

**Business role:** Gives marketing a route from campaign idea to an on-site landing experience and subscriber communication.

**Boundaries:** Supported content types constrain what the existing homepage can render. Newsletter email is a separate queue/consent journey from in-app notification blasts. Cancelling a campaign does not recall already delivered emails. Image upload and real email delivery need their provider configurations.

### 5.28 Onboarding

**Staff can:** Inspect first-order gift records, update supported gift statuses and, with elevated permissions, manage the welcome-gift settings, gift item and launch end date.

**Business role:** Adds a memorable first-purchase incentive and helps convert newcomers into returning customers.

**Important:** The first-order physical gift is awarded when the qualifying first order reaches **delivered**, only if the offer is enabled and within its launch window. It is not guaranteed merely by registration, payment initiation or an order-created message.

### 5.29 Feature Flags

**Staff can:** Inspect release switches; super administrators can create/update/toggle them. The current administrative switch model is global, even though other settings and services may evaluate campus context.

**Business role:** Allows controlled rollout or withdrawal of a capability.

**Boundary:** Do not infer that a feature is live everywhere because its page and backend exist. Confirm the deployed switch before launching creative.

### 5.30 Settings, including operating hours and delivery email settings

**Staff can:** Inspect/manage permitted programme and operational settings. Elevated controls cover sensitive values such as programme rates, perk configuration and service integrations. Operating hours can have weekday schedules and date-specific overrides, such as holiday closures.

**Business role:** Aligns the customer promise with current service capacity and programme policy.

**Marketing requirement:** Treat reward amounts, limits, expiry periods and opening hours as current campaign inputs, not permanent values copied once into artwork.

### 5.31 Academic Calendar

**Staff can:** Maintain campus academic periods such as semesters, exams, breaks and holidays, with active dates and current-period information.

**Business role:** Supports relevant planning and comparison of demand across campus seasons.

**Boundary:** A calendar entry does not by itself launch a discount or personalised campaign.

### 5.32 Webhook Events

**Staff can:** Inspect integration event logs, statuses and failures exposed in the admin view.

**Business role:** Helps operations investigate payment/fulfilment discrepancies that would otherwise become customer trust issues.

**Boundary:** Viewing an event is not proof every external side effect completed; durable recovery still has known gaps.

### 5.33 System

**Staff can:** Inspect audit history and scheduled-job status; super administrators can manually trigger supported jobs.

**Business role:** Helps establish whether automated loyalty and messaging work actually ran.

**Boundary:** A job listed in the interface is not proof that the worker is healthy or every award/message completed exactly once.

### 5.34 Shared admin utilities

Global search helps staff find records and sections. Campus selection, role gates, image upload/URL fallback, error/retry states and common editors support administration rather than representing separate customer offers. Image upload depends on the configured media service.

---

## 6. Kitchen and rider pages

### Kitchen — `/kitchen`

Kitchen staff can inspect the live preparation queue and scheduled orders, review delivery-window/batch summaries, advance permitted order/batch states, view operational metrics and use the limited kitchen settings/catering controls exposed to their role.

**Retention connection:** Faster, clearer execution supports the food promise and makes repeat ordering sensible. Loyalty points are awarded on real fulfilment, not simply to make a dashboard look active.

**Boundary:** Bulk kitchen/rider flows and some later-stage reward interactions remain audit work; do not describe every possible operational shortcut as fully verified.

### Rider — `/rider`

Riders can view assigned work and batch details, mark pickup, record delivery or attempted delivery, toggle availability, send location updates and inspect delivery history, performance and batch earnings. Protected customer call links support contact for live assigned orders. The payload does not simply expose all customer phone numbers to every rider.

**Retention connection:** Delivery status and controlled contact reduce missed handovers and customer uncertainty.

**Boundary:** Attempted delivery is different from completed delivery. Rider earnings displays and paid markers are not an automated banking payout service.

---

## 7. Automated retention journeys

These are implemented background/service behaviours, not separate pages. They require working scheduling and, for outward communication, real delivery services. The repository’s wider audit does not certify every interrupted/retried journey.

| Journey | Implemented behaviour | Retention purpose / caution |
|---|---|---|
| First delivered order | Food HP, configured welcome bonus, referral completion and eligible first-order gift hooks. | Makes the first successful experience rewarding; keep each award’s conditions separate. |
| Delivered food order | Food HP, some Pending unlocking, eligible squad distribution, streak/milestone hooks and review-related prompts. | Links everyday buying to progress. Full reward stacking/recovery remains an audit area. |
| Post-delivery follow-up | Satisfaction prompt around two hours after delivery and re-engagement prompt around a day later. | Encourages feedback and another visit. These are approximate job windows, not guaranteed delivery timestamps. |
| Abandoned cart | Detects eligible abandoned carts and supports reminders/recovery tracking. | Brings customers back to unfinished intent. |
| Weekly/monthly recognition | Archives ranking periods and performs supported awards/recognition. | Creates fresh competition and preserves achievement history. |
| Tier maintenance | Recalculates rolling 120-day earned HP and manages downgrade grace handling. | Encourages sustained activity without equating point spending with lost status. |
| Monthly tier perks | Issues configured monthly HP/side/delivery perks. | Gives a recurring reason to retain status and return. |
| Birthday | Issues configured tier-related birthday HP; reporting supports staff visibility. | Creates a personal recognition moment. Real date data and job execution matter. |
| Membership anniversary | Evaluates configured membership-age/anniversary awards. | Recognises relationship longevity. Confirm the actual configured milestones. |
| Inactivity win-back | Default reminder milestones at 70, 95 and 118 inactivity days. | Encourages return before inactivity decay. These defaults are not a promised live campaign schedule. |
| Inactivity decay | Default rule starts after 120 inactive days, with a configured monthly decay rate, currently 10% by default. | Creates an activity-maintenance rule; communicate transparently, not as a surprise penalty. |
| Order-lock follow-up | Reminders before the locked date and expiry of unused locks. | Turns future intent into a return occasion. |
| Scheduled orders | Promotes eligible scheduled orders into the operational flow. | Supports planned purchases; not a recurring subscription service. |
| Pending squad claiming | Registration/service sweeps connect eligible held shares to newly registered members. | Completes the invitation-to-account value loop. Auxiliary recovery still needs audit. |
| Scheduled campaigns/newsletters | Processes queued sends and supported retries/cancellation. | Supports a communications calendar. Queueing does not prove receipt. |

---

## 8. Campaign and design planning guide

### 8.1 Practical campaign map

These are ways to combine existing features—not claims that the site automatically assembles these campaigns.

| Objective | Existing feature combination | Suitable message direction | What must be confirmed |
|---|---|---|---|
| Convert first-time buyers | Menu + eligible welcome gift + referral attribution | “Make your first plate count.” | Delivery-based eligibility, gift availability and launch end date. |
| Encourage the second order | Pending HP + saved addresses + reorder | “Your next plate can unlock more of your points.” | Actual unlock rules and current menu/fees. |
| Increase weekly frequency | Order streak + weekly challenge | “Keep your weekly run going.” | Target, period boundary, reward and delivered-order requirement. |
| Grow social acquisition | Referral link + milestone + squad invitations | “Bring your people into the rewards.” | Completion-based award and squad share rules. |
| Drive a short burst of visits | Flash redemption + banner + targeted blast | “A limited HP reward drop is open.” | Slots, HP price, time window, switch and fulfilment. |
| Promote a dish | Item multiplier + menu placement | “More HP on this eligible plate.” | Live item boost and checkout preview. |
| Retain high-value customers | Tier progress + monthly perks | “Keep your status working for you.” | Actual perk configuration, grace rules and monthly issuance. |
| Build community | Events + ticket benefits + attendance HP | “Join the experience—and keep progressing.” | Ticket payment terms, capacity and check-in award rules. |
| Celebrate advocates | Monthly ranking + Hall of Fame + share card | “Earn your place in the campus story.” | Closed-period results and fulfilment readiness. |
| Recover intent | Saved/cart items + nudge | “Your picks are waiting.” | Current availability/prices; no invented stock reservation. |

### 8.2 What design needs to distinguish

1. Active HP, Pending HP and rolling tier progress are different measures.
2. A reserved reward, an applied reward and a released reward are different states.
3. A reward claimed is not necessarily a physical reward delivered.
4. A saved order can still require payment.
5. A scheduled order is not an order lock, and neither is a subscription.
6. A recurring challenge is not a lifetime badge.
7. Loyalty tiers are not event admission tiers.
8. A squad HP split is not multi-person payment collection.
9. A cash promo, HP earning boost and flash HP price are different offers.
10. “No data” and “could not load” should not look like a zero balance or a lost reward.

### 8.3 Minimum campaign handoff checklist

Before publishing a promotion, marketing, design and operations should agree on:

- The exact customer page and next action.
- Eligible campus, account state and audience.
- Required behaviour: registration, paid order, delivered order, check-in or claim.
- Whether the benefit is cash discount, Active HP, Pending HP, side credit, spin or physical item.
- Amount/rate, minimum spend, usage/stock limits and expiry.
- Whether the benefit is automatic, selected at checkout or manually fulfilled.
- Payment/refund and cancellation implications.
- The feature switch and live configuration.
- Notification consent/channel requirements.
- Who verifies issuance and handles failed claims or fulfilment.

### 8.4 What to measure

The available reports can help teams investigate first-to-second-order conversion, weekly ordering, average basket value, cart recovery, referral completion, squad participation, challenge/event engagement, redemption uptake, tier distribution and programme cost. Use consistent date/campus filters and confirm the report’s definition. Do not claim causal uplift from a campaign merely because activity rose during its dates.

---

## 9. Limitations and claims to avoid

### 9.1 Implemented does not always mean released or externally verified

The repository contains substantial customer/admin implementation and prior test evidence, but its ecosystem audit is explicitly unfinished. This review did not run a fresh live customer journey, connect production providers or change configuration. Existing provider blockers identify real Paystack, media upload, email and worker checks still required; later audit notes may supersede individual older blocker entries. Treat these records as warnings and evidence of scope, not a single blanket release verdict.

Before a public campaign, verify:

- Real card, split, guest and wallet-funding payments.
- Bank-transfer account provisioning and reconciliation where offered.
- Successful image upload and customer-visible media rendering.
- Real inbox/email/push delivery and functioning scheduled workers.
- End-to-end issuance, checkout use, delivery and cancellation of the advertised reward.

### 9.2 Open or partially verified families

Existing progress records call out remaining work in physical-prize delivery/attachment, full discount/HP/refund stacking, later-stage refund/reversal policy, some bulk kitchen/rider paths, auxiliary reward/job recovery, durable provider retries and unresolved guest-to-account checkout transitions. Event admission/check-in HP atomicity and funded cancellation/refunds remain open, as do marketplace financial/report races and parts of the historical security/role audit.

Selected checkout reward-choice, cancellation and lost-response recovery journeys have prior browser evidence in the repository. That narrower evidence does not certify every reward, provider or operational path.

### 9.3 Claims that should not be made from this code review

- “Every feature is live and fully audited.”
- “Every daily login immediately pays spendable HP.”
- “All Pending HP unlocks on your next order.”
- “Signing up always gives free HP.”
- “HP is withdrawable cash” or “all purchases can be paid entirely with HP.”
- “Friends each pay their own share automatically in a squad order.”
- “All flash offers are 50% for 24 hours.”
- “A banner automatically creates the offer it advertises.”
- “You can cancel at any point and receive an automatic card refund.”
- “Winning or redeeming a physical prize means it has already been delivered.”
- “The site verifies that every declared social follow happened.”
- “Admins can create any arbitrary external challenge or audience segment.”
- “Reviews can be promoted to testimonials in one click.”
- “Delivery always includes a live customer rider map.”
- “The site automatically pays riders or vendors to their bank accounts.”
- “Order locks freeze every menu price” or “scheduled orders are recurring subscriptions.”

---

## 10. Source and coverage reference

The main document is deliberately non-technical. These references let internal teams trace statements without turning the guide into an engineering specification. Current implementation takes precedence over older documentation or comments that describe superseded behaviour.

| Area reviewed | Main source locations |
|---|---|
| Complete page/route inventory | `holy-grills-frontend/src/App.tsx`; `holy-grills-frontend/src/pages/` |
| Admin section inventory | `holy-grills-frontend/src/lib/adminSections.ts`; `holy-grills-frontend/src/components/admin/` |
| Home, content and newsletter | `pages/Home.tsx`; `routes/storefront.py`; storefront/banner/newsletter admin components |
| Menu, cart, saved items and stock | `routes/menu.py`, `cart.py`, `saved_for_later.py`, `kitchen.py`; menu/cart/stock frontend components |
| Checkout, receipts, payment and cancellation | `pages/Checkout.tsx`, `OrderConfirmation.tsx`, `OrderDetail.tsx`; `routes/orders.py`; `services/order_service.py`, `order_payments.py`, `order_reward_summary.py` |
| Wallet and external payment handling | `routes/wallet.py`, `webhooks.py`; `services/wallet_service.py`, `payment_service.py` |
| HP, tier perks and earning rules | `routes/hp.py`; `services/hp_service.py`, `tier_service.py`, `food_hp_multiplier.py`; `app/config.py` |
| Badges/challenges/install/push | `routes/challenges.py`; `services/milestone_service.py`; rewards/streak/challenge components |
| Streaks and automated follow-up | `services/streak_service.py`; `tasks/scheduled.py` |
| Rewards, flash and side credits | `routes/rewards.py`, `free_sides.py`; `services/free_side_checkout.py`; `pages/Rewards.tsx`; `AdminRewards.tsx` |
| Spin prizes and delivery benefits | `routes/exclusive_spin.py`; `services/exclusive_spin_service.py`, `delivery_benefits.py`; spin/checkout admin and customer components |
| Referrals and squads | `routes/referrals.py`, `squads.py`; order squad actions; `services/squad_service.py`; referral/squad components |
| Rankings, monthly awards and Hall of Fame | `routes/leaderboard.py`, `admin_feature_flags.py`; `tasks/scheduled.py`; leaderboard/Hall of Fame pages |
| Events and catering | `routes/events.py`; event pages/components; `AdminEvents.tsx`, `AdminCatering.tsx` |
| Marketplace | `routes/marketplace.py`; marketplace pages/components and purchase modal |
| Accounts, academic data and graduation | `routes/auth.py`, `academic_levels.py`, `departments.py`, `graduation.py`; `services/auth_service.py`; account/profile pages |
| Messaging and campaigns | `routes/notifications.py`; notification services/templates/preferences; admin campaign and customer notification components |
| Operations, campuses, roles and settings | `routes/admin.py`, `admin_gifts.py`, `admin_feature_flags.py`, `campuses.py`, `delivery.py`, `riders.py`, `order_locks.py`, `academic_calendar.py`; admin and staff pages |
| Reports and programme economics | `routes/analytics.py`, `admin_economics.py`; economics services and analytics admin views |
| Known verification limits | [Ecosystem audit progress](ECOSYSTEM_AUDIT_PROGRESS.md), [provider checks](PROVIDER_VERIFICATION_BLOCKERS.md), [deferred items](DEFERRED_ITEMS.md), [Workstream B evidence matrix](WORKSTREAM_B_EVIDENCE_MATRIX.md) |
| Prior selected checkout browser evidence | [Checkout reward evidence](CHECKOUT_REWARD_BROWSER_EVIDENCE.json) |

Backend paths in this table are relative to `holy-grills-backend/app/`; frontend shorthand is relative to `holy-grills-frontend/src/`.

### Final positioning summary

**Holy Grills is a campus food experience with connected loyalty, social participation and community tools—not just an ordering menu with occasional coupons.**

The strongest messaging explains the connections: a delivered meal creates points and progress; useful activities create future value; friends participate through referrals and squads; recognition gives that participation status; and rewards/events provide reasons to keep returning. The operational pages, controls and reporting exist to make those promises manageable. Campaigns should only promise the parts that are enabled, configured and ready to fulfil.
