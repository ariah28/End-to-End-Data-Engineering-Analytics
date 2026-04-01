#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan 15 21:40:53 2026

@author: abriah
"""

from __future__ import annotations

import os
import json
import shutil
from pathlib import Path
from datetime import datetime

import pandas as pd
import psycopg2
import matplotlib.pyplot as plt


# =========================
# Paths
# =========================
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).resolve().parents[1])))

FIGURES_DIR = PROJECT_ROOT / "analytics" / "outputs" / "figures"
VERSIONED_DIR = FIGURES_DIR / "versioned"
LATEST_DIR = FIGURES_DIR / "latest"
STATE_PATH = FIGURES_DIR / "_visuals_state.json"

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
VERSIONED_DIR.mkdir(parents=True, exist_ok=True)
LATEST_DIR.mkdir(parents=True, exist_ok=True)


# =========================
# DB
# =========================
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB   = os.getenv("POSTGRES_DB", "Online-Retail-II")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PW   = os.getenv("POSTGRES_PASSWORD", "")  

def get_conn():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PW,
    )

def qdf(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn)


# =========================
# Change detection + versioning
# =========================
def compute_data_signature(conn) -> dict:
    sql_signature = """
    SELECT
      MAX(d.full_date) AS max_date,
      COUNT(*) AS n_rows
    FROM analytics.fact_sales f
    JOIN analytics.dim_date d
      ON d.date_key = f.date_key;
    """
    row = qdf(conn, sql_signature).iloc[0]
    return {
        "max_date": str(row["max_date"]),
        "n_rows": int(row["n_rows"]),
    }

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_state(data_signature: dict, version: int) -> None:
    STATE_PATH.write_text(
        json.dumps(
            {
                "data_signature": data_signature,
                "version": version,
                "last_run_utc": datetime.utcnow().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

def next_version(state: dict) -> int:
    return int(state.get("version", 0)) + 1

def save_versioned_and_latest(fig_name: str, version: int) -> None:
    vpath = VERSIONED_DIR / f"{fig_name}_v{version}.png"
    lpath = LATEST_DIR / f"{fig_name}_latest.png"
    plt.savefig(vpath, dpi=150, bbox_inches="tight")
    shutil.copyfile(vpath, lpath)
    print("Saved:", vpath.name)
    print("Saved:", lpath.name)


# =========================
# Plots
# =========================
def plot_daily_revenue(conn, version: int) -> None:
    sql = """
    SELECT
      d.full_date AS date,
      ROUND(SUM(f.total_price), 2) AS revenue
    FROM analytics.fact_sales f
    JOIN analytics.dim_date d
      ON d.date_key = f.date_key
    GROUP BY d.full_date
    ORDER BY d.full_date;
    """
    df = qdf(conn, sql)

    plt.figure(figsize=(14, 6))
    plt.plot(df["date"], df["revenue"], linewidth=1)
    plt.title("Daily Revenue Over Time", fontsize=14)
    plt.xlabel("Date")
    plt.ylabel("Revenue")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    save_versioned_and_latest("daily_revenue_over_time", version)
    plt.close()

def plot_monthly_revenue(conn, version: int) -> None:
    sql = """
    SELECT
      DATE_TRUNC('month', d.full_date)::date AS month,
      ROUND(SUM(f.total_price), 2) AS revenue
    FROM analytics.fact_sales f
    JOIN analytics.dim_date d
      ON d.date_key = f.date_key
    GROUP BY 1
    ORDER BY 1;
    """
    df = qdf(conn, sql)

    plt.figure(figsize=(12, 5))
    plt.plot(df["month"], df["revenue"], linewidth=2)
    plt.title("Monthly Revenue Over Time", fontsize=14)
    plt.xlabel("Month")
    plt.ylabel("Revenue")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    save_versioned_and_latest("monthly_revenue_over_time", version)
    plt.close()

def plot_top_countries(conn, version: int) -> None:
    sql = """
    SELECT
      c.country,
      ROUND(SUM(f.total_price), 2) AS revenue
    FROM analytics.fact_sales f
    JOIN analytics.dim_country c
      ON c.country_id = f.country_id
    GROUP BY c.country
    ORDER BY revenue DESC
    LIMIT 10;
    """
    df = qdf(conn, sql)

    colors = [
        "#4CAF50", "#C44E52", "#4C72B0", "#DD8452", "#55A868",
        "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974"
    ]

    plt.figure(figsize=(10, 6))
    plt.barh(df["country"][::-1], df["revenue"][::-1], color=colors)

    for i, v in enumerate(df["revenue"][::-1]):
        plt.text(v, i, f"${v:,.0f}", va="center", ha="left", fontsize=10)

    plt.title("Top 10 Countries by Revenue", fontsize=14)
    plt.xlabel("Revenue")
    plt.ylabel("Country")
    plt.grid(axis="x", alpha=0.3)
    plt.tight_layout()

    save_versioned_and_latest("top_countries_by_revenue", version)
    plt.close()

def plot_top_products(conn, version: int) -> None:
    sql = """
    SELECT
      p.stockcode,
      COALESCE(NULLIF(TRIM(p.product_name), ''), '[No Description]') AS product_name,
      ROUND(SUM(f.total_price), 2) AS revenue
    FROM analytics.fact_sales f
    JOIN analytics.dim_product p
      ON p.stockcode = f.stockcode
    GROUP BY p.stockcode, p.product_name
    ORDER BY revenue DESC
    LIMIT 10;
    """
    df = qdf(conn, sql)

    df["label"] = df["stockcode"].astype(str) + " - " + df["product_name"].astype(str)

    colors = [
        "#4CAF50", "#C44E52", "#4C72B0", "#DD8452", "#55A868",
        "#8172B3", "#937860", "#DA8BC3", "#8C8C8C", "#CCB974"
    ]

    plt.figure(figsize=(12, 7))
    plt.barh(df["label"][::-1], df["revenue"][::-1], color=colors)

    for i, v in enumerate(df["revenue"][::-1]):
        plt.text(v, i, f"${v:,.0f}", va="center", ha="left", fontsize=9)

    plt.title("Top 10 Products by Revenue", fontsize=14)
    plt.xlabel("Revenue")
    plt.ylabel("Product (Stockcode - Name)")
    plt.grid(axis="x", alpha=0.3)
    plt.tight_layout()

    save_versioned_and_latest("top_products_by_revenue", version)
    plt.close()

def plot_revenue_breakdown(conn, version: int) -> None:
    sql = """
    SELECT
      ROUND(SUM(CASE WHEN quantity > 0 THEN total_price ELSE 0 END), 2) AS gross_sales,
      ROUND(SUM(CASE WHEN quantity < 0 THEN total_price ELSE 0 END), 2) AS returns,
      ROUND(SUM(total_price), 2) AS net_revenue
    FROM analytics.fact_sales;
    """
    df_returns = qdf(conn, sql)

    df_returns_plot = pd.DataFrame({
        "type": ["Gross Sales", "Returns", "Net Revenue"],
        "amount": [
            df_returns.loc[0, "gross_sales"],
            df_returns.loc[0, "returns"],
            df_returns.loc[0, "net_revenue"],
        ]
    })

    colors = ["#4CAF50", "#C44E52", "#4C72B0"]

    plt.figure(figsize=(8, 5))
    plt.bar(df_returns_plot["type"], df_returns_plot["amount"], color=colors)

    for i, v in enumerate(df_returns_plot["amount"]):
        plt.text(i, v, f"${v:,.0f}", ha="center", va="bottom", fontsize=10)

    plt.title("Revenue Breakdown: Gross Sales vs Returns vs Net Revenue", fontsize=14)
    plt.ylabel("Revenue")
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    save_versioned_and_latest("revenue_breakdown_gross_returns_net", version)
    plt.close()


# =========================
# Orchestrator
# =========================
def generate_visuals_if_changed() -> bool:
    """
    Returns True if visuals were generated, False if skipped.
    """
    with get_conn() as conn:
        new_sig = compute_data_signature(conn)
        state = load_state()

        if state.get("data_signature") == new_sig:
            print("No new data detected. Skipping visual generation.")
            return False

        version = next_version(state)
        print(f"New data detected. Generating visuals v{version}...")

        plot_daily_revenue(conn, version)
        plot_monthly_revenue(conn, version)
        plot_top_countries(conn, version)
        plot_top_products(conn, version)
        plot_revenue_breakdown(conn, version)

        save_state(new_sig, version)
        print("State saved.")
        return True


if __name__ == "__main__":
    generate_visuals_if_changed()
