# Live automatic-funding SQL verification — 12 November 2026

Read-only comparison found the live `hg_wallet_auto_funding(text,uuid,uuid,jsonb)` body exactly matches `20261108231500_wallet_auto_funding_fee_reconciliation.sql` after excluding comments and formatting. The normalized body SHA-256 was `518c8e486dd9cb03bb99fae52c017b6762235334f40738fc601e9151749e9b84`.

The current backend and UI use `wallet-auto-funding-v2` consent. New plans require that consent; existing-plan verification remains available. Anon and authenticated roles cannot execute the RPC; the backend service role can. Removing explanatory SQL comments did not change the function's behavior.

The current code labels Paystack fees as customer-paid. The owner explicitly reconfirmed **Customer pays the fee** on 12 November, superseding the earlier Holy Grills-absorbs choice. No fee-policy change was made during this verification.

The existing automatic-funding SQL matrix ran successfully in a production BEGIN/ROLLBACK transaction. It exercises new-plan receipt replay, ownership, invalid/underpaid confirmation, bounded fee reconciliation, funding credits, duplicate callbacks and plan lifecycle without a provider request. The full backend suite, including automatic-funding contracts, passes. No existing plan/attempt was edited and no real Paystack charge was attempted. This confirms code/database agreement and recorded financial rules; it does not claim a new bank/card acceptance test.
