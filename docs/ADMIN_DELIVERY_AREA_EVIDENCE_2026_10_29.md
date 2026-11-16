# Admin page audit: Delivery → Delivery area

Story: an authorized admin chooses a campus, reads its saved centre and radius, changes one, and the public configuration/checkout distance decision uses that campus's values.

## Fixed boundaries

- Centre GET/PATCH already used an explicit campus path, but radius GET/PATCH omitted the explicit query required by the kitchen settings endpoint. Both now target the local selector's campus. A super admin's student campus or unrelated header selection cannot redirect these requests.
- A campus admin uses their verified user/profile campus, rather than the super-admin-only selector's stored value. Existing backend ownership checks and RLS still enforce the boundary.
- Failed reads previously became an empty centre and a guessed 15 km radius. Now either failed read exposes Retry and no editable defaults. When an optional setting is absent after a successful read, the radius comes from the server's location metadata, not a hardcoded frontend radius.
- A request generation guard ignores a late response from a previously selected campus. An immediate write latch and disabled inputs/selector prevent duplicate or overlapping centre/radius saves.
- Outside-country override is offered only after the specific 400 response code. A timeout, authorization failure or other error cannot be mistaken for permission to force coordinates.
- Backend radius updates reject boolean, zero, negative, nonnumeric and nonfinite inputs before any setting is written. Invalid outer JSON is a clear 400. Super-admin campus query identifiers are validated. Existing callers without an explicit campus argument retain their API contract; this page passes its target explicitly.
- The old no-centre warning incorrectly promised a default-radius check. It now explains the actual contract: without a centre the distance limit cannot be enforced. Clearing a centre remains explicit; setting it before accepting off-campus orders is an operational launch requirement.

## Executed evidence

| Boundary | Result / evidence |
| --- | --- |
| Native UI → requests | `scripts/test-admin-delivery-area-browser.py`: choose B while admin header/profile are A; both requests target B, including saves; delayed A reply cannot overwrite B |
| Inputs / failed requests | Negative radius refused, duplicate Save sends once, failed centre save retains text, generic error has no force action, explicit outside-country override and clear work, failed read has Retry and no Save control |
| Response → UI / public view | Saved centre/radius reload, Maps URL reflects saved centre, successful server metadata supplies a missing setting, controlled public config reflects only the selected campus |
| Handler → data / rules | Nine `tests/test_delivery_area_contract.py` cases: strict radius/JSON validation, explicit super scope, campus-admin scope pinning, foreign-centre refusal, save/clear/force code, and actual checkout distance helper using the configured radius |
| Real database backing rows / permissions | `tests/sql/admin_delivery_area_scope.sql`: real authenticated own-radius insert/edit, foreign and student update denial, private settings visibility, super-admin superset; authorized service centre save/clear leaves the other campus and radius intact. All fixtures roll back |
| Integrated regression | Full backend **769 passed**; frontend typecheck, changed-file lint, full production build and native browser checks pass. The current upstream real SSR child-process test confirms Home renders and exits naturally |

The browser uses controlled HTTP; the handler distance check uses controlled rows; the SQL test proves actual persisted backing rows/RLS. These are distinct pieces of evidence, not a claim that a production customer order was charged or a physical delivery performed. No production centre, radius, account, financial balance or public content was changed; no migration or new policy was needed.

Latest main's independent SSR timer, storefront recovery and push-origin fixes are preserved. The integrated calendar and delivery-location browser regressions also passed. Native device push/install and remaining provider acceptance checks are separate from these admin pages.

This closes the listed Delivery area controls. The broader admin audit remains open: the wider kitchen/settings controls, feature-flag consumers, promo/reward combination controls, messaging/admin blasts and remaining platform/reporting actions still require their own matrices. No cleanup, external cron or hosting migration was performed.
