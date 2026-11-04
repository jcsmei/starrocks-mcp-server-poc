-- Precomputed counts for the most common question: how many
-- creatives are live or not live on each platform, on each date.
-- StarRocks rewrites matching queries on fact_creative to read this
-- view instead, without the query naming it.
USE poc;

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_status_counts
DISTRIBUTED BY HASH (platform_id) BUCKETS 1
REFRESH MANUAL
PROPERTIES ("replication_num" = "1")
AS
SELECT report_date,
       platform_id,
       status,
       COUNT(*) AS creatives,
       COUNT(DISTINCT campaign) AS campaigns,
       SUM(media_cost) AS media_cost
FROM fact_creative
GROUP BY report_date, platform_id, status;
