# Holy Grills email approval follow-up

The user confirmed the reviewing OneSignal login is **support@holygrills.online**. It forwards to an existing Gmail mailbox. Changing the local mailbox name (support/contact/hello) does not address a demonstrated domain mismatch. A paid mailbox is not inherently required for forwarding, but the forwarding address must reliably receive verification/invitation messages and be the actual signed-in OneSignal account, not merely an invited address.

Provider domain verification reported holygrills.online active, with SPF, DKIM, DMARC, tracking and ownership checks passed. Public MX currently points to Namecheap forwarding servers; SPF includes both OneSignal and Namecheap forwarding. These facts establish configuration checks, not sending approval. The rejection notice gives no specific private risk/reputation finding. Do not replace working MX records just to match cached provider MX expectations.

Earliest re-evaluation date in the supplied notice: **1 November 2026**. Re-submit from the verified domain login after that date. If the domain warning persists, retain its exact text and ask OneSignal to identify which account/domain association is failing.

Draft for the owner to submit to OneSignal support (not sent):

> Our Holy Grills App email-sending re-evaluation was declined, with the next review date shown as 1 November 2026. App ID: 471bd695-2342-4521-aa0f-8c93d7ce805f. The sender domain is holygrills.online, and the review was submitted while logged in as support@holygrills.online. This address receives mail through Namecheap forwarding. The domain is active and the provider reports SPF, DKIM, DMARC, tracking and ownership checks passed. When inviting the same domain address, we saw a domain-association warning. Please identify the exact missing account/domain association or approval requirement, and whether any forwarding-mailbox restriction applies. We want to correct the specific issue before submitting again.

Push is a separate channel. Admin notifications and automatic order events use the backend and OneSignal delivery API; the OneSignal dashboard is also available for independent manual campaigns. Existing app email routing can use Resend separately, and a successful Resend send does not establish OneSignal email approval.

Google setup still required: restricted `VITE_GOOGLE_MAPS_API_KEY` for Maps JavaScript API and Places API (New), plus billing enabled. Google uses usage-based charges and SKU-specific free allowances; custom styling is not the rule that makes usage free. Set quotas to control requests; budget alerts alone do not impose a spending cap. The implementation loads a map only when needed, debounces Places search and requests minimal place fields. Live provider testing remains required after key deployment.

Google reviews require the owner's Google Business Profile Place ID in `VITE_GOOGLE_BUSINESS_PLACE_ID`. Customers submit reviews on Google themselves; the site offers a neutral voluntary handoff for every rating. Site reviews cannot automatically be exported as Google reviews.
