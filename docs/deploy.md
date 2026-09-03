# Deploying to a Databricks workspace (Phase B)

Prerequisites: workspace access with permission to create an app, a SQL warehouse, a Unity Catalog schema
(`<catalog>.retpack`) and a Volume (`<catalog>.retpack.attachments`). Reference views per
`docs/data_contract.md` §4 must exist in `<catalog>.<ref_schema>` (dev stubs: `RETPACK_MIGRATE_DEV_STUBS=1`).

## Current dev deployment (3 Sep 2026)

| Item | Value |
|---|---|
| Workspace | `https://adb-1283361390446220.0.azuredatabricks.net` (CLI profile `CT`) |
| Catalog | `ct_retpack_dev`, created with `MANAGED LOCATION` under the workspace root storage (the metastore has no default storage root; Default Storage catalogs can only be created in the UI) |
| App schema / CI schema | `ct_retpack_dev.retpack` (demo data seeded) / `ct_retpack_dev.retpack_ci` (truncated per test) |
| Reference stubs | `ct_retpack_dev.retpack.ref_*` and `keg_balance`, seeded from `config/mock` plus the developer's email in `ref_internal_user` |
| Warehouse | Starter Warehouse `26d7ac8a72a227a0` (serverless PRO) |
| App | `retpack-portal`, https://retpack-portal-1283361390446220.0.azure.databricksapps.com, service principal `8c693ca9-c4c8-498f-852f-e262ff4f8000` |
| Source path | `/Workspace/Users/bogdan.nejcev@customertimes.com/retpack-portal` (uploaded with `databricks sync`) |
| Row filters | not applied (opt-in; the app queries as its service principal) |
| Demo impersonation | on (`RETPACK_DEMO_IMPERSONATION=1` in `app.yaml`): ABI-team sign-ins can view as `anna@…`, `bram@…`, `carla@…`, `ops1@…`, `ops2@…` |

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

The steps below are what was actually run; the asset bundle in `databricks.yml` is an alternative that still needs
validating against the workspace.

```bash
uv export --no-dev --extra ui --extra databricks --no-hashes --no-emit-project -o requirements.txt
databricks sync . /Workspace/Users/<you>/retpack-portal --full
databricks apps create --json '{"name": "retpack-portal", "resources": [{"name": "sql-warehouse", "sql_warehouse": {"id": "<warehouse id>", "permission": "CAN_USE"}}]}'
databricks apps deploy retpack-portal --source-code-path /Workspace/Users/<you>/retpack-portal
```

Do not pass `user_api_scopes`: with none selected the platform assigns the identity scopes
(`iam.access-control:read`, `iam.current-user:read`) by default, which is all the app needs to resolve the signed-in
email from the forwarded access token. Named identity scopes are rejected by the API.

Grant the app's service principal (shown by `databricks apps get`) access to the data:

```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<service principal client id>`;
GRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA <catalog>.retpack TO `<service principal client id>`;
GRANT READ VOLUME, WRITE VOLUME ON VOLUME <catalog>.retpack.attachments TO `<service principal client id>`;
```

`app.yaml` sets `PYTHONPATH=src` so the three packages import without installing the project, and reads the
warehouse id from the bound resource. Redeploy after every `databricks sync`.

## 3. Verify

```bash
export DATABRICKS_CONFIG_PROFILE=CT DATABRICKS_WAREHOUSE_ID=<id> RETPACK_SUBMISSION_BACKEND=delta
export RETPACK_CATALOG=<catalog> RETPACK_SCHEMA=retpack_ci RETPACK_REF_SCHEMA=retpack RETPACK_TEST_DELTA=1
uv run pytest tests/contract tests/isolation -k "delta or volume-real"
```

Use a dedicated test schema: the fixtures empty `submission_event` before every test. The first workspace run on
3 Sep 2026 passed all 29 cases in about three minutes, warehouse cold start included.

Smoke-check the deployed app with your own OAuth token:

```bash
TOKEN=$(databricks auth token --profile CT -o json | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -H "Authorization: Bearer $TOKEN" https://<app url>/_stcore/health     # ok
curl -H "Authorization: Bearer $TOKEN" https://<app url>/logz/batch         # JSON log entries
```

The isolation suite is the FR-02 release gate; do not promote a build that does not pass it on the target backend.

## 4. Provisioning users

Two independent things gate a person:

1. **Access to the app itself** (Databricks). Workspace admins have it through the `admins` group; anyone else needs
   `CAN_USE` on the app: Compute → Apps → retpack-portal → Permissions, or
   `databricks apps set-permissions retpack-portal --json '{"access_control_list": [{"user_name": "<email>", "permission_level": "CAN_USE"}]}'`.
2. **Provisioning in the portal** (the reference tables; ABI-owned views in production, dev stubs here). Until this is
   done the person sees *"Your account is not provisioned"*.

```bash
export DATABRICKS_CONFIG_PROFILE=CT DATABRICKS_WAREHOUSE_ID=26d7ac8a72a227a0 RETPACK_CATALOG=ct_retpack_dev RETPACK_REF_SCHEMA=retpack
make users ARGS="list"
make users ARGS="add-internal someone@customertimes.com"          # ABI-team role: sees the Request Queue
make users ARGS="add-customer someone@dist.example A1 A2"         # customer role: sees the two customer screens
make users ARGS="remove someone@dist.example"
```

Or in the SQL editor: `INSERT INTO ct_retpack_dev.retpack.ref_internal_user VALUES ('someone@customertimes.com')` /
`INSERT INTO ct_retpack_dev.retpack.ref_email_account VALUES ('someone@dist.example', 'A1')`.

No restart or redeploy: identity is resolved from these tables on every page load, so the person just reloads the app.
The **View as** list in Demo Mode picks up new users the same way.

## 5. Jobs

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
| `RETPACK_DEMO_IMPERSONATION` | `1` lets a token-verified user who is on the internal list view the portal as any provisioned demo user (sidebar **Demo Mode**); every switch is audited as `demo_impersonation`. Dev demo only; leave unset in production |
| `RETPACK_REAPER_GRACE_HOURS` | reaper grace period (default 24) |
