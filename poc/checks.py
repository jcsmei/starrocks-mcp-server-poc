"""What the PoC verifies once the data is loaded.

Three kinds of check:

- data quality: the load is complete and consistent with the files;
- the core business questions, asked as the read-only agent user,
  with answers fixed in advance under the agreed definitions;
- query optimisation: what the planner does with and without a date
  filter, and before and after the materialized view exists.
"""

from decimal import Decimal

import db
import load

# The questions an analyst asks most, the SQL that answers them, and
# the answer agreed in advance.  "Not live" means status Not Live only;
# Unknown is always reported separately; creatives are counted, and a
# question about campaigns gets both numbers.
CORE_QUESTIONS = [
    ("How many live creatives on Reddit, and across how many campaigns?",
     "SELECT COUNT(*), COUNT(DISTINCT campaign) FROM v_latest_creatives "
     "WHERE platform = 'Reddit' AND status = 'Live'",
     [[29, 13]]),
    ("How many not live on Twitter Paid, and how many unknown?",
     "SELECT status, COUNT(*) FROM v_latest_creatives "
     "WHERE platform = 'Twitter Paid' AND status <> 'Live' "
     "GROUP BY status ORDER BY status",
     [["Not Live", 24], ["Unknown", 8]]),
    ("How many live on LinkedIn?",
     "SELECT COUNT(*) FROM v_latest_creatives "
     "WHERE platform = 'LinkedIn' AND status = 'Live'",
     [[36]]),
    ("How many live on Display for Site Direct?",
     "SELECT COUNT(*) FROM v_latest_creatives "
     "WHERE report = 'site_direct' AND platform = 'Display' "
     "AND status = 'Live'",
     [[67]]),
    ("Live and not live for Site Serve?",
     "SELECT status, COUNT(*) FROM v_latest_creatives "
     "WHERE report = 'site_serve' GROUP BY status ORDER BY status",
     [["Live", 38], ["Not Live", 62]]),
    ("Is creative CR-LIN-1000 live?",
     "SELECT platform, status FROM v_latest_creatives "
     "WHERE creative_key = 'CR-LIN-1000' ORDER BY platform",
     [["LINE", "Live"], ["LinkedIn", "Not Live"]]),
]

# The query the materialized view was built for.
STATUS_COUNTS = (
    "SELECT platform_id, status, COUNT(*) FROM fact_creative "
    "{where} GROUP BY platform_id, status"
)


def plain(value):
    """Return a whole-number Decimal as an int, so results compare simply."""
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    return value


def data_quality(connection, rows):
    """Return (check, expected, actual) for each data quality check."""
    checks = []
    expected = {}
    for row in rows:
        key = (row["report"], row["report_date"])
        expected[key] = expected.get(key, 0) + 1
    _, actual_rows = db.query(
        connection,
        "SELECT p.report, CAST(f.report_date AS VARCHAR), COUNT(*) "
        "FROM fact_creative f JOIN dim_platform p "
        "ON p.platform_id = f.platform_id GROUP BY 1, 2")
    actual = {(r[0], r[1]): int(r[2]) for r in actual_rows}
    for key, count in sorted(expected.items()):
        checks.append((f"Rows for {key[0]} on {key[1]}", count,
                       actual.get(key, 0)))
    _, statuses = db.query(connection,
                           "SELECT DISTINCT status FROM fact_creative")
    found = sorted(r[0] for r in statuses)
    checks.append(("Only known status values",
                   sorted(load.STATUSES & set(found)), found))
    _, orphans = db.query(
        connection,
        "SELECT COUNT(*) FROM fact_creative f LEFT JOIN dim_platform p "
        "ON p.platform_id = f.platform_id WHERE p.platform_id IS NULL")
    checks.append(("Every fact row has a platform", 0, int(orphans[0][0])))
    return checks


def core_questions(connection):
    """Return (question, sql, expected, actual) for each core question."""
    results = []
    for question, sql, expected in CORE_QUESTIONS:
        _, rows = db.query(connection, sql)
        actual = [[plain(value) for value in row] for row in rows]
        results.append((question, sql, expected, actual))
    return results


def explain(connection, sql):
    """Return the planner's text plan for `sql`."""
    _, rows = db.query(connection, f"EXPLAIN {sql}")
    return "\n".join(str(row[0]) for row in rows)


def plan_facts(plan):
    """Return the lines of a plan that show pruning and rewriting."""
    keep = ("partitions=", "TABLE:", "rollup:", "MaterializedView")
    return [line.strip() for line in plan.splitlines()
            if any(word in line for word in keep)]
