-- Local / test store with the same shape. Timestamps are ISO-8601 UTC strings; payload is JSON text.
CREATE TABLE IF NOT EXISTS submission_event (
  submission_id TEXT    NOT NULL,
  account_id    TEXT    NOT NULL,
  seq           INTEGER NOT NULL CHECK (seq >= 1),
  event_type    TEXT    NOT NULL,
  actor         TEXT    NOT NULL,
  actor_role    TEXT    NOT NULL,
  occurred_at   TEXT    NOT NULL,
  payload       TEXT    NOT NULL,
  ingested_at   TEXT    NOT NULL,
  PRIMARY KEY (submission_id, seq)
);

CREATE INDEX IF NOT EXISTS submission_event_account_idx ON submission_event (account_id, submission_id);
