"""Turn the report workbooks into rows for the star schema, and load them.

Each workbook's tabs share their columns, but the three reports name
the same idea differently, so each report has a mapping to the fact
table's columns.  Loading uses Stream Load, StarRocks's HTTP batch
load.  Every load has a label built from its content, so retrying a
load that already succeeded is refused by StarRocks instead of
duplicating rows.
"""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import httpx
import openpyxl

import db

DATA_FOLDER = Path(__file__).parent.parent / "data"
FILE_PATTERN = re.compile(
    r"^(?P<report>[a-z_]+)_creatives_(?P<date>\d{4}-\d{2}-\d{2})\.xlsx$")

# Where each fact column comes from, per report.  None: not in that report.
COMMON = {
    "creative_name": "Creative Name", "campaign": "Campaign Name",
    "region": "Region", "impressions": "Impressions", "clicks": "Clicks",
    "media_cost": "Media Cost", "account": "Account",
    "channel_group": "Channel Group",
}
MAPPINGS = {
    "paid_social": {**COMMON, "creative_key": "Creative ID",
                    "status": "Creative ID Status",
                    "days_since_end": "Days Since Creative ID End Date",
                    "conversions": None},
    "site_direct": {**COMMON, "creative_key": "Creative Name",
                    "status": "Creative Status",
                    "days_since_end": "Days Since Creative End Date",
                    "conversions": None},
    "site_serve": {**COMMON, "creative_key": "Creative UID",
                   "status": "Creative UID Status",
                   "days_since_end": "Days Since UID End Date",
                   "conversions": "Total Conversions"},
}
STATUSES = {"Live", "Not Live", "Unknown"}


def workbook_files(folder=DATA_FOLDER):
    """Return (report, report_date, path) for every dated workbook."""
    found = []
    for path in sorted(folder.glob("*.xlsx")):
        match = FILE_PATTERN.match(path.name)
        if match and match["report"] in MAPPINGS:
            found.append((match["report"],
                          date.fromisoformat(match["date"]), path))
    return found


def read_rows(report, report_date, path):
    """Return one dict per creative in the workbook, from every tab."""
    mapping = MAPPINGS[report]
    rows = []
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in book.worksheets:
            values = list(sheet.iter_rows(values_only=True))
            header = [str(name) for name in values[0]]
            missing = [source for source in mapping.values()
                       if source and source not in header]
            if missing:
                raise ValueError(f"{path.name}, tab {sheet.title!r}: "
                                 f"missing columns {missing}")
            for raw in values[1:]:
                if not any(value is not None for value in raw):
                    continue
                cells = dict(zip(header, raw))
                row = {column: (cells[source] if source else None)
                       for column, source in mapping.items()}
                row.update(report=report, platform=sheet.title,
                           report_date=report_date.isoformat(),
                           source_file=path.name, source_tab=sheet.title)
                rows.append(row)
    finally:
        book.close()
    return rows


def build_tables(rows):
    """Split the workbook rows into the two dimensions and the fact."""
    platforms = sorted({(r["report"], r["platform"], r["channel_group"])
                        for r in rows})
    platform_ids = {(report, platform): number
                    for number, (report, platform, _) in
                    enumerate(platforms, start=1)}
    accounts = sorted({r["account"] for r in rows if r["account"]})
    account_ids = {name: number
                   for number, name in enumerate(accounts, start=1)}
    dim_platform = [{"platform_id": platform_ids[(report, platform)],
                     "report": report, "platform": platform,
                     "channel_group": channel_group}
                    for report, platform, channel_group in platforms]
    dim_account = [{"account_id": number, "account": name}
                   for name, number in account_ids.items()]
    fact = [{
        "report_date": r["report_date"],
        "platform_id": platform_ids[(r["report"], r["platform"])],
        "status": r["status"],
        "account_id": account_ids.get(r["account"]),
        "creative_key": str(r["creative_key"]),
        "creative_name": r["creative_name"], "campaign": r["campaign"],
        "region": r["region"], "days_since_end": r["days_since_end"],
        "impressions": r["impressions"], "clicks": r["clicks"],
        "conversions": r["conversions"], "media_cost": r["media_cost"],
        "source_file": r["source_file"], "source_tab": r["source_tab"],
    } for r in rows]
    return {"dim_platform": dim_platform, "dim_account": dim_account,
            "fact_creative": fact}


def stream_load(table, records):
    """Load `records` into `table` with Stream Load; return the result.

    The label is a hash of the content, so loading the same content
    twice is refused with "Label Already Exists" and nothing is
    duplicated.
    """
    body = json.dumps(records, default=str).encode()
    label = f"{table}_{hashlib.sha256(body).hexdigest()[:16]}"
    response = httpx.put(
        f"http://{db.HOST}:{db.LOAD_PORT}/api/{db.DATABASE}/{table}"
        "/_stream_load",
        content=body,
        auth=(db.ADMIN_USER, db.ADMIN_PASSWORD),
        headers={"label": label, "format": "json",
                 "strip_outer_array": "true"},
        timeout=60,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("Status") not in ("Success", "Label Already Exists"):
        raise RuntimeError(f"Stream Load into {table} failed: {result}")
    return {"table": table, "label": label, "status": result["Status"],
            "rows": result.get("NumberLoadedRows", 0)}


def load_all(folder=DATA_FOLDER):
    """Read every workbook, load the star schema; return what was done."""
    rows = []
    for report, report_date, path in workbook_files(folder):
        rows.extend(read_rows(report, report_date, path))
    tables = build_tables(rows)
    loads = [stream_load(name, records)
             for name, records in tables.items()]
    return rows, tables, loads
