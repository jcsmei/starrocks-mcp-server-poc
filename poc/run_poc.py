"""Run the whole PoC against a running StarRocks, and report on it.

Steps, in order: create the schema and views, load the workbooks,
check the data, capture query plans before and after the materialized
view, create the read-only agent user, answer the core questions as
that user, and use the official MCP server as an agent would.

The report is written to `results/summary.md` and, in GitHub Actions,
to the run's summary page.  The script exits with an error if any
check fails, so the build fails with it.
"""

import os
import sys
import time
from pathlib import Path

import checks
import db
import load
import mcp_check

RESULTS = Path(__file__).parent.parent / "results"


def table(header, rows):
    """Return a Markdown table."""
    lines = ["| " + " | ".join(header) + " |",
             "|" + "---|" * len(header)]
    # Cells are kept on one line, or the table breaks.
    lines += ["| " + " | ".join(" ".join(str(cell).split())
                                .replace("|", "\\|")
                                for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def main():
    report, failures = [], []
    started = time.monotonic()

    db.wait_until_ready()
    with db.connect() as admin:
        _, version = db.query(admin, "SELECT current_version()")
        report.append(f"# StarRocks PoC results\n\nStarRocks "
                      f"{version[0][0]}, run in "
                      f"{os.environ.get('RUN_PLACE', 'a local container')}.")

        db.run_file(admin, "01_schema.sql")
        admin.select_db(db.DATABASE)
        db.run_file(admin, "02_views.sql")

        rows, tables, loads = load.load_all()
        report.append("## Load\n\n" + table(
            ["Table", "Label", "Stream Load status", "Rows loaded"],
            [[item["table"], item["label"], item["status"], item["rows"]]
             for item in loads]))

        quality = checks.data_quality(admin, rows)
        failures += [name for name, want, got in quality if want != got]
        report.append("## Data quality\n\n" + table(
            ["Check", "Expected", "Actual", "Result"],
            [[n, w, g, "pass" if w == g else "**FAIL**"]
             for n, w, g in quality]))

        unfiltered = checks.STATUS_COUNTS.format(where="")
        one_date = checks.STATUS_COUNTS.format(
            where="WHERE report_date = '2025-10-26'")
        plans = [("No date filter, before the materialized view",
                  checks.explain(admin, unfiltered)),
                 ("One date, before the materialized view",
                  checks.explain(admin, one_date))]

        db.run_file(admin, "03_materialized_view.sql")
        db.query(admin, "REFRESH MATERIALIZED VIEW mv_status_counts "
                        "WITH SYNC MODE")
        plans.append(("One date, after the materialized view",
                      checks.explain(admin, one_date)))
        sections = []
        for title, plan in plans:
            facts = "\n".join(checks.plan_facts(plan)) or "(none found)"
            sections.append(f"**{title}**\n\n```\n{facts}\n```")
        report.append("## Query plans\n\nThe lines of each plan that "
                      "show partition pruning and materialized view "
                      "rewriting.\n\n" + "\n\n".join(sections))
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "plans.txt").write_text("\n\n".join(
            f"== {title} ==\n{plan}" for title, plan in plans))

        db.run_file(admin, "04_agent_access.sql")

    with db.connect(db.AGENT_USER, db.AGENT_PASSWORD, db.DATABASE) as agent:
        answers = checks.core_questions(agent)
    failures += [q for q, _, want, got in answers if want != got]
    report.append("## Core questions, asked as the read-only agent user\n\n"
                  + table(["Question", "Expected", "Actual", "Result"],
                          [[q, w, g, "pass" if w == g else "**FAIL**"]
                           for q, _, w, g in answers]))

    steps = mcp_check.mcp_checks()
    failures += [step for step, outcome, _ in steps
                 if outcome not in ("ok", "refused")]
    report.append("## The official StarRocks MCP server, as the agent "
                  "user\n\n" + table(["Step", "Outcome", "Detail"], steps))

    report.append(f"Finished in {time.monotonic() - started:.0f} s. "
                  + ("All checks passed." if not failures
                     else f"**{len(failures)} check(s) failed.**"))
    text = "\n\n".join(report) + "\n"
    (RESULTS / "summary.md").write_text(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write(text)
    print(text)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
