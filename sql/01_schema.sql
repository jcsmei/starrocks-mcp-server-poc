-- A small star schema for marketing creatives.
--
-- One fact table, one row per creative per report date, and two
-- dimensions.  The fact table is a Duplicate Key table: it keeps every
-- row as loaded, which suits report snapshots.  It is partitioned by
-- report date, so a question about one date reads one partition, and
-- each load of a date can replace that date alone.

CREATE DATABASE IF NOT EXISTS poc;
USE poc;

-- Where a creative runs: a tab of a report workbook.
CREATE TABLE IF NOT EXISTS dim_platform (
    platform_id   INT          NOT NULL COMMENT "Surrogate key",
    report        VARCHAR(32)  NOT NULL COMMENT "paid_social, site_direct or site_serve",
    platform      VARCHAR(64)  NOT NULL COMMENT "The workbook tab, such as Reddit",
    channel_group VARCHAR(64)           COMMENT "Paid Social, Site Direct or Site Serve"
)
DUPLICATE KEY (platform_id)
DISTRIBUTED BY HASH (platform_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- Who the creative is for.
CREATE TABLE IF NOT EXISTS dim_account (
    account_id INT          NOT NULL COMMENT "Surrogate key",
    account    VARCHAR(64)  NOT NULL COMMENT "Advertiser account"
)
DUPLICATE KEY (account_id)
DISTRIBUTED BY HASH (account_id) BUCKETS 1
PROPERTIES ("replication_num" = "1");

-- One row per creative per report date.
CREATE TABLE IF NOT EXISTS fact_creative (
    report_date    DATE          NOT NULL COMMENT "The date in the workbook's file name",
    platform_id    INT           NOT NULL COMMENT "dim_platform",
    status         VARCHAR(16)   NOT NULL COMMENT "Live, Not Live or Unknown",
    account_id     INT                    COMMENT "dim_account",
    creative_key   VARCHAR(64)   NOT NULL COMMENT "Creative ID, or the name where a report has no ID",
    creative_name  VARCHAR(128)           COMMENT "",
    campaign       VARCHAR(128)           COMMENT "",
    region         VARCHAR(16)            COMMENT "NA, EMEA or APAC",
    days_since_end INT                    COMMENT "Days since the creative's end date",
    impressions    BIGINT                 COMMENT "",
    clicks         BIGINT                 COMMENT "",
    conversions    BIGINT                 COMMENT "Site Serve only",
    media_cost     DECIMAL(18, 2)         COMMENT "",
    source_file    VARCHAR(128)  NOT NULL COMMENT "Lineage: the workbook",
    source_tab     VARCHAR(64)   NOT NULL COMMENT "Lineage: the tab"
)
DUPLICATE KEY (report_date, platform_id, status)
PARTITION BY date_trunc('day', report_date)
DISTRIBUTED BY HASH (creative_key) BUCKETS 3
PROPERTIES ("replication_num" = "1");
