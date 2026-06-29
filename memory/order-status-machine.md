---
name: Order status machine
description: VALID_TRANSITIONS dict in app/services/order_service.py controls allowed status progressions.
---

## Rule
Admin refunds can be issued from ANY non-terminal order status (received, paid, preparing, ready, assigned, out_for_delivery, delivery_attempted, unclaimed, delivered).
`refunded` is a terminal state — no further transitions allowed.
`cancelled` is also terminal.

**Why:** The original machine only allowed `received → preparing | cancelled`, so admin refunds on any order that hadn't reached a specific state would 400. Fixed by adding `refunded` to all non-terminal destination lists.

**How to apply:** When adding new terminal states, add them to each applicable source state in `VALID_TRANSITIONS`. Never add transitions FROM terminal states.
