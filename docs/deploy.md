# Deploying to a Databricks workspace (Phase B)

Prerequisites: workspace access with permission to create an app, a SQL warehouse, a Unity Catalog schema
(`<catalog>.retpack`) and a Volume (`<catalog>.retpack.attachments`). Reference views per
`docs/data_contract.md` §4 must exist in `<catalog>.<ref_schema>` (dev stubs: `RETPACK_MIGRATE_DEV_STUBS=1`).

## 1. Schema

```bash
export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
export DATABRICKS_WAREHOUSE_ID=<id>
export RETPACK_CATALOG=ct_retpack_dev RETPACK_SCHEMA=retpack RETPACK_REF_SCHEMA=retpack
uv run python -m retpack_adapters.migrate_cli delta          # 001 table, 003 row filters
RETPACK_MIGRATE_DEV_STUBS=1 uv run python -m retpack_adapters.migrate_cli delta   # dev only: stub reference tables
```

Lakebase (optional Wave-2 path): `RETPACK_LAKEBASE_INSTANCE=<name> uv run python -m retpack_adapters.migrate_cli lakebase`.

## 2. App

```bash
databricks bundle deploy -t dev --var warehouse_id=$DATABRICKS_WAREHOUSE_ID
databricks apps deploy retpack-portal --source-code-path <workspace path printed by the bundle>
```

Then, in the app's settings, enable **user authorization** with the `iam.current-user:read` scope so the platform
forwards `X-Forwarded-Access-Token`; the app resolves the signed-in email from that token. Grant the app's service
principal `SELECT` on the reference views, `MODIFY` on `submission_event` and `READ/WRITE VOLUME` on the Volume.

## 3. Verify

```bash
RETPACK_TEST_DELTA=1 RETPACK_SUBMISSION_BACKEND=delta uv run pytest tests/contract tests/isolation -k delta
```

The isolation suite is the FR-02 release gate; do not promote a build that does not pass it on the target backend.

## 4. Jobs

`databricks bundle deploy` also creates `retpack-maintenance` (nightly OPTIMIZE / VACUUM) and
`retpack-attachment-reaper` (nightly orphan cleanup, 24 h grace). Build the wheel first: `uv build`.

## Settings reference

| Variable | Purpose |
|---|---|
| `RETPACK_SUBMISSION_BACKEND` | `delta` or `lakebase` |
| `RETPACK_CATALOG`, `RETPACK_SCHEMA` | where `submission_event` lives |
| `RETPACK_REF_SCHEMA` | where the ABI reference views live (defaults to `RETPACK_SCHEMA`) |
| `RETPACK_VOLUME` | Volume name under the schema (default `attachments`) |
| `DATABRICKS_WAREHOUSE_ID` | SQL warehouse for Delta access |
| `RETPACK_LAKEBASE_INSTANCE`, `RETPACK_LAKEBASE_DATABASE` | Lakebase backend only |
| `RETPACK_TRUST_FORWARDED_EMAIL` | `1` falls back to the email header when no token is forwarded (weaker; default `0`) |
| `RETPACK_REAPER_GRACE_HOURS` | reaper grace period (default 24) |
