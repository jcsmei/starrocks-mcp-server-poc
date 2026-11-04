-- A read-only user for AI agents.  The StarRocks MCP server always
-- offers a write_query tool, so the database itself must refuse
-- changes: this user can read the poc database and nothing else.
-- The password placeholder is replaced at run time from a secret.
CREATE USER IF NOT EXISTS 'agent_reader'@'%' IDENTIFIED BY '${AGENT_PASSWORD}';
GRANT SELECT ON ALL TABLES IN DATABASE poc TO USER 'agent_reader'@'%';
GRANT SELECT ON ALL VIEWS IN DATABASE poc TO USER 'agent_reader'@'%';
GRANT SELECT ON ALL MATERIALIZED VIEWS IN DATABASE poc TO USER 'agent_reader'@'%';
