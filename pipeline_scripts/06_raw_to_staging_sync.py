#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 28 23:23:36 2025

@author: abriah
"""

"""
Online Retail II – Incremental Data Pipeline

This script implements an end-to-end RAW → STAGING pipeline:

1. RAW synchronization (incremental ingestion)
   - Loads CSV files into a temporary table
   - Inserts only new rows into raw.online_retail
   - Prevents duplicate ingestion across runs

2. STAGING refresh (clean, rebuildable layer)
   - Rebuilds staging.online_retail_clean from raw
   - Applies data-quality and business rules
   - Ensures analytics always query a clean dataset

Designed to be:
- Idempotent
- Incremental
- Airflow-ready
"""

import os
from pathlib import Path

import psycopg2


# -------------------------------------------------------------------
# Project root (avoid hardcoded /Users/... paths)
# -------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# -------------------------------------------------------------------
# Source CSV files to be synchronized into raw.online_retail.
# Additional files can be appended to this list over time.
# Uses project-relative paths (portable + GitHub-safe).
# -------------------------------------------------------------------
RAW_SOURCE_FILES = [
    str(PROJECT_ROOT / "Year_2009-2010_online_retail_II.csv"),
    str(PROJECT_ROOT / "Year_2010-2011_online_retail_II.csv"),
]


# -------------------------------------------------------------------
# PostgreSQL connection configuration
# (loaded from environment variables; keeps secrets out of code)
# -------------------------------------------------------------------
def get_database_config():
    """
    Load DB config from environment variables (set via .env).
    Keeps secrets out of code/GitHub.
    """
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB", "Online-Retail-II"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def create_temp_raw_load_table(db_connection):
    """
    Creates a session-scoped temporary table used as a loading buffer
    during RAW synchronization.

    The table exists only for the lifetime of the database connection
    and is automatically dropped at transaction commit.
    """
    with db_connection.cursor() as db_cursor:
        db_cursor.execute("""
            CREATE TEMP TABLE IF NOT EXISTS tmp_online_retail_load (
                invoice      TEXT,
                stockcode    TEXT,
                description  TEXT,
                quantity     INTEGER,
                invoicedate  TIMESTAMP,
                price        NUMERIC(12,2),
                customer_id  INTEGER,
                country      TEXT
            ) ON COMMIT DROP;
        """)


def sync_raw_table_from_csv(db_connection, csv_file_path):
    """
    Synchronizes a single CSV file into raw.online_retail.

    Process:
    1. Load CSV into a temporary table
    2. Compare temporary rows against raw.online_retail
    3. Insert only rows that do not already exist

    This ensures incremental ingestion without duplication.
    """
    if not os.path.exists(csv_file_path):
        raise FileNotFoundError(f"Source CSV not found: {csv_file_path}")

    with db_connection.cursor() as db_cursor:
        # Reset the temporary buffer before loading a new file
        db_cursor.execute("TRUNCATE TABLE tmp_online_retail_load;")

        # Client-side COPY: Python reads the file and streams it to PostgreSQL
        copy_sql = """
            COPY tmp_online_retail_load (
                invoice,
                stockcode,
                description,
                quantity,
                invoicedate,
                price,
                customer_id,
                country
            )
            FROM STDIN WITH (FORMAT csv, HEADER true);
        """

        with open(csv_file_path, "r", encoding="utf-8") as csv_file:
            db_cursor.copy_expert(copy_sql, csv_file)

        # Insert only new records into RAW
        db_cursor.execute("""
            INSERT INTO raw.online_retail (
                invoice,
                stockcode,
                description,
                quantity,
                invoicedate,
                price,
                customer_id,
                country
            )
            SELECT
                t.invoice,
                t.stockcode,
                t.description,
                t.quantity,
                t.invoicedate,
                t.price,
                t.customer_id,
                t.country
            FROM tmp_online_retail_load t
            WHERE NOT EXISTS (
                SELECT 1
                FROM raw.online_retail r
                WHERE r.invoice = t.invoice
                  AND r.stockcode = t.stockcode
                  AND r.invoicedate = t.invoicedate
                  AND r.quantity = t.quantity
                  AND r.price = t.price
                  AND COALESCE(r.customer_id, -1) = COALESCE(t.customer_id, -1)
                  AND r.country = t.country
                  AND COALESCE(r.description, '') = COALESCE(t.description, '')
            );
        """)

        return db_cursor.rowcount


def rebuild_staging_table(db_connection):
    """
    Rebuilds staging.online_retail_clean from raw.online_retail.

    Applied rules:
    - Trim whitespace from descriptions
    - Remove negative prices
    - Exclude non-product rows (stockcode 'M', BANK CHARGES, AMAZONFEE)
    - Compute total_price = quantity * price

    The staging layer is rebuildable by design.
    """
    with db_connection.cursor() as db_cursor:
        db_cursor.execute("TRUNCATE TABLE staging.online_retail_clean;")

        db_cursor.execute("""
            INSERT INTO staging.online_retail_clean (
                id,
                invoice,
                stockcode,
                description,
                quantity,
                invoicedate,
                price,
                customer_id,
                country,
                total_price
            )
            SELECT
                id,
                invoice,
                stockcode,
                TRIM(description) AS description,
                quantity,
                invoicedate,
                price,
                customer_id,
                country,
                quantity * price AS total_price
            FROM raw.online_retail
            WHERE quantity IS NOT NULL
              AND price IS NOT NULL
              AND price >= 0
              AND stockcode <> 'M'
              AND COALESCE(description, '') NOT IN ('BANK CHARGES', 'AMAZONFEE');
        """)


def main():
    db_connection = None
    try:
        database_config = get_database_config()

        # Fail fast (prevents "hang forever" if password isn't being passed)
        if not database_config.get("password"):
            raise ValueError(
                "POSTGRES_PASSWORD is not set. Load your .env before running "
                "(or pass env vars via Airflow task env=...)."
            )

        db_connection = psycopg2.connect(**database_config)
        db_connection.autocommit = False

        # Initialize the temporary load table once per session
        create_temp_raw_load_table(db_connection)

        # ---------------- RAW SYNC ----------------
        total_inserted_rows = 0
        for source_file in RAW_SOURCE_FILES:
            inserted_rows = sync_raw_table_from_csv(db_connection, source_file)
            total_inserted_rows += inserted_rows
            print(f"RAW sync: inserted {inserted_rows} new rows from {os.path.basename(source_file)}")

        # ---------------- STAGING REFRESH ----------------
        rebuild_staging_table(db_connection)

        db_connection.commit()
        print(f"Done. Total new RAW rows inserted: {total_inserted_rows}")
        print("Staging load completed successfully.")

    except Exception as pipeline_error:
        if db_connection:
            db_connection.rollback()
        print("Pipeline failed:", pipeline_error)
        raise  # important so Airflow marks the task as failed

    finally:
        if db_connection:
            db_connection.close()


if __name__ == "__main__":
    main()