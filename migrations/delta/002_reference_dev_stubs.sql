-- DEV ONLY. In production these are ABI-owned views (input 4); the portal reads them and never writes.
-- Column names below are the portal's ASSUMPTION until the real DDL arrives; see docs/data_contract.md section 4.
CREATE TABLE IF NOT EXISTS ${catalog}.${ref_schema}.ref_account (
  account_id STRING NOT NULL, name STRING NOT NULL, sales_org STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${catalog}.${ref_schema}.ref_sku (
  account_id STRING NOT NULL, sku_code STRING NOT NULL, description STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${catalog}.${ref_schema}.ref_sales_org (
  code STRING NOT NULL, name STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${catalog}.${ref_schema}.ref_email_account (
  email STRING NOT NULL, account_id STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${catalog}.${ref_schema}.ref_internal_user (
  email STRING NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${catalog}.${ref_schema}.keg_balance (
  account_id STRING NOT NULL, shipped INT NOT NULL, returned INT NOT NULL, as_of TIMESTAMP NOT NULL
) USING DELTA;
