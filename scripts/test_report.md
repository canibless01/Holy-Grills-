# Holy Grills API — End-to-End Test Report

**Run ID:** `5bf11874`  
**Date:** 2026-07-09 06:44 UTC  
**Results:** 125 passed / 1 failed / 0 skipped / 126 total

## Endpoint Results

| Status | Endpoint | HTTP | Error |
|--------|----------|------|-------|
| ✅ | GET /health | 200 |  |
| ✅ | POST /auth/register | 201 |  |
| ✅ | POST /auth/login | 200 |  |
| ✅ | POST /auth/refresh | 200 |  |
| ✅ | GET /auth/me | 200 |  |
| ✅ | PATCH /auth/profile | 200 |  |
| ✅ | POST /auth/addresses | 201 |  |
| ✅ | GET /auth/addresses | 200 |  |
| ✅ | PATCH /auth/addresses/<id> | 200 |  |
| ✅ | DELETE /auth/addresses/<id> | 200 |  |
| ✅ | GET /auth/streak | 200 |  |
| ✅ | POST /auth/verify-email | 200 |  |
| ✅ | POST /auth/reset-password | 200 |  |
| ✅ | POST /auth/device-token | 201 |  |
| ✅ | GET /storefront/sections | 200 |  |
| ✅ | GET /storefront/operating-hours | 200 |  |
| ✅ | GET /storefront/banners | 200 |  |
| ✅ | POST /storefront/promo-codes/validate | 200 |  |
| ✅ | POST /storefront/newsletter | 201 |  |
| ✅ | GET /menu/items | 200 |  |
| ✅ | GET /menu/categories | 200 |  |
| ✅ | GET /menu/items/<id> | 200 |  |
| ✅ | GET /orders/delivery-windows | 200 |  |
| ✅ | GET /orders/delivery-windows/status | 200 |  |
| ✅ | GET /orders/delivery-zones | 200 |  |
| ✅ | POST /orders/validate-promo | 200 |  |
| ✅ | POST /orders (wallet payment) | 400 |  |
| ✅ | GET /orders | 200 |  |
| ✅ | GET /orders/active | 200 |  |
| ✅ | GET /orders/scheduled | 200 |  |
| ✅ | GET /cart | 200 |  |
| ✅ | POST /cart (add item) | 201 |  |
| ✅ | PATCH /cart/<id> (qty=3) | 200 |  |
| ✅ | GET /saved | 200 |  |
| ✅ | POST /saved (save item) | 201 |  |
| ✅ | PATCH /saved/<id> | 200 |  |
| ✅ | DELETE /saved/<id> | 200 |  |
| ✅ | POST /saved/from-cart/<id> | 200 |  |
| ✅ | DELETE /cart (clear) | 200 |  |
| ✅ | GET /hp/balance | 200 |  |
| ✅ | GET /hp/transactions | 200 |  |
| ✅ | GET /hp/tiers | 200 |  |
| ✅ | GET /hp/spin/history | 200 |  |
| ✅ | POST /hp/spin | 200 |  |
| ✅ | POST /hp/transfer | 400 |  |
| ✅ | GET /wallet | 200 |  |
| ✅ | GET /wallet/transactions | 200 |  |
| ❌ | POST /wallet/fund/card | 502 | {"error": "Card payments are not configured on this server."} |
| ✅ | POST /wallet/fund/bank | 502 |  |
| ✅ | GET /referrals | 200 |  |
| ✅ | GET /referrals/stats | 200 |  |
| ✅ | GET /notifications | 200 |  |
| ✅ | GET /notifications?unread=true | 200 |  |
| ✅ | GET /notifications/preferences | 200 |  |
| ✅ | POST /notifications/read-all | 200 |  |
| ✅ | GET /leaderboard | 200 |  |
| ✅ | GET /leaderboard/my-rank | 200 |  |
| ✅ | GET /leaderboard/squad | 200 |  |
| ✅ | GET /leaderboard/hall-of-fame | 200 |  |
| ✅ | GET /rewards | 200 |  |
| ✅ | GET /rewards/redemptions | 200 |  |
| ✅ | GET /rewards/<id> | 200 |  |
| ✅ | POST /rewards/<id>/redeem | 400 |  |
| ✅ | GET /marketplace | 200 |  |
| ✅ | GET /marketplace/<id> | 200 |  |
| ✅ | POST /marketplace/<id>/purchase (wallet) | 201 |  |
| ✅ | GET /marketplace/purchases | 200 |  |
| ✅ | GET /marketplace/admin/purchases | 200 |  |
| ✅ | GET /marketplace/admin/listings | 200 |  |
| ✅ | POST /marketplace/requests | 201 |  |
| ✅ | GET /marketplace/admin/requests | 200 |  |
| ✅ | PATCH /marketplace/admin/requests/<id> | 200 |  |
| ✅ | GET /events | 200 |  |
| ✅ | GET /events/<id> | 200 |  |
| ✅ | POST /events/<id>/register (first call → 201) | 201 |  |
| ✅ | POST /events/<id>/register (second call → 200, idempotent) | 200 |  |
| ✅ | Event registration idempotent — same ticket_id on re-register | 200 |  |
| ✅ | POST /events/<id>/qr (admin) | 200 |  |
| ✅ | POST /events/<id>/checkin (ticket_id as qr_token) | 400 |  |
| ✅ | POST /events/catering-requests | 201 |  |
| ✅ | GET /events/catering-requests (admin) | 200 |  |
| ✅ | PATCH /events/catering-requests/<id> | 200 |  |
| ✅ | GET /events/admin | 200 |  |
| ✅ | PATCH /events/<id> (admin) | 200 |  |
| ✅ | GET /challenges | 200 |  |
| ✅ | GET /challenges/admin | 200 |  |
| ✅ | POST /challenges/<id>/complete | 200 |  |
| ✅ | PATCH /challenges/<id> (admin) | 200 |  |
| ✅ | GET /kitchen/settings | 200 |  |
| ✅ | GET /kitchen/queue | 200 |  |
| ✅ | GET /kitchen/windows | 200 |  |
| ✅ | GET /kitchen/scheduled | 200 |  |
| ✅ | GET /kitchen/metrics | 200 |  |
| ✅ | GET /riders/my-batch | 200 |  |
| ✅ | GET /riders/history | 200 |  |
| ✅ | GET /riders/stats | 200 |  |
| ✅ | GET /riders/earnings | 200 |  |
| ✅ | POST /order-locks (create) | 201 |  |
| ✅ | GET /order-locks | 200 |  |
| ✅ | GET /order-locks/<id> | 200 |  |
| ✅ | PATCH /order-locks/<id>/reschedule | 200 |  |
| ✅ | GET /admin/users | 200 |  |
| ✅ | GET /admin/users/<id> | 200 |  |
| ✅ | GET /admin/users/<id>/orders | 200 |  |
| ✅ | GET /admin/users/<id>/hp | 200 |  |
| ✅ | GET /admin/users/<id>/wallet | 200 |  |
| ✅ | GET /admin/orders | 200 |  |
| ✅ | GET /admin/delivery-windows | 200 |  |
| ✅ | GET /admin/delivery-batches | 200 |  |
| ✅ | GET /admin/promo-codes | 200 |  |
| ✅ | GET /admin/abandoned-carts | 200 |  |
| ✅ | GET /admin/first-order-gifts | 200 |  |
| ✅ | GET /admin/settings | 200 |  |
| ✅ | PATCH /admin/settings/<key> | 200 |  |
| ✅ | POST /admin/hp/bulk-grant | 200 |  |
| ✅ | POST /admin/delivery-windows | 201 |  |
| ✅ | GET /analytics/dashboard | 200 |  |
| ✅ | GET /analytics/sales | 200 |  |
| ✅ | GET /analytics/hp | 200 |  |
| ✅ | GET /analytics/referrals | 200 |  |
| ✅ | GET /analytics/orders | 200 |  |
| ✅ | GET /analytics/marketplace | 200 |  |
| ✅ | POST /webhooks/paystack (no sig → 401) | 401 |  |
| ✅ | POST /webhooks/flutterwave (no sig → 401) | 401 |  |
| ✅ | POST /auth/logout-all-devices | 200 |  |
| ✅ | POST /auth/logout | 200 |  |

---
*Auto-generated by `scripts/test_e2e.py`*
