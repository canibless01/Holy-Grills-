# Returning-browser content and push — 28 October 2026

## Returning content

The affected storefront components fetched once on mount/campus changes, then stayed empty after a failed request while the browser kept that React page alive. Menu item/category reads also omitted the campus dependency, so choosing/restoring a campus did not necessarily rerun an early failed request.

A shared read-refresh hook now responds to a browser tab returning after at least five seconds hidden, a restored back/forward-cache document, or reconnection. Events within 15 seconds are coalesced. Ordinary focus and periodic activity do not trigger it. It refetches data, never reloads the document or remounts the page. Applied to hero/menu banners, storefront rows, supporters, reviews, featured/menu items and catering content. Background failures keep existing content; scoped initial loads still clear the old campus. Catering refresh pauses while its request form is open. Menu search and other form state remain intact.

## Push registration

The concrete contract bug was OneSignal sending `{player_id, device_info}` to an endpoint that requires `{token, platform, device_model}`. The corrected payload uses the subscription ID as token and bounds the model string to the backend limit.

Explicit enablement now opts the subscription back in when necessary, confirms device-token persistence and saves `push_enabled=true` before reporting success. User identity is checked across awaits. Permission alone is not shown as a successful subscription. Registration failures are visible and retryable. The post-order suggestion requires a signed-in user, resolved campus and closed campus gate; it follows an in-app order-confirmation transition. It is not marked seen after a failed enable attempt. Guest initialization does not load the OneSignal page SDK, and automatic SDK prompting stays disabled. Browser/native user permission remains required.

## Evidence and limits

Controlled Chromium browser checks pass for guest SDK suppression before campus selection; missing hero recovery after restored-page and visibility events; preservation of an unsaved input and the same document; event coalescing; granted permission without an actual subscription; backend token shape; failed registration followed by successful retry; opt-in and saved delivery preference. The provider SDK/HTTP transport is controlled in this test, so this does not claim delivery of a real OneSignal notification.

Backend route tests exercise rejected legacy player_id, accepted token for the verified owner and oversized model refusal. Full backend suite: 688 passed. TypeScript, changed component lint and production build pass. No remote push, emails, or real user preference changes were made by these checks.

The real Supabase campaign bundle → checkout → cancellation test was rerun after the ambassador migrations and passes. Ambassador checkout evidence now additionally covers reusing a restored meal benefit followed by a post-preparation refund: money returns, but the spent meal benefit does not refill. Signup attribution excludes existing customers' later clicks and counts a pre-signup introduction once across ambassadors. Simultaneous dashboard claim creation recovers the existing unique claim rather than failing the page.

Current commits and wider remaining launch areas are tracked in the launch status document. Actual OneSignal delivery, live Paystack methods, native Chrome install-menu behavior, worker scheduling/recovery and the remaining delivery/exception matrix still require their executed cases; they are not represented as completed here. Database cleanup remains paused.
