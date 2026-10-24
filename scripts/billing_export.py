"""Export tag-filtered Lab 5 Cloud Billing rows from BigQuery to CSV."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


TABLE_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")


def build_query(table: str) -> str:
    """Build the parameterized query; only the validated table identifier is interpolated."""
    if not TABLE_RE.fullmatch(table):
        raise ValueError(f"Invalid BigQuery table identifier: {table!r}")
    return f"""
SELECT
  invoice.month AS invoice_month,
  service.description AS service,
  sku.description AS sku,
  currency,
  ROUND(SUM(cost), 6) AS usage_cost,
  ROUND(SUM(IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit), 0)), 6)
    AS credits,
  ROUND(SUM(cost) +
    SUM(IFNULL((SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit), 0)), 6)
    AS net_cost
FROM `{table}`
WHERE project.id = @project_id
  AND EXISTS (
    SELECT 1 FROM UNNEST(labels) AS label
    WHERE label.key = 'course' AND label.value = 'itcs355'
  )
  AND EXISTS (
    SELECT 1 FROM UNNEST(labels) AS label
    WHERE label.key = 'lab' AND label.value = '5'
  )
GROUP BY invoice_month, service, sku, currency
ORDER BY invoice_month, service, sku
""".strip()


def find_standard_export_table(client, project: str, dataset: str) -> str:
    tables = sorted(
        table.table_id
        for table in client.list_tables(f"{project}.{dataset}")
        if table.table_id.startswith("gcp_billing_export_v1_")
    )
    if not tables:
        raise RuntimeError(
            "No standard Cloud Billing export table exists yet. Enable Standard usage cost "
            "export in the Billing console, then wait several hours for the first load."
        )
    return f"{project}.{dataset}.{tables[-1]}"


def write_csv(rows, out: Path) -> tuple[float, float]:
    fields = [
        "invoice_month", "service", "sku", "currency",
        "usage_cost", "credits", "net_cost",
    ]
    materialized = [{field: row[field] for field in fields} for row in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(materialized)
    return (
        sum(float(row["usage_cost"] or 0) for row in materialized),
        sum(float(row["credits"] or 0) for row in materialized),
    )


def main() -> int:
    from google.cloud import bigquery

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--dataset", default="itcs355_billing")
    ap.add_argument("--table", help="fully qualified table; discovered when omitted")
    ap.add_argument("--out", type=Path, default=Path("reports/lab5/billing.csv"))
    args = ap.parse_args()

    client = bigquery.Client(project=args.project)
    table = args.table or find_standard_export_table(client, args.project, args.dataset)
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("project_id", "STRING", args.project),
    ])
    rows = client.query(build_query(table), job_config=job_config).result()
    usage, credits = write_csv(rows, args.out)
    print(f"wrote {args.out}")
    print(f"tag-filtered usage={usage:.6f}, credits={credits:.6f}, net={usage + credits:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
