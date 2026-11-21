# Remaining editor recovery — 21 November 2026

This batch extends A5's recorded controls; it does not declare every remaining editor field or provider observation complete.

- Menu catalogue failures now show an error and Retry instead of an apparently empty catalogue. Retry restores the real rows. A pending item save cannot dismiss its editor.
- Add-on configuration and menu catalogue reads start together. A failed initial read cannot silently fabricate an empty global catalogue. Failed post-save list refresh has an independent Retry.
- Per-item modifiers are bound to the item whose reads actually completed. Inputs and save are disabled until that item's detail and add-on reads succeed. Reversed responses are ignored; selecting another item cannot attach the former item's groups to it. Item selection stays fixed during a modifier save.
- Global add-on and reward save actions reject immediate duplicate invocation. Their fields and dismissal are locked while saving; failure retains the draft. Reward economics previews, percentage units, read-only HP outputs and expected-version conflict recovery remain intact.

Validation: actual React pages via controlled HTTP, no production writes. `scripts/test-admin-editor-recovery-browser.py` passes at 393 and 1280 pixels (read failures, Retry, reversed replies, disabled save, duplicate invocation, retained draft and failed post-save refresh). `scripts/test-reward-price-browser.py` passes at both widths (pending double invocation, dismissal/field lock, 503 retained draft, success and 409 recovery). Typecheck, lint and full production build pass.

Remaining A5: final native reconciliation of challenge, free-credit and onboarding editor controls and the other menu field cases absent from prior evidence. Remaining reporting and actual operational observations stay in the master checklist.
