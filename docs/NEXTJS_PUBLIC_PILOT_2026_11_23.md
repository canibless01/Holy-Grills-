# Next.js public pilot — 23 November 2026

Branch: `migration/nextjs-public-pilot`. Based on `main` at `ac76567`; no production cutover.

## Implemented scope

The browser loads a Next page; the Next server resolves an active campus, reads the existing public Python API and renders the selected public menu fields and CMS hero content into HTML. Native filtering and navigation work with JavaScript disabled. Ordering and account actions link to the existing live frontend.

| Boundary | Evidence |
|---|---|
| Production compilation | Next 16.4.6 production build and strict TypeScript pass |
| Public data selection | Nine tests cover internal-field exclusion, malformed data, sold-out states, filtering and unsafe CMS destinations |
| Browser/data flow | Fifteen local fixture acceptance checks cover no-JS rendering, search/categories, campus isolation, immediate price changes, retries and live product handoff |
| Route exposure | Private/payment paths return 404; all preview pages are noindex |
| Read-only source | Only five allowlisted public GET paths; no token/cookie forwarding, mutations, payment/messaging provider calls or DB migrations |
| Dependencies | Production dependency audit reports zero vulnerabilities |

## Operational findings

Native Node fetch initially could not reach Railway from the managed workspace because it did not use the configured outbound proxy. `NODE_USE_ENV_PROXY=1` fixes that environment-specific path. Python could reach the same public API throughout. This was not evidence of a production backend failure.

Browser testing found that the native category selector needed an explicit accessible name; corrected before the acceptance suite passed. A malformed public response now produces a recoverable error instead of a fabricated empty catalog. Selected public fields prevent internal pricing/reward metadata appearing in RSC payloads.

## Limits

This is a tested public Home/Menu pilot, not a complete Next.js rewrite. It does not implement authentication, cart, checkout, payment callbacks, private role pages, notifications, PWA or complete CMS visual parity. Its fixed preview noindex policy is intentional. No production speed improvement is claimed without a matched hosted comparison.

See `holy-grills-next/README.md` for run commands, source/cache boundaries and remaining phases. Live API browser screenshots and detailed source-data observations are kept outside the public repository under `/workspace/shared/nextjs-pilot/`.

## Live public-source acceptance

A production-mode local Next server read the Railway public API successfully using the workspace proxy. Home CMS copy and all 15 returned public menu items appeared in initial HTML. Desktop/mobile browser checks and a JavaScript-disabled menu check passed, without browser-side source API calls, page errors or horizontal overflow. There were no source mutations. This proves the read/render boundary against the existing API; it does not prove a Vercel-hosted preview or any payment/auth flow.
