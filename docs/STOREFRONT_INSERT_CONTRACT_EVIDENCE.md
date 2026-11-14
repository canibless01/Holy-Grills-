# Storefront insert contracts — 21 October 2026

The editor and backend now require only content used by each consumer. What's Inside visibility after login is managed separately by the homepage and remains guest-only per the user's correction.

| Surface | Required content | Optional content |
|---|---|---|
| What's Inside text card | Title | Icon, subtitle, eyebrow, action |
| Process text card | Title and image | Subtitle, eyebrow, badge, action |
| Process/Inside/promo artwork | Image | Overlay copy is not required |
| Popup | Image | Destination; no action label or overlay copy required |
| Story/catering/promo text | At least one useful visible text/artwork field | Title or image need not both be present |
| Review | Reviewer identity and review | Separate display title, rating defaults to existing consumer behavior |
| Share template | Base image | Title and caption |
| Tier icon | Image and known tier (including legacy key) | Display title |
| Menu banner | Image on every slide | No overlay title required |

Recognized text and image fields reject structured/non-string values. Destinations must be application paths or explicit HTTP(S) URLs; credentials, protocol-relative destinations, backslashes, whitespace and malformed hosts/ports are rejected. Popup placement is restricted to its five supported pages; banner placement is restricted to its four actual consumers. Existing custom metadata remains intact, and an unrelated visibility/order edit does not force old rows through new insert minimums.

Six new focused tests plus existing CMS suites completed **103 test executions**, including optional-field validation on insert/update, missing required content, unsupported placement, malformed URLs, preserved custom metadata and image-only menu slides. TypeScript and owned component ESLint passed.

The parent ran the actual routed admin browser with controlled API/upload fixtures on port 5189. All four cases passed: story caption without title/image, catering title without image, What's Inside text without an icon, and process artwork without copy. This proves the actual input controls and submitted payloads; it is not proof of real Cloudinary provider delivery or remote publication. The previous live publication evidence remains in [media repair evidence](STOREFRONT_MEDIA_REPAIR_EVIDENCE.md).

No migration, table, provider change or customer-data mutation was introduced. Cleanup remains paused. UI copy uses the central `messages.py` keys staged by the parent.
