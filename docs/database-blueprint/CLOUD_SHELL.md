# Export the schema using a browser terminal

This is the alternative when this assistant workspace cannot reach PostgreSQL. It does **not** require running the export on your phone/computer, upgrading Supabase or changing the live site's database connection.

## Open the terminal

Open [Google Cloud Shell](https://shell.cloud.google.com/) and sign in to your own Google account. Cloud Shell has a usage quota; no paid server or billing-enabled Google Maps API is needed for this database export. Check Google's [current quotas](https://cloud.google.com/shell/docs/quotas-limits) for your account.

In the terminal, run:

```bash
git clone --depth 1 https://github.com/canibless01/Holy-Grills-.git hg-schema-export
cd hg-schema-export
bash tools/export_schema_browser_terminal.sh
```

This creates a small isolated Python environment in the browser workspace and installs the pinned database driver. It uses PostgreSQL client tools if available, otherwise the PostgreSQL 17 Docker client.

## Enter the connection privately

When the script prompts for **Source URL**, paste your project's **Session pooler connection URL** from Supabase → **test 2 → Connect**. Use session mode, normally port **5432**, with the database password filled in. The input is hidden; it is not placed in the shell command history or committed anywhere. Do not paste it into chat.

The script reads the database only. A successful export produces a private ZIP containing the complete schema-only SQL, managed Auth/Storage overlays, reference SQL, inventory and checksums. It then starts the Cloud Shell browser download. No customer, menu, price, balance, order or other application data rows are exported. Cron definitions and role attributes/membership are reference configuration metadata, without role passwords.

If the terminal asks you to enable billing or provision a paid service, stop: those steps are not needed by this script. Likewise, do not create a new Supabase branch or restore a full customer-data backup for this purpose.

## What to do with the result

Save the downloaded ZIP privately. You can attach its schema files here for inspection and fresh-project restore planning. Follow [the main restore guide](README.md) before applying anything: a new hosted Supabase project already owns its Auth/Storage infrastructure, and its settings/provider credentials must be chosen separately.

Do not upload the live SQL ZIP to the public GitHub repository. Even without table rows, database code can contain internal business rules, brand wording and fixed URLs.

## Verification boundary

The underlying exporter passed a real PostgreSQL 17 local dump/restore proof. This browser-terminal wrapper has syntax and local integration checks. The actual Google sign-in and source-project network connection must happen in your own browser terminal; they have not been marked successful from this workspace.
