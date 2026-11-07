# Administrative webhook controls — 7 November 2026

The replay endpoint now uses the same atomic failed-to-processing claim as provider callbacks. An admin retry competing with another retry/callback returns in-progress or already-processed without entering the handler. Failed handlers retain a retryable failed record. Only failed receipts from supported providers with saved identity/payload can enter this path.

Webhook reads use strict pagination, stable timestamp/ID order, inclusive WAT date boundaries with exclusive UTC end, and reject reversed/invalid dates. A campus-unknown failure is shown to campus admins only as bounded diagnostic metadata; payload, reference, raw error and any response/headers/metadata are withheld. Super-admin diagnostics retain the full receipt.

The native log now forwards selected campus, resets/discards old responses across scope/filter changes, pages through results and distinguishes failed reads from an empty log with Retry. Replay is latched against double clicks. The empty-state copy correctly identifies incoming provider events.

Executed checks: 19 targeted backend tests passed; native Chromium passed scope switching, superseded replies, pagination, failed reads/Retry and replay double-click isolation. Provider traffic was intercepted; no actual charge was replayed. The separate database-security migration protects stored payloads against browser writes; see EVENT_WEBHOOK_DATABASE_SECURITY_2026_11_07.md.

Integration: **1,268 backend tests passed**, TypeScript and targeted ESLint passed, and the complete client/SSR/seven-route prerender build passed.
