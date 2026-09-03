-- Defence in depth for FR-02. Effective only when queries run as the signed-in user (on-behalf-of
-- authorization); when the app queries as its service principal the repository-layer filter is the control.
CREATE OR REPLACE FUNCTION ${catalog}.${schema}.account_visible(account_id STRING)
RETURNS BOOLEAN
RETURN
  is_account_group_member('retpack_internal')
  OR EXISTS (
    SELECT 1 FROM ${catalog}.${ref_schema}.ref_email_account m
    WHERE lower(m.email) = lower(current_user()) AND m.account_id = account_id
  );

ALTER TABLE ${catalog}.${schema}.submission_event
  SET ROW FILTER ${catalog}.${schema}.account_visible ON (account_id);
