-- Defence in depth for FR-02. Apply only when queries run as the signed-in user (on-behalf-of authorization) or
-- when every service identity that reads the table is listed in ref_internal_user. Opt-in via
-- RETPACK_MIGRATE_ROW_FILTERS=1 in the migrate CLI. When the app queries as its service principal without that
-- listing, this filter would hide every row from it; the repository-layer filter remains the primary control.
CREATE OR REPLACE FUNCTION ${catalog}.${schema}.account_visible(account_id STRING)
RETURNS BOOLEAN
RETURN
  EXISTS (SELECT 1 FROM ${catalog}.${ref_schema}.ref_internal_user i WHERE lower(i.email) = lower(current_user()))
  OR EXISTS (
    SELECT 1 FROM ${catalog}.${ref_schema}.ref_email_account m
    WHERE lower(m.email) = lower(current_user()) AND m.account_id = account_visible.account_id
  );

ALTER TABLE ${catalog}.${schema}.submission_event
  SET ROW FILTER ${catalog}.${schema}.account_visible ON (account_id);
