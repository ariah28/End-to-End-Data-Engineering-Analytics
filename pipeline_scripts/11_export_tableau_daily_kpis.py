
#!/usr/bin/env python3
"""
11_export_tableau_daily_kpis.py

Exports a Tableau-ready (file-based) dataset from the analytics star schema.

Why this exists:
- Tableau Public does NOT support live PostgreSQL connections.
- We generate a curated, denormalized BI dataset (daily KPIs) as a CSV.
- Airflow can run this after the analytics model build, so the CSV updates automatically.

Output:
- analytics/outputs/tableau/tableau_daily_kpis.csv
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg2


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def main() -> None:
    # --- DB connection (same env vars you already use in your pipeline) ---
    host = _require_env("POSTGRES_HOST")
    port = _require_env("POSTGRES_PORT")
    db = _require_env("POSTGRES_DB")
    user = _require_env("POSTGRES_USER")
    pwd = _require_env("POSTGRES_PASSWORD")

    # --- Output path ---
    project_root = Path(__file__).resolve().parents[1]  # End-to-End-Data-Engi-Analy-Pro/
    out_dir = project_root / "analytics" / "outputs" / "tableau"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "tableau_daily_kpis.csv"

    # --- Query: daily KPIs (aggregated, fast for Tableau Public) ---
    # IMPORTANT: Your analytics.fact_sales uses total_price (not revenue).
    sql = """
    SELECT
        d.full_date                                AS full_date,
        d.year                                     AS year,
        d.month                                    AS month,
        d.month_name                               AS month_name,
        c.country                                  AS country,

        COUNT(DISTINCT f.invoice)                  AS daily_orders,

        -- gross revenue: sum of positive total_price
        SUM(CASE WHEN f.total_price > 0 THEN f.total_price ELSE 0 END) AS gross_revenue,

        -- returns revenue: sum of negative total_price (kept negative for clarity)
        SUM(CASE WHEN f.total_price < 0 THEN f.total_price ELSE 0 END) AS returns_revenue,

        -- net revenue: full sum
        SUM(f.total_price)                         AS net_revenue,

        CASE
            WHEN d.quarter = 4 THEN 1
            ELSE 0
        END                                        AS is_q4

    FROM analytics.fact_sales f
    JOIN analytics.dim_date d
        ON f.date_key = d.date_key
    JOIN analytics.dim_country c
        ON f.country_id = c.country_id

    GROUP BY
        d.full_date, d.year, d.month, d.month_name, d.quarter, c.country
    ORDER BY
        d.full_date, c.country;
    """

    # --- Execute ---
    conn = psycopg2.connect(
        host=host,
        port=int(port),
        dbname=db,
        user=user,
        password=pwd,
    )
    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        conn.close()

    # --- Save ---
    df.to_csv(out_path, index=False)

    print(f"[OK] Wrote {len(df):,} rows to: {out_path}")


if __name__ == "__main__":
    main()
