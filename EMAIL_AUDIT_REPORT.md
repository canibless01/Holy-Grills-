# Holy Grills Email Template Audit Report

**Date:** 2026-10-26  
**Auditor:** Arena.ai Agent  
**Scope:** All email templates, shared design, CTAs, dynamic content, and integration

---

## Executive Summary

This audit reviewed **16 hardcoded email templates** in `holy-grills-backend/app/utils/email.py`, **3 guest status emails** in `order_service.py`, **1 QR ticket email** in `email.py`, **1 newsletter builder** in `newsletter_service.py`, and **Supabase auth emails** (verification + password reset). The shared HTML layout `_build_html()` was also audited.

**Key findings:**
- Guest order confirmation displays claim token as plain text (no clickable tracking link)
- All templates append brand sign-off `— {app_tagline}` which duplicates the shared layout's footer sign-off
- Guest status emails use minimal HTML (no branding, no footer, no tracking link)
- QR ticket email uses separate minimal HTML (no shared layout)
- Newsletter uses separate minimal HTML (no shared layout)
- Dynamic content handling is solid but some templates have awkward fallbacks

---

## A. Findings by Template

### A.1 Hardcoded Templates (email.py)

#### 1. `order_confirmed`
- **Location:** `holy-grills-backend/app/utils/email.py:24-36`
- **Purpose:** Confirm order placement to registered users
- **Subject:** "Your {brand} order is confirmed!"
- **What works:** Clear order number, total, delivery window, simple structure
- **Issues:**
  - Appends `— {app_tagline}` which duplicates shared layout's "With love, The Holy Grills Team" sign-off
  - Says "Track your order in the app" but provides no link or button
  - No CTA button to view order
- **Recommendation:** Remove trailing sign-off (layout handles it). Add "Track Your Order" button linking to `/orders/{order_id}`

#### 2. `hp_earned`
- **Location:** `holy-grills-backend/app/utils/email.py:37-47`
- **Purpose:** Notify user of HP earned from order
- **Subject:** "You just earned {currency}!"
- **What works:** Shows earned amount, active/pending balance
- **Issues:**
  - Appends redundant sign-off
  - "Keep ordering to build your {currency} balance" is generic
  - No CTA to browse menu or view rewards
- **Recommendation:** Remove sign-off. Add "See What You Can Unlock" button linking to `/rewards`

#### 3. `tier_upgrade`
- **Location:** `holy-grills-backend/app/utils/email.py:48-59`
- **Purpose:** Celebrate tier level-up
- **Subject:** "You levelled up on {brand}!"
- **What works:** Exciting tone, lists new benefits
- **Issues:**
  - `d.get('perks', '')` may render as empty string if perks not provided
  - "Keep earning to maintain your status" feels slightly threatening
  - Redundant sign-off
- **Recommendation:** Remove sign-off. Soften closing to "Enjoy your new perks!" Add "View Your Perks" button

#### 4. `wallet_funded`
- **Location:** `holy-grills-backend/app/utils/email.py:60-70`
- **Purpose:** Confirm wallet top-up
- **Subject:** "Wallet funded successfully"
- **What works:** Clear amount and new balance
- **Issues:**
  - Subject is generic and not exciting for a funding event
  - Redundant sign-off
  - No CTA to order or browse
- **Recommendation:** Remove sign-off. Add "Treat Yourself" button linking to `/menu`

#### 5. `password_reset`
- **Location:** `holy-grills-backend/app/utils/email.py:71-82`
- **Purpose:** Password reset link
- **Subject:** "Reset your {brand} password"
- **What works:** Clear instructions, expiry warning, security note
- **Issues:**
  - Link displayed as plain text URL (not a button)
  - Redundant sign-off
- **Recommendation:** Convert link to "Reset Password" button. Remove sign-off

#### 6. `birthday_bonus`
- **Location:** `holy-grills-backend/app/utils/email.py:83-93`
- **Purpose:** Birthday HP gift
- **Subject:** "Happy Birthday from {brand}! 🎂"
- **What works:** Warm tone, clear gift amount, encouraging CTA
- **Issues:**
  - Redundant sign-off
  - "treat yourself on us" is good but no actual CTA button
- **Recommendation:** Remove sign-off. Add "Order Now" button

#### 7. `referral_completed`
- **Location:** `holy-grills-backend/app/utils/email.py:94-105`
- **Purpose:** Notify referrer that referral completed
- **Subject:** "Your referral earned you {currency}!"
- **What works:** Celebratory, clear reward amount
- **Issues:**
  - Redundant sign-off
  - "Spend it on your next order" is text, not a button
- **Recommendation:** Remove sign-off. Add "Order Now" button

#### 8. `abandoned_cart`
- **Location:** `holy-grills-backend/app/utils/email.py:106-117`
- **Purpose:** Recover abandoned cart
- **Subject:** "Your cart is waiting for you"
- **What works:** Urgency messaging, HP incentive
- **Issues:**
  - `d.get('items_summary', '')` may be empty if not provided
  - Redundant sign-off
  - No "Complete Order" button
- **Recommendation:** Remove sign-off. Add "Complete Your Order" button

#### 9. `reward_redeemed`
- **Location:** `holy-grills-backend/app/utils/email.py:118-129`
- **Purpose:** Confirm reward redemption
- **Subject:** "Reward redemption confirmed"
- **What works:** Clear reward name, HP spent, fulfillment time
- **Issues:**
  - Subject is generic
  - Redundant sign-off
  - No tracking link or status info
- **Recommendation:** Remove sign-off. Add "Track Your Reward" button if applicable

#### 10. `tier_grace_period`
- **Location:** `holy-grills-backend/app/utils/email.py:130-141`
- **Purpose:** Warn about tier downgrade risk
- **Subject:** "Your tier grace period has started"
- **What works:** Clear deadline, actionable
- **Issues:**
  - Tone is slightly alarming
  - Redundant sign-off
  - No CTA to order
- **Recommendation:** Remove sign-off. Add "Place an Order" button. Soften tone to "You've got this!"

#### 11. `tier_dropped`
- **Location:** `holy-grills-backend/app/utils/email.py:142-152`
- **Purpose:** Notify tier downgrade
- **Subject:** "Your tier has changed"
- **What works:** Encouraging to climb back
- **Issues:**
  - Subject is vague (could be upgrade or downgrade)
  - Redundant sign-off
  - "Keep ordering to climb back up" is text, not button
- **Recommendation:** Remove sign-off. Add "Start Climbing" button

#### 12. `hp_expired`
- **Location:** `holy-grills-backend/app/utils/email.py:153-164`
- **Purpose:** Notify HP decay
- **Subject:** "Some of your {currency} has expired"
- **What works:** Clear decay amount and reason
- **Issues:**
  - Tone is negative without recovery path
  - Redundant sign-off
  - "Place an order to protect your remaining balance" is text, not button
- **Recommendation:** Remove sign-off. Add "Order Now" button. Add "Your Current Balance: X HP" if available

#### 13. `monthly_birthday_report`
- **Location:** `holy-grills-backend/app/utils/email.py:165-182`
- **Purpose:** Admin digest of birthdays
- **Subject:** "🎂 Birthday Report — {month} ({count} users)"
- **What works:** Clear summary, actionable for admin
- **Issues:**
  - Redundant sign-off (admin email, less critical)
  - "You can use this list to send birthday wishes" is verbose
- **Recommendation:** Remove sign-off. Simplify to "Use this list for birthday outreach"

#### 14. `event_tickets_export`
- **Location:** `holy-grills-backend/app/utils/email.py:183-197`
- **Purpose:** Admin export of event registrants
- **Subject:** "Event Registrants — {event_title}"
- **What works:** Clear attendee count, table data
- **Issues:**
  - Redundant sign-off
  - `d.get('registrant_table', '')` may be empty
- **Recommendation:** Remove sign-off

#### 15. `event_ticket_qr`
- **Location:** `holy-grills-backend/app/utils/email.py:198-213`
- **Purpose:** Event ticket with QR code
- **Subject:** "🎟️ Your Ticket for {event_title}"
- **What works:** Clear event details, QR code
- **Issues:**
  - Uses separate HTML builder (not shared layout)
  - "Create an account to earn HP for this event!" feels tacked on
  - No CTA button
- **Recommendation:** Migrate to shared layout. Add "View Event Details" button if event page exists

#### 16. `squad_invite`
- **Location:** `holy-grills-backend/app/utils/email.py:214-227`
- **Purpose:** Invite to squad order
- **Subject:** "You've been invited to join a squad order on {app_name}!"
- **What works:** Clear organizer name, HP incentive
- **Issues:**
  - Link displayed as plain text URL
  - Redundant sign-off
  - No CTA button
- **Recommendation:** Remove sign-off. Convert link to "Join Squad" button

#### 17. `guest_order_confirmed`
- **Location:** `holy-grills-backend/app/utils/email.py:228-241`
- **Purpose:** Guest order confirmation
- **Subject:** "Guest Order Confirmed — {app_name}"
- **What works:** Clear order number
- **CRITICAL ISSUE:**
  - **Claim token displayed as plain text: `Claim token: {claim_token}`**
  - No clickable tracking link
  - Guest must manually copy token and navigate to tracking page
  - "Create an account or log in with this email to claim your order" is confusing (guest doesn't have account)
  - Redundant sign-off
- **Recommendation:** 
  - Remove "Create an account or log in" text (guest doesn't have account yet)
  - Add "Track Your Order" button linking to `/track-orders?order_number={order_number}&claim_token={claim_token}`
  - Show claim token as fallback in plain text below button
  - Remove sign-off
  - Change subject to "Your Order {order_number} is Confirmed!" (more personal)

---

### A.2 Guest Status Emails (order_service.py)

#### 18. `out_for_delivery` (Guest)
- **Location:** `holy-grills-backend/app/services/order_service.py:2066-2068`
- **Subject:** "Your order {order_number} is on its way"
- **Body:** "Good news - order {order_number} is out for delivery. Please keep your phone close so the rider can reach you."
- **What works:** Clear status, actionable (keep phone close)
- **Issues:**
  - Uses minimal HTML (no branding, no footer, no tracking link)
  - No support contact info
- **Recommendation:** Migrate to shared layout. Add "Contact Support" link. Add tracking link

#### 19. `delivered` (Guest)
- **Location:** `holy-grills-backend/app/services/order_service.py:2069-2070`
- **Subject:** "Your order {order_number} was delivered"
- **Body:** "Order {order_number} has been delivered. Enjoy your meal!"
- **What works:** Warm, concise
- **Issues:**
  - Minimal HTML
  - No feedback/review prompt
  - No "Order Again" CTA
- **Recommendation:** Migrate to shared layout. Add "Enjoy!" and "Order Again" button

#### 20. `delivery_attempted` (Guest)
- **Location:** `holy-grills-backend/app/services/order_service.py:2071-2072`
- **Subject:** "We could not deliver order {order_number}"
- **Body:** "Our rider tried to deliver order {order_number} but could not reach you. Please contact us so we can arrange another attempt."
- **What works:** Clear problem, actionable
- **Issues:**
  - Minimal HTML
  - "Please contact us" but no contact info
  - No tracking link
- **Recommendation:** Migrate to shared layout. Add "Contact Support" button with mailto link. Add tracking link

---

### A.3 QR Ticket Email (email.py)

#### 21. `event_ticket_qr` (send_qr_ticket_email)
- **Location:** `holy-grills-backend/app/utils/email.py:730-770`
- **Subject:** "🎟️ Your Ticket for {event_title}"
- **What works:** QR code embedded, event details clear
- **Issues:**
  - Uses separate minimal HTML (no shared layout)
  - "Create an account with {email} to earn HP" is pushy
  - No CTA button
  - No event page link
- **Recommendation:** Migrate to shared layout. Soften account creation prompt. Add "View Event" button if page exists

---

### A.4 Newsletter (newsletter_service.py)

#### 22. Newsletter
- **Location:** `holy-grills-backend/app/services/newsletter_service.py:80-95`
- **What works:** Unsubscribe link included, simple structure
- **Issues:**
  - Uses separate minimal HTML (no shared layout)
  - No branding
  - Tagline sign-off is minimal
- **Recommendation:** Consider migrating to shared layout for brand consistency. Keep unsubscribe link

---

### A.5 Supabase Auth Emails

#### 23. Email Verification
- **Triggered by:** `auth_service.py:453` via `db.auth_resend_email`
- **What works:** Handled by Supabase, secure
- **Issues:**
  - Uses Supabase default template (not branded)
  - No Holy Grills branding
- **Recommendation:** Configure Supabase auth email templates with Holy Grills branding. This is a Supabase dashboard configuration, not code change.

#### 24. Password Reset
- **Triggered by:** `auth_service.py:471` via `db.auth_reset_password`
- **What works:** Secure reset link
- **Issues:**
  - Uses Supabase default template (not branded)
  - No Holy Grills branding
- **Recommendation:** Configure Supabase auth email templates with Holy Grills branding

---

## B. Shared Design Recommendations

### B.1 Current Layout Analysis

The shared layout `_build_html()` (lines 254-485 in email.py) includes:
- ✅ Wordmark header with gradient divider
- ✅ Mobile-responsive (620px breakpoint)
- ✅ Dark mode support
- ✅ Greeting: "Hello {name} 👋"
- ✅ Body text area
- ✅ CTA button support (primary/secondary)
- ✅ Secondary section support
- ✅ Social links
- ✅ Sign-off: "With love, {tagline}"
- ✅ Footer: "Thank you for being part of our community!", support email, copyright

### B.2 Issues with Shared Layout

1. **Duplicate Sign-offs**
   - Shared layout includes "With love, {tagline}" in body
   - Templates also append "— {tagline}" at end of body text
   - **Result:** Email shows TWO sign-offs
   - **Fix:** Remove "— {tagline}" from all templates. Let layout handle sign-off.

2. **Duplicate "Thank you" Messages**
   - Footer says "Thank you for being part of our community!"
   - Templates don't repeat this, but it's redundant for transactional emails
   - **Recommendation:** Keep footer "thank you" for marketing/newsletter emails. For transactional emails (order confirmed, HP earned, etc.), consider removing or changing to "Need help? Contact support@holygrills.online"

3. **Greeting Redundancy**
   - Layout adds "Hello {name} 👋" automatically
   - Templates also start with "Hi {name},"
   - **Result:** Email shows TWO greetings
   - **Fix:** Remove "Hi {name}," from all templates. Let layout handle greeting.

4. **Missing CTA Button Styling**
   - CTA buttons work but lack hover state (email clients don't support CSS hover well)
   - **Recommendation:** Keep current styling (works well)

5. **Footer Contact Info**
   - Footer has support email but no phone or WhatsApp
   - **Recommendation:** Add WhatsApp link if available: "Chat with us on WhatsApp"

6. **Logo Sizing**
   - Wordmark is 180px max-width (good)
   - **Recommendation:** Keep as-is

7. **Mobile Responsiveness**
   - Good breakpoint at 620px
   - **Recommendation:** Test on iOS Mail and Gmail app (known issues with email clients)

8. **Dark Mode**
   - Supported via media query
   - **Recommendation:** Test dark mode rendering (some clients override colors)

---

### B.3 Shared Layout Improvements

1. **Remove Duplicate Greeting**
   - Layout already adds "Hello {name} 👋"
   - Remove "Hi {name}," from all templates

2. **Remove Duplicate Sign-off**
   - Layout already adds "With love, {tagline}"
   - Remove "— {tagline}" from all templates

3. **Add Tracking Link Support**
   - Add optional `tracking_url` parameter to layout
   - Render as secondary section or button

4. **Add Order Details Section**
   - Add optional `order_details` parameter
   - Render as styled table (order number, total, delivery window)

5. **Add Support Contact in Footer**
   - Add "Chat with us" or "Call us" link
   - Keep email as fallback

---

## C. Prioritized Recommendations

### HIGH PRIORITY (Broken/Missing Actions)

#### 1. Guest Order Claim Token → Clickable Link
- **Impact:** Critical — guests cannot track orders without manually copying token
- **Fix:** 
  - Add "Track Your Order" button to `guest_order_confirmed` template
  - Link to `/track-orders?order_number={order_number}&claim_token={claim_token}`
  - Show token as fallback: "Or copy this tracking code: {claim_token}"
  - Remove confusing "Create an account or log in" text
- **Files:** `email.py:228-241`, `OrderConfirmation.tsx` (verify claim_token param works)

#### 2. Guest Status Emails → Migrate to Shared Layout
- **Impact:** High — no branding, no support contact, no tracking link
- **Fix:**
  - Update `_send_guest_status_email` to use `_build_html` or `_build_rich_html`
  - Add "Track Your Order" button
  - Add "Contact Support" link
- **Files:** `order_service.py:2066-2086`

#### 3. Order Confirmed → Add Tracking Button
- **Impact:** High — users have no quick way to view order
- **Fix:**
  - Add `cta_buttons=[{"label": "Track Your Order", "url": f"/orders/{order_id}", "primary": True}]`
  - Remove "Track your order in the app" text
- **Files:** `email.py:24-36`

#### 4. Password Reset → Convert Link to Button
- **Impact:** High — plain text URL is not user-friendly
- **Fix:**
  - Add `cta_buttons=[{"label": "Reset Password", "url": reset_link, "primary": True}]`
  - Keep plain text URL as fallback below button
- **Files:** `email.py:71-82`

#### 5. Squad Invite → Convert Link to Button
- **Impact:** High — plain text URL is not user-friendly
- **Fix:**
  - Add `cta_buttons=[{"label": "Join Squad", "url": invite_link, "primary": True}]`
- **Files:** `email.py:214-227`

#### 6. Remove Duplicate Greetings and Sign-offs
- **Impact:** Medium — confusing and unprofessional
- **Fix:**
  - Remove "Hi {name}," from all templates (layout handles it)
  - Remove "— {tagline}" from all templates (layout handles it)
- **Files:** All templates in `email.py:24-241`

---

### MEDIUM PRIORITY (Messaging/Design Issues)

#### 7. Add CTA Buttons to Templates
- **Templates:** `hp_earned`, `tier_upgrade`, `wallet_funded`, `birthday_bonus`, `referral_completed`, `abandoned_cart`, `reward_redeemed`, `tier_grace_period`, `tier_dropped`, `hp_expired`
- **Fix:** Add contextual CTA buttons:
  - `hp_earned` → "See What You Can Unlock" → `/rewards`
  - `tier_upgrade` → "View Your Perks" → `/rewards`
  - `wallet_funded` → "Treat Yourself" → `/menu`
  - `birthday_bonus` → "Order Now" → `/menu`
  - `referral_completed` → "Order Now" → `/menu`
  - `abandoned_cart` → "Complete Your Order" → `/checkout`
  - `reward_redeemed` → "Track Your Reward" → `/rewards` (if tracking exists)
  - `tier_grace_period` → "Place an Order" → `/menu`
  - `tier_dropped` → "Start Climbing" → `/menu`
  - `hp_expired` → "Order Now" → `/menu`
- **Files:** `email.py`

#### 8. QR Ticket Email → Migrate to Shared Layout
- **Impact:** Medium — no branding
- **Fix:** Use `_build_html` with hero image or secondary section
- **Files:** `email.py:730-770`

#### 9. Newsletter → Migrate to Shared Layout
- **Impact:** Medium — no branding consistency
- **Fix:** Use `_build_html` with unsubscribe_url parameter
- **Files:** `newsletter_service.py:80-95`

#### 10. Supabase Auth Emails → Configure Branded Templates
- **Impact:** Medium — no Holy Grills branding
- **Fix:** Configure Supabase dashboard auth email templates
- **Files:** Supabase dashboard (not code)

#### 11. Improve Subject Lines
- **Issues:**
  - `wallet_funded`: "Wallet funded successfully" → "Your Wallet is Funded! 🎉"
  - `tier_dropped`: "Your tier has changed" → "Your Tier Status Updated"
  - `guest_order_confirmed`: "Guest Order Confirmed — {app_name}" → "Your Order {order_number} is Confirmed!"
  - `reward_redeemed`: "Reward redemption confirmed" → "Your Reward is Confirmed! 🎁"
- **Files:** `messages.py` (EMAIL_* constants)

#### 12. Soften Tone in Negative Emails
- **Templates:** `tier_grace_period`, `tier_dropped`, `hp_expired`
- **Fix:**
  - `tier_grace_period`: Add "You've got this!" before sign-off
  - `tier_dropped`: Change "Keep ordering to climb back up" to "Start earning to climb back — we're rooting for you!"
  - `hp_expired`: Add "Order now to protect your remaining balance"
- **Files:** `email.py`

---

### LOW PRIORITY (Minor Refinements)

#### 13. Add WhatsApp Link to Footer
- **Impact:** Low — nice-to-have
- **Fix:** Add "Chat with us on WhatsApp" link if available
- **Files:** `email.py` (footer section)

#### 14. Add Event Page Link to QR Ticket Email
- **Impact:** Low — nice-to-have
- **Fix:** Add "View Event Details" button if event page exists
- **Files:** `email.py:730-770`

#### 15. Improve Monthly Birthday Report Wording
- **Impact:** Low — admin email
- **Fix:** Simplify "You can use this list to send birthday wishes, create flyers, or DM them directly" to "Use this list for birthday outreach"
- **Files:** `email.py:165-182`

#### 16. Test Dark Mode Rendering
- **Impact:** Low — ensure dark mode works across clients
- **Fix:** Test on Gmail, Apple Mail, Outlook
- **Files:** None (testing only)

#### 17. Test Mobile Responsiveness
- **Impact:** Low — ensure mobile rendering works
- **Fix:** Test on iOS Mail, Gmail app, Android mail apps
- **Files:** None (testing only)

---

## D. Summary

### What Should Remain Unchanged

1. **Shared Layout Structure**
   - Wordmark header, gradient divider, footer structure — all work well
   - Mobile responsiveness and dark mode support — keep as-is
   - CTA button styling — works well

2. **Template Content That Works**
   - `birthday_bonus`: Warm, clear, good tone
   - `referral_completed`: Celebratory, clear reward
   - `order_confirmed` (body text): Clear order details
   - Guest status email body text: Clear and actionable

3. **Dynamic Content Handling**
   - Fallback values (`d.get('name', 'there')`) work well
   - Currency and brand placeholders work correctly
   - Order number formatting (uppercase, truncated) works

4. **Email Integration**
   - Resend + OneSignal quota failover works correctly
   - SPF/DKIM/DMARC already configured (per task instructions)
   - Admin template override system works

---

### What Should Be Improved

1. **Guest Order Tracking (HIGH)**
   - Convert claim token to clickable tracking link
   - This is the most critical fix

2. **Remove Duplicate Greetings/Sign-offs (HIGH)**
   - Templates and layout both add these
   - Causes confusion and looks unprofessional

3. **Add CTA Buttons (MEDIUM)**
   - Most templates have text CTAs but no buttons
   - Buttons improve click-through rates

4. **Migrate Guest Status Emails to Shared Layout (HIGH)**
   - Currently use minimal HTML
   - No branding, no support contact, no tracking link

5. **Migrate QR Ticket and Newsletter to Shared Layout (MEDIUM)**
   - Currently use minimal HTML
   - Inconsistent branding

6. **Configure Supabase Auth Emails (MEDIUM)**
   - Currently use Supabase default templates
   - No Holy Grills branding

---

### What Needs Further Investigation

1. **Frontend Route for Guest Tracking**
   - Need to verify `/track-orders` accepts `order_number` and `claim_token` query params
   - Check `TrackOrders.tsx` to see if it handles these params
   - If not, add support for `?order_number=X&claim_token=Y`

2. **Order Reward Summary**
   - Check if `/orders/{id}` shows reward summary for guest orders
   - May need to handle guest case differently

3. **Supabase Auth Email Configuration**
   - Need to verify if Supabase dashboard allows custom HTML templates
   - Check if templates can be configured via API or only dashboard

4. **Dark Mode Testing**
   - Need to test actual rendering in Gmail, Apple Mail, Outlook
   - May need to adjust colors for better contrast

5. **Mobile Testing**
   - Need to test on iOS Mail, Gmail app, Android mail apps
   - May need to adjust spacing or font sizes

---

### Recommended Order of Implementation

1. **Phase 1: Critical Fixes (Week 1)**
   - Add tracking link to `guest_order_confirmed` template
   - Verify frontend `/track-orders` route accepts query params
   - Remove duplicate greetings/sign-offs from all templates
   - Add CTA button to `order_confirmed` template

2. **Phase 2: Guest Email Migration (Week 2)**
   - Migrate guest status emails to shared layout
   - Add tracking links to guest status emails
   - Add support contact to guest status emails

3. **Phase 3: CTA Button Rollout (Week 3)**
   - Add CTA buttons to all templates (see list in C.7)
   - Convert plain text links to buttons (password reset, squad invite)
   - Test all CTAs work correctly

4. **Phase 4: Layout Migration (Week 4)**
   - Migrate QR ticket email to shared layout
   - Migrate newsletter to shared layout
   - Test rendering across email clients

5. **Phase 5: Supabase Auth Emails (Week 5)**
   - Configure branded auth email templates in Supabase dashboard
   - Test verification and password reset emails

6. **Phase 6: Polish & Testing (Week 6)**
   - Test dark mode rendering
   - Test mobile responsiveness
   - Improve subject lines
   - Soften tone in negative emails
   - Add WhatsApp link to footer (if available)

---

## Appendix: File Locations

### Email Templates
- `holy-grills-backend/app/utils/email.py` (lines 24-241) — hardcoded templates
- `holy-grills-backend/app/utils/email.py` (lines 254-485) — shared layout `_build_html()`
- `holy-grills-backend/app/utils/email.py` (lines 730-770) — QR ticket email

### Guest Status Emails
- `holy-grills-backend/app/services/order_service.py` (lines 2066-2086)

### Newsletter
- `holy-grills-backend/app/services/newsletter_service.py` (lines 80-95)

### Subject Lines
- `holy-grills-backend/app/messages.py` (lines 420-431)

### Frontend Routes
- `holy-grills-frontend/src/App.tsx` (line 97) — `/track-orders` route
- `holy-grills-frontend/src/pages/TrackOrders.tsx` — tracking page
- `holy-grills-frontend/src/pages/OrderConfirmation.tsx` — order confirmation page

### Backend Routes
- `holy-grills-backend/app/routes/orders.py` (line 265) — `/track` endpoint
- `holy-grills-backend/app/routes/orders.py` (line 643) — `/claim` endpoint

---

## Conclusion

The email system is functional but has several UX issues:
1. **Critical:** Guest order tracking is not user-friendly (plain text token)
2. **High:** Duplicate greetings/sign-offs cause confusion
3. **Medium:** Most templates lack CTA buttons
4. **Medium:** Guest status emails, QR ticket, and newsletter don't use shared layout

The recommended fixes will improve user experience, brand consistency, and click-through rates. The shared layout is solid and only needs minor adjustments (remove duplicate greeting/sign-off from templates).

**Next steps:** Implement Phase 1 (critical fixes) immediately, then proceed through phases 2-6 over 6 weeks.

---

**Report compiled by:** Arena.ai Agent  
**Date:** 2026-10-26  
**Status:** Complete (no code changes made, report only)
