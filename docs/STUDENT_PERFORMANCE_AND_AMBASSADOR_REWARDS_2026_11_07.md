# Student loading and ambassador reward audit — 7 November 2026

## Student page loading

Dashboard now renders account/streak/tier/actions independently of order and lock panels. Recent orders have their own loading/error/retry state; an unavailable lock read does not fabricate a lock-in prompt. Wallet balances render independently of transaction history, while funding-return verification remains blocking and authoritative. Unknown wallet balances show a loading placeholder rather than an invented zero. Histories have retry feedback; completed funding no longer fetches the same history twice. HP-transfer eligibility reads run only when that feature is released.

Home and Menu use the same campus-scoped available catalogue query and existing 15-second cache. Home and Dashboard share a 15-second, account/campus/earned-total-scoped ranking query. Profile reuses the consistent campus/department/level snapshot. Financial balances, checkout totals, rewards and order status are not added to the catalogue cache. Server-rendered ranking queries do not retain a garbage-collection timer that prevents prerender exit.

Controlled mobile Chromium checks passed: visible Dashboard with held order-lock response, visible Wallet balance with held HP history response, blocked funding-return screen until verification succeeds, one catalogue request across Home→Menu, and one ranking request across Home→Dashboard. Production writes: zero. TypeScript and the complete client/SSR/prerender build passed. These are interaction/request-count checks, not a claim that every device/page is a fixed percentage faster.
