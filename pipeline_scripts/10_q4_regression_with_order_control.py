#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 21 16:00:13 2026

@author: abriah

Goal:
- Run a simple regression using DAILY data from Postgres (NO CSV reads)
- Dependent variable: daily_revenue
- Independent variables:
    1) is_q4 (1 if month in Oct/Nov/Dec else 0)
    2) daily_orders (control variable)

Model:
  daily_revenue ~ is_q4 + daily_orders

Outputs:
- Prints OLS summary
- Saves a CSV of the modeling dataset into analytics/outputs/modeling
"""

from __future__ import annotations

import os
import math
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2


# ----------------------------
# Config
# ----------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = PROJECT_ROOT / "analytics" / "outputs" / "modeling"
DATASET_OUTFILE = OUTPUT_DIR / "q4_regression_dataset_daily.csv"


# ----------------------------
# Minimal .env loader (no external deps)
# ----------------------------
def load_env_file(env_path: Path) -> None:
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


# ----------------------------
# Postgres pull (daily dataset)
# ----------------------------
def fetch_daily_dataset(conn) -> pd.DataFrame:
    # IMPORTANT: your analytics.fact_sales has column "invoice" (not invoice_no)
    sql = """
        SELECT
            d.full_date AS order_date,
            SUM(f.total_price) AS daily_revenue,
            COUNT(DISTINCT f.invoice) AS daily_orders,
            CASE
                WHEN EXTRACT(MONTH FROM d.full_date) IN (10, 11, 12) THEN 1
                ELSE 0
            END AS is_q4
        FROM analytics.fact_sales f
        JOIN analytics.dim_date d
          ON d.date_key = f.date_key
        GROUP BY d.full_date
        ORDER BY d.full_date;
    """
    df = pd.read_sql_query(sql, conn)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["daily_revenue"] = pd.to_numeric(df["daily_revenue"], errors="coerce").fillna(0.0)
    df["daily_orders"] = pd.to_numeric(df["daily_orders"], errors="coerce").fillna(0).astype(int)
    df["is_q4"] = pd.to_numeric(df["is_q4"], errors="coerce").fillna(0).astype(int)
    return df


# ----------------------------
# Regression (NumPy OLS)
# ----------------------------
def run_regression(df: pd.DataFrame) -> None:
    """
    NumPy-based OLS (no statsmodels / scipy).
    Model: daily_revenue ~ 1 + is_q4 + daily_orders
    """
    df = df.dropna(subset=["daily_revenue", "is_q4", "daily_orders"]).copy()

    # y and X (with intercept)
    y = df["daily_revenue"].astype(float).to_numpy().reshape(-1, 1)
    x_is_q4 = df[["is_q4"]].astype(float).to_numpy()
    x_orders = df[["daily_orders"]].astype(float).to_numpy()
    X = np.hstack([np.ones((len(df), 1)), x_is_q4, x_orders])  # [1, is_q4, daily_orders]

    n, k = X.shape  # k=3
    if n <= k:
        raise ValueError(f"Not enough observations to fit model: n={n}, k={k}")

    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError as e:
        raise ValueError("X'X is singular; regression cannot be estimated (collinearity).") from e

    beta = XtX_inv @ (X.T @ y)  # (k,1)
    y_hat = X @ beta
    resid = y - y_hat

    df_resid = n - k
    sse = float((resid.T @ resid)[0, 0])
    y_mean = float(y.mean())
    sst = float(((y - y_mean).T @ (y - y_mean))[0, 0])
    r2 = 1.0 - (sse / sst) if sst > 0 else float("nan")
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / df_resid if np.isfinite(r2) else float("nan")

    # Standard errors (classic OLS)
    sigma2 = sse / df_resid
    cov_beta = sigma2 * XtX_inv
    se_beta = np.sqrt(np.diag(cov_beta)).reshape(-1, 1)
    t_stats = beta / se_beta  # (k,1)

    # Normal-approx p-values (no SciPy)
    def normal_cdf(z: float) -> float:
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    def pval_two_sided(t: float) -> float:
        if not math.isfinite(t):
            return float("nan")
        return 2.0 * (1.0 - normal_cdf(abs(t)))

    # ✅ FIX: flatten t_stats so each t is a scalar (prevents float(array) TypeError)
    p_vals = np.array([pval_two_sided(float(t)) for t in t_stats.flatten()]).reshape(-1, 1)

    terms = ["const", "is_q4", "daily_orders"]

    print("\n✅ Q4 Regression (Postgres-based | NumPy OLS)")
    print("Model: daily_revenue ~ is_q4 + daily_orders")
    print(f"Observations (n): {n}")
    print(f"R-squared: {r2:.4f}" if np.isfinite(r2) else "R-squared: NA")
    print(f"Adj. R-squared: {adj_r2:.4f}" if np.isfinite(adj_r2) else "Adj. R-squared: NA")

    print("\nCoefficients (Normal-approx p-values):")
    header = f"{'term':<14}{'coef':>14}{'std err':>14}{'t':>12}{'p>|t|':>12}"
    print(header)

    for i, term in enumerate(terms):
        coef = float(beta[i, 0])
        se = float(se_beta[i, 0])
        t = float(t_stats[i, 0])
        p = float(p_vals[i, 0])
        print(f"{term:<14}{coef:>14,.4f}{se:>14,.4f}{t:>12.4f}{p:>12.6g}")

    print("\nKey coefficients:")
    print(f"  is_q4: {float(beta[1, 0]):,.4f}")
    print(f"  daily_orders: {float(beta[2, 0]):,.4f}")


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    load_env_file(PROJECT_ROOT / ".env")
    cfg = get_database_config()

    # Ensure output folder exists (important in Airflow)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with psycopg2.connect(**cfg) as conn:
        df = fetch_daily_dataset(conn)

    df.to_csv(DATASET_OUTFILE, index=False)
    print(f"\nSaved dataset: {DATASET_OUTFILE}")

    run_regression(df)


if __name__ == "__main__":
    main()