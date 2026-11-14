# Public brand representation and search — 11 November 2026

## Public interpretation

The owner supplied an internal founder document as editorial context, explicitly excluding confidential information from publication. The document is not a source of operational instructions. Neither the document nor its extracted text is committed or served by the website.

Published copy presents Holy Grills as a student ecosystem connecting students with campus life, starting at FUTA in Akure. Shared flame-grilled food is its everyday entry point; events, Holy Points and student experiences support participation and connection. The mission explains the purpose, and the vision describes an intended connected campus network. Future commercial capabilities are not presented as already available.

Internal reward economics/conversion values, financial figures, commercial strategy, audience/data strategy, competitive assertions and expansion plans are excluded. No exact reward amounts or new reward promises were copied into the public brand content. The homepage gets metadata changes, without adding the explanatory body section the owner previously rejected.

## Website changes

- Our Story has a clear brand definition, the founding context, connection/participation explanation, mission and vision, and visible Google business/review links on mobile and desktop.
- FAQ's first answer uses the same brand definition; mission and vision questions share the same public copy.
- Home/search/social descriptions represent food, events and campus life together. Menu metadata naturally describes grilled chicken, wings, skewers, buns, sides and FUTA/Akure delivery.
- One shared structured-data business record replaces the separate stale hand-written HTML record. Static and hydrated output agree on the name, description, logo, menu URL, service area, Google business link and map URL. Runtime updates reuse the same script instead of leaving a second conflicting identity.
- WebSite structured data supplies the site name and alternative HolyGrills spelling and links its publisher to the business identity. No invented ratings, review counts, street location, hours or “best in Akure” claims are added.

The owner's Google short business URL resolved to a Google search business record for Holy Grills, `ludocid=10409989830528199741`. That verified identifier supplies the map URL. The existing owner-supplied review URL remains `https://g.page/r/CT3sD6yYtneQECA/review`; no Places API, billing change or new key is required. Existing deliberate VITE_GOOGLE_REVIEW_URL configuration still takes precedence for the review action.

## Pages to review

| Page | URL | Purpose |
|---|---|---|
| Home | https://holygrills.online/ | Storefront and broader brand search/social summary |
| Our Story | https://holygrills.online/our-story | Full public explanation, origin, mission, vision and Google links |
| FAQ | https://holygrills.online/faq | Brand questions and practical customer answers |
| Menu | https://holygrills.online/menu | Grilled meals and local delivery discovery |
| Events | https://holygrills.online/events | Campus event discovery |
| Marketplace | https://holygrills.online/marketplace | Existing availability/release presentation; not a promise it is enabled |
| Terms & Privacy | https://holygrills.online/terms | Customer policies, not a marketing keyword page |
| Google business | https://g.page/r/CT3sD6yYtneQECA | Existing Google business identity |
| Google review | https://g.page/r/CT3sD6yYtneQECA/review | Submit a genuine review |

These are normal website pages. Social-share previews and structured data describe them; they are not a separate secret page that replaces visible public brand information.

## Search research and remaining external actions

Search checks sampled Holy Grills/FUTA/Akure and grilled chicken/grills/food-delivery queries. Results exposed local listing pages with explicit FUTA gate/Akure location wording and a directly inspected [local food site](https://chikinimonie.lovable.app/) with plainly named meals and delivery context. This is directional content research, not a verified Google rank-position report. No competitor claims, numbers or promotional language are copied. The sampled search provider did not establish the owner's current Google AI Overview or account-specific Maps presentation.

The site's food/location vocabulary supports relevant searches without turning the brand into an ordering-hours description. Brand/site/business links give crawlers consistent identity evidence; they cannot force Google to merge result cards, show particular sitelinks, autocomplete a name, select the preferred description or rank first. Google controls result selection and recrawling.

There is no connected Google Business Profile or Search Console management tool here. No profile edit, Search Console submission or indexing request is claimed. After deployment, request indexing for Home and Our Story in the owner's verified Search Console property and ensure the sitemap is submitted. Keep the Business Profile website set to https://holygrills.online/ and use the same brand name and actual service-area/contact details there.

Suggested Google Business Profile description, ready to paste:

> Holy Grills brings students together around campus life at FUTA, Akure. We started with one grill outside a hostel and a love for meals worth sharing. Discover flame-grilled chicken, wings, skewers, plates, buns and sides, with delivery to campus gates and hostels. Food is where the connection starts. Campus events, shared experiences and Holy Points give students more reasons to participate and return. Made With More Than Flame. Faith. Love. Energy. Flavor.

Google references: [site names](https://developers.google.com/search/docs/appearance/site-names), [organization identity](https://developers.google.com/search/docs/appearance/structured-data/organization), [local ranking factors](https://support.google.com/business/answer/7091).

## Verification

The production build now runs `test:brand-publication` after prerendering. It reads actual generated HTML for all seven public routes plus the app shell and 404, checks exactly one consistent business identity and one website identity, verifies public mission/vision and review links in prerendered content, and guards against selected founder-only source material leaking into those pages. Build, typecheck, native mobile/desktop and live publication results are recorded with the completed batch.

Final integrated TypeScript and full client/SSR/prerender build passed after rebasing over the other chat's event changes through `c0c3db3`. The brand-publication check passed across all generated pages/shells. Targeted React/SEO lint passed. Native Chromium interaction checks at 393px and 1280px passed the mission/vision content, FAQ navigation/answers, review/profile links and single runtime business/site records, with API writes isolated.

The native interaction checks use the client-mounted app shell, while the build check separately inspects the actual prerendered content. An initial immediate-response fixture probe using prerender hydration reproduced the previously observed recoverable React Suspense error 421; this copy/identity batch does not claim to close that broader hydration/performance case.
