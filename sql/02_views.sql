-- Views for people and agents: names and joins resolved once, here.
USE poc;

-- Every creative, with its platform and account names.
CREATE VIEW IF NOT EXISTS v_creatives AS
SELECT f.report_date,
       p.report,
       p.platform,
       p.channel_group,
       a.account,
       f.status,
       f.creative_key,
       f.creative_name,
       f.campaign,
       f.region,
       f.days_since_end,
       f.impressions,
       f.clicks,
       f.conversions,
       f.media_cost,
       f.source_file,
       f.source_tab
FROM fact_creative AS f
JOIN dim_platform AS p ON p.platform_id = f.platform_id
LEFT JOIN dim_account AS a ON a.account_id = f.account_id;

-- Only the latest report date of each report.
CREATE VIEW IF NOT EXISTS v_latest_creatives AS
SELECT c.*
FROM v_creatives AS c
JOIN (SELECT report, MAX(report_date) AS report_date
      FROM v_creatives
      GROUP BY report) AS latest
  ON latest.report = c.report AND latest.report_date = c.report_date;
