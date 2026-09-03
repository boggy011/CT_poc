-- Schema and attachment Volume. The catalog itself is created once by an admin (see docs/deploy.md).
CREATE SCHEMA IF NOT EXISTS ${catalog}.${schema};
CREATE VOLUME IF NOT EXISTS ${catalog}.${schema}.attachments COMMENT 'RetPack PDF attachments, one folder per account and submission';
