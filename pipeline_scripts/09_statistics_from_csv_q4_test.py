#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 21 15:53:17 2026

@author: abriah

09_statistics_from_csv_q4_test.py 

Goal:
- Run two Welch t-tests using DAILY data from Postgres (NO CSV reads)
  1) Daily Revenue: Q4 vs Non-Q4
  2) Daily Return Rate: Q4 vs Non-Q4

Data source (analytics layer):
- analytics.fact_sales
- analytics.dim_date

Outputs:
- Prints test results
- Saves a small TXT report into analytics/outputs/modeling
"""

from __future__ import annotations

import os
import math
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "analytics" / "outputs" / "modeling"
REPORT_OUTFILE = OUTPUT_DIR / "q4_stats_tests_report.txt"

ALPHA = 0.05
CONF_LEVEL = 0.95


def load_env_file(env_path: Path) -> None:
    """Lightweight .env loader so the script can run under BashOperator."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_database_config() -> dict:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB", "Online-Retail-II"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def normal_cdf(z: float) -> float:
    """Standard normal CDF using erf (no SciPy)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def z_critical(conf_level: float) -> float:
    """
    Critical value for two-sided Normal CI.
    This script is designed for CONF_LEVEL=0.95 by default.
    If you keep CONF_LEVEL at 0.95, z=1.96 is standard.
    """
    # Common levels hardcoded to avoid needing SciPy:
    common = {
        0.90: 1.6448536269514722,
        0.95: 1.959963984540054,
        0.99: 2.5758293035489004,
    }
    if conf_level in common:
        return common[conf_level]

    # Fallback: default to 1.96 if custom conf_level is used
    # (keeps script robust inside minimal Airflow env).
    return 1.959963984540054


def welch_df(x: np.ndarray, y: np.ndarray) -> float:
    """Welch–Satterthwaite effective degrees of freedom (reported for reference)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    nx, ny = x.size, y.size
    vx, vy = x.var(ddof=1), y.var(ddof=1)

    num = (vx / nx + vy / ny) ** 2
    den = (vx**2) / (nx**2 * (nx - 1)) + (vy**2) / (ny**2 * (ny - 1))
    return float(num / den)


def diff_ci_approx_normal(x: np.ndarray, y: np.ndarray, conf_level: float = 0.95) -> tuple[float, float]:
    """
    Confidence interval for mean difference using Normal approximation:
    diff ± zcrit * SE
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    nx, ny = x.size, y.size
    mx, my = x.mean(), y.mean()
    vx, vy = x.var(ddof=1), y.var(ddof=1)

    diff = mx - my
    se = math.sqrt(vx / nx + vy / ny)

    zcrit = z_critical(conf_level)
    return float(diff - zcrit * se), float(diff + zcrit * se)


def split_q4_nonq4(dates: pd.Series, values: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    dts = pd.to_datetime(dates)
    months = dts.dt.month
    q4 = values[months.isin([10, 11, 12])].to_numpy(dtype=float)
    non_q4 = values[~months.isin([10, 11, 12])].to_numpy(dtype=float)
    return q4, non_q4


def fetch_daily_revenue(conn) -> pd.DataFrame:
    sql = """
        SELECT
            d.full_date AS order_date,
            SUM(f.total_price) AS revenue
        FROM analytics.fact_sales f
        JOIN analytics.dim_date d
          ON d.date_key = f.date_key
        GROUP BY d.full_date
        ORDER BY d.full_date;
    """
    df = pd.read_sql_query(sql, conn)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0)
    return df


def fetch_daily_return_rate(conn) -> pd.DataFrame:
    sql = """
        WITH daily AS (
            SELECT
                d.full_date AS order_date,
                SUM(CASE WHEN f.quantity > 0 THEN f.total_price ELSE 0 END) AS gross_revenue,
                ABS(SUM(CASE WHEN f.quantity < 0 THEN f.total_price ELSE 0 END)) AS returned_revenue_abs
            FROM analytics.fact_sales f
            JOIN analytics.dim_date d
              ON d.date_key = f.date_key
            GROUP BY d.full_date
        )
        SELECT
            order_date,
            CASE
                WHEN gross_revenue > 0 THEN (returned_revenue_abs / gross_revenue)
                ELSE NULL
            END AS return_rate
        FROM daily
        WHERE gross_revenue > 0
        ORDER BY order_date;
    """
    df = pd.read_sql_query(sql, conn)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["return_rate"] = pd.to_numeric(df["return_rate"], errors="coerce")
    df = df.dropna(subset=["return_rate"]).copy()
    return df


def welch_test_block(name: str, q4: np.ndarray, non_q4: np.ndarray, decimals: int = 2) -> str:
    if q4.size < 2 or non_q4.size < 2:
        raise ValueError(f"{name}: Need >=2 observations in each group.")

    q4 = np.asarray(q4, dtype=float)
    non_q4 = np.asarray(non_q4, dtype=float)

    n1, n2 = q4.size, non_q4.size
    m1, m2 = float(q4.mean()), float(non_q4.mean())
    v1, v2 = float(q4.var(ddof=1)), float(non_q4.var(ddof=1))

    diff = m1 - m2
    se = math.sqrt(v1 / n1 + v2 / n2)
    t_stat = diff / se if se > 0 else float("nan")

    # Two-sided p-value using Normal approximation (robust without SciPy)
    p_value = 2.0 * (1.0 - normal_cdf(abs(t_stat))) if math.isfinite(t_stat) else float("nan")

    df_eff = welch_df(q4, non_q4)
    ci_lo, ci_hi = diff_ci_approx_normal(q4, non_q4, conf_level=CONF_LEVEL)

    fmt = f"{{:,.{decimals}f}}"
    out = []
    out.append(f"=== {name} ===")
    out.append(f"n_q4={n1} | n_non_q4={n2}")
    out.append(f"mean_q4: {fmt.format(m1)}")
    out.append(f"mean_non_q4: {fmt.format(m2)}")
    out.append(f"diff (q4 - non_q4): {fmt.format(diff)}")
    out.append(f"t_stat (Welch): {t_stat:.4f}")
    out.append(f"p_value (Normal approx): {p_value:.6g}")
    out.append(f"significant (alpha={ALPHA}): {bool(p_value < ALPHA) if math.isfinite(p_value) else 'NA'}")
    out.append(f"df_eff (Welch-Satterthwaite): {df_eff:.2f}")
    out.append(f"{int(CONF_LEVEL*100)}% CI (diff, Normal approx): [{fmt.format(ci_lo)}, {fmt.format(ci_hi)}]")
    return "\n".join(out)


def main() -> None:
    load_env_file(PROJECT_ROOT / ".env")
    cfg = get_database_config()

    # Ensure output folder exists (important when running from Airflow)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with psycopg2.connect(**cfg) as conn:
        daily_rev = fetch_daily_revenue(conn)
        q4_rev, non_q4_rev = split_q4_nonq4(daily_rev["order_date"], daily_rev["revenue"])

        daily_rr = fetch_daily_return_rate(conn)
        q4_rr, non_q4_rr = split_q4_nonq4(daily_rr["order_date"], daily_rr["return_rate"])

    block1 = welch_test_block("TEST 1: Daily Revenue (Q4 vs Non-Q4)", q4_rev, non_q4_rev, decimals=2)
    block2 = welch_test_block("TEST 2: Daily Return Rate (Q4 vs Non-Q4)", q4_rr, non_q4_rr, decimals=4)

    report = "\n\n".join([block1, block2]) + "\n"

    print("\n" + report)
    REPORT_OUTFILE.write_text(report, encoding="utf-8")
    print(f"Saved report: {REPORT_OUTFILE}")


if __name__ == "__main__":
    main()