CREATE TABLE IF NOT EXISTS ref_account (account_id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, sales_org TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ref_sku (account_id TEXT NOT NULL, sku_code TEXT NOT NULL, description TEXT NOT NULL, PRIMARY KEY (account_id, sku_code));
CREATE TABLE IF NOT EXISTS ref_sales_org (code TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ref_email_account (email TEXT NOT NULL, account_id TEXT NOT NULL, PRIMARY KEY (email, account_id));
CREATE TABLE IF NOT EXISTS ref_internal_user (email TEXT NOT NULL PRIMARY KEY);
CREATE TABLE IF NOT EXISTS keg_balance (account_id TEXT NOT NULL PRIMARY KEY, shipped INTEGER NOT NULL, returned INTEGER NOT NULL, as_of TEXT NOT NULL);
