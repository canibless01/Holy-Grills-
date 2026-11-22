# Database architecture export kit — 22 November 2026

The requested clean-slate copy is a **schema-only baseline from the current live database**, not a customer-data backup and not a replay of every historical migration. It captures the current definitions even when another chat changed SQL directly.

## Current state — read this first

The live `test 2` architecture inventory was captured through the Supabase connection. A full live `application.sql` dump **has not been generated in this workspace**: direct PostgreSQL connections are unavailable here (the direct hostname is IPv6; session-pooler PostgreSQL traffic is also unavailable through this workspace's HTTP-only route). Do not mistake the inventory or function-reference file for a complete importable baseline.

The exporter is implemented and verified using a real PostgreSQL 17 dump and fresh local restore. It is ready to run from a computer/runner that can reach the source project's session pooler. No source database schema, customer, order, price, setting or permission was changed by this work.

### Captured live inventory

| Object | Count |
|---|---:|
| Application tables (`public` + `hg_internal`) | 157 |
| Views | 16 |
| Application functions/procedures, excluding extension-owned routines | 282 |
| Custom enums/domains/ranges | 3 |
| Constraints | 800 |
| Indexes, including constraint indexes | 640 |
| Application triggers plus its Auth hook | 124 |
| Application/Auth/Storage policies | 322 |
| Database cron job definitions | 5 |

175 relations includes the 157 tables, 16 views and 2 sequences. Counts are a dated inventory, not a promise that future changes keep the same counts.

## 1. Produce the actual SQL baseline

On a trusted machine with this repository, the backend's Python dependencies (`psycopg2`) and PostgreSQL **17 or later** client tools installed:

1. Supabase → **test 2 → Connect → Session pooler**. Use the session-mode port, normally 5432. The transaction pooler is not the recommended pg_dump route.
2. Store that URL securely as `SOURCE_DATABASE_URL`. Percent-encode special characters in its password; do not paste credentials into chat, commit them, or put them into command arguments. The exporter parses them into environment variables.
3. Run from the repository root:

```bash
python tools/export_database_architecture.py --output database-architecture-2026-11-22
```

Use the Python interpreter where backend dependencies are installed. Alternatively the exporter uses Docker's `postgres:17-alpine` image if native `pg_dump` is absent; Docker host networking must reach the configured database host (Linux or explicitly supported Docker Desktop host networking). Native PostgreSQL client tools are the simpler cross-platform option.

The exporter never applies SQL, never dumps rows, never resets a project, and uses read-only sessions. Both dumps import the same exported PostgreSQL snapshot held open by the inventory transaction. Output uses a new empty directory; an interrupted dump cannot masquerade as a finished file. The completion marker is **manifest.json**.

### Output files

| File | Purpose |
|---|---|
| `application.sql` | Application schemas, tables/columns, enums, sequences, constraints, functions/procedures, views, indexes, triggers, RLS policies, grants/default privileges. `public` schema creation alone is made `IF NOT EXISTS` for a fresh Supabase project. |
| `managed-overlays.sql` | The application's Auth/Storage hooks and policies, after application objects. It never recreates Supabase's managed tables. |
| `inventory.json` | Source definitions/counts, extensions, role attributes/memberships without passwords, publications/membership and database cron definitions. |
| `manifest.json` | Capture time, file hashes, counts and explicit `restore_tested: false` until the actual target has been checked. |
| `reference/application.raw.sql` | Unmodified canonical application pg_dump output, before the public-schema compatibility adjustment. |
| `reference/full-database.schema.sql` | Schema-only reference for managed Auth/Storage/Realtime/extension infrastructure as well. **Do not import wholesale over a new hosted Supabase project.** |

The export is private source code. A schema-only file can still contain fixed URLs, brand wording or a literal inside a function. Review such bindings and any credentials before sharing/reusing it; do not assume “no table rows” means “no environment-specific strings.”

## 2. Restore into a fresh Supabase project

Create the new project separately; this kit does not create a billable project or write to an existing target. Use PostgreSQL 17+ with the compatible Supabase platform baseline.

Before applying anything:

- Confirm the destination is **the new empty project**, never test 2. Confirm no existing application tables/data would be overwritten. Do not use `--clean`, a remote reset, or `DROP SCHEMA public CASCADE` on an existing project.
- Enable the source's required supported extensions using `inventory.json`. Its extension set includes `citext`, `pg_cron`, `pg_net`, `pg_stat_statements`, `pg_trgm`, `pgcrypto`, `supabase_vault`, `uuid-ossp` and built-in `plpgsql`. Managed/non-relocatable extensions must be installed through supported Supabase setup; do not blindly move or rebuild them.
- Keep Supabase-managed roles. Review any genuinely custom role and membership required by grants; do not copy old role passwords or JWT keys. `--no-owner` deliberately makes imported application objects owned by the restoring trusted database owner.

With the new project's connection securely configured for `psql`, apply in order, stopping on errors:

```bash
psql --single-transaction --set ON_ERROR_STOP=1 --file database-architecture-2026-11-22/application.sql
psql --single-transaction --set ON_ERROR_STOP=1 --file database-architecture-2026-11-22/managed-overlays.sql
```

Do **not** also replay all historical migrations after importing the current baseline: that can reapply old changes, old seeds or obsolete policies. Establish this as the new project's starting migration, then apply only later reviewed changes. Existing Supabase migration-history **rows** are intentionally not copied.

Compare the target against the inventory: table/type/function signatures, constraints, indexes, view security options, trigger enabled modes, RLS/policies and browser/service grants. Then test signup/Auth hook, login, role/campus isolation, checkout/payment/refund, wallet/reward conservation and notification workers using the **new project's** own configuration. The local fixture proof is not a completed live-source-to-new-Supabase restore test.

## 3. Fresh configuration — deliberately separate from structure

A schema contains feature implementations; it does not populate their runtime settings.

The following records/settings must be selected afresh for the new brand:

- Campuses/academic reference data, delivery gates/zones/hostels, ordering/delivery calendar and capacity.
- Tier definitions/perks, settings, feature flags, challenges/reward catalogue and measurement/reference units. Do not invent economic settings or silently reuse Holy Grills' financial values.
- Menus, add-ons, prices, stock and campaigns. **No such rows are copied.**
- Initial administrator: create its own Auth account, then bootstrap the appropriate role through a reviewed destination-only operation. No old super-admin/customer identities are copied.
- Operational alert/report recipients, sender branding, business/review URLs, privacy/terms and notification wording. Never let a new brand's reports go to Holy Grills' inbox.

Auth/SMTP/provider configuration is not reconstructed by database DDL. Set new project keys, Site URL/redirect allowlist, SMTP/templates, provider callbacks/webhooks, storage buckets, Realtime publication membership, Auth provider/hook configuration, any Edge Functions/secrets, Vercel/Railway variables and domains. Storage object files and Cloudinary assets are not included.

### Scheduled jobs

There are **five database cron jobs** in the captured source, in addition to the external Celery worker/beat deployment. Their names/schedules/commands are recorded as private configuration metadata; do not automatically enable them against a new brand. Review commands for old endpoints/keys and whether the external scheduler already handles an equivalent job. Recreate only the intended jobs and verify one effective scheduler per job. Celery schedules and task code are in the application repository, not magically copied by SQL.

## Validation performed here

- Five exporter safeguard tests pass (credential handling, schema-only invocation, failed-output safety, managed overlays and targeted public-schema compatibility).
- A real disposable localhost PostgreSQL 17 source → dump → empty-target restore passes: enum, indexes, invoker view, RLS, service-only function grants, Auth signup trigger and Storage policy survive. Customer/price sentinels are absent and the restored menu is empty.
- Source production access in this task was read-only metadata and the owner's requested order eligibility lookup. No customer messages or fake paid orders were created.

The remaining export step is running the exporter over a reachable PostgreSQL connection. The later step is testing that completed export against the actual fresh Supabase target. Neither is marked completed in the kit.

References: [Supabase backup/restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore), `tools/schema_architecture_inventory.sql`, `tools/export_database_architecture.py`.
