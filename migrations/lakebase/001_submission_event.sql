-- Lakebase (Postgres) transactional store. Same columns as the Delta table; ACID and a real unique constraint.
CREATE SCHEMA IF NOT EXISTS ${schema};

CREATE TABLE IF NOT EXISTS ${schema}.submission_event (
  submission_id TEXT        NOT NULL,
  account_id    TEXT        NOT NULL,
  seq           INTEGER     NOT NULL CHECK (seq >= 1),
  event_type    TEXT        NOT NULL,
  actor         TEXT        NOT NULL,
  actor_role    TEXT        NOT NULL,
  occurred_at   TIMESTAMPTZ NOT NULL,
  payload       JSONB       NOT NULL,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (submission_id, seq)
);

CREATE INDEX IF NOT EXISTS submission_event_account_idx ON ${schema}.submission_event (account_id, submission_id);
