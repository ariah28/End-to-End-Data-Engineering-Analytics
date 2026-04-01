#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb 21 16:30:32 2026

@author: abriah
"""


import os
from pathlib import Path
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator


# -------------------------------------------------------------------
# Postgres config (loaded from environment variables; keeps secrets out of code)
# -------------------------------------------------------------------
Postgres_Host = os.getenv("POSTGRES_HOST", "localhost")
Postgres_Port = os.getenv("POSTGRES_PORT", "5432")
Postgres_Database = os.getenv("POSTGRES_DB", "Online-Retail-II")
Postgres_User = os.getenv("POSTGRES_USER", "postgres")
Postgres_Password = os.getenv("POSTGRES_PASSWORD", "")


# -------------------------------------------------------------------
# psql path + project paths (no hardcoded /Users/... paths)
# -------------------------------------------------------------------
# Uses .env if provided; defaults to Homebrew path
PSQL = os.getenv("PSQL_PATH", "/opt/homebrew/bin/psql")

# Infer project root from this DAG location:
# .../airflow/dags/... -> project root is 2 levels up
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])

PYTHON_BIN = f"{PROJECT_ROOT}/airflow_env/bin/python"

WAREHOUSE_SQL_DIR = f"{PROJECT_ROOT}/warehouse_sql"
PIPELINE_SCRIPTS_DIR = f"{PROJECT_ROOT}/pipeline_scripts"


# -------------------------------------------------------------------
# Common env for all tasks (prevents psql password prompts + keeps secrets out of bash_command)
# -------------------------------------------------------------------
COMMON_ENV = {
    "PROJECT_ROOT": PROJECT_ROOT,
    "POSTGRES_HOST": Postgres_Host,
    "POSTGRES_PORT": Postgres_Port,
    "POSTGRES_DB": Postgres_Database,
    "POSTGRES_USER": Postgres_User,
    "POSTGRES_PASSWORD": Postgres_Password,
    "PGPASSWORD": Postgres_Password,  # psql reads this
    "PSQL_PATH": PSQL,
}


default_args = {
    "owner": "Aksil Riah",
    "start_date": datetime(2025, 1, 7),
    "email": ["ariah2@uic.edu"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 4,
    "retry_delay": timedelta(minutes=3),
}

with DAG(
    dag_id="online_retail_data_pipeline_dag",
    default_args=default_args,
    schedule="@daily",
    catchup=False,
    description="End-to-end Online Retail II data pipeline",
) as dag:

    ######################################################################
    # Task 1: Create schemas
    ######################################################################

    create_schemas = BashOperator(
        task_id="01_create_schemas",
        bash_command=(
            f'export PGPASSWORD="{Postgres_Password}"; '
            f'"{PSQL}" -w '
            f'-h {Postgres_Host} -p {Postgres_Port} -U {Postgres_User} -d "{Postgres_Database}" '
            "-v ON_ERROR_STOP=1 "
            f'-f "{WAREHOUSE_SQL_DIR}/01_create_schemas.sql"'
        ),
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 2: Create raw online retail table
    ######################################################################

    create_raw_table = BashOperator(
        task_id="02_create_raw_online_retail_table",
        bash_command=(
            f'export PGPASSWORD="{Postgres_Password}"; '
            f'"{PSQL}" -w '
            f'-h {Postgres_Host} -p {Postgres_Port} -U {Postgres_User} -d "{Postgres_Database}" '
            "-v ON_ERROR_STOP=1 "
            f'-f "{WAREHOUSE_SQL_DIR}/02_create_raw_online_retail_table.sql"'
        ),
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 3: Raw data profiling checks
    ######################################################################

    raw_data_profiling = BashOperator(
        task_id="04_raw_data_profiling_checks",
        bash_command=(
            f'export PGPASSWORD="{Postgres_Password}"; '
            f'"{PSQL}" -w '
            f'-h {Postgres_Host} -p {Postgres_Port} -U {Postgres_User} -d "{Postgres_Database}" '
            "-v ON_ERROR_STOP=1 "
            f'-f "{WAREHOUSE_SQL_DIR}/04_raw_data_profiling_checks.sql"'
        ),
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 4: Raw → Staging sync (Python)
    ######################################################################

    raw_to_staging_sync = BashOperator(
        task_id="06_raw_to_staging_sync",
        bash_command=f'"{PYTHON_BIN}" "{PIPELINE_SCRIPTS_DIR}/06_raw_to_staging_sync.py"',
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 5: Staging validation checks
    ######################################################################

    staging_validation_checks = BashOperator(
        task_id="05_staging_validation_checks",
        bash_command=(
            f'export PGPASSWORD="{Postgres_Password}"; '
            f'"{PSQL}" -w '
            f'-h {Postgres_Host} -p {Postgres_Port} -U {Postgres_User} -d "{Postgres_Database}" '
            "-v ON_ERROR_STOP=1 "
            f'-f "{WAREHOUSE_SQL_DIR}/05_staging_validation_checks.sql"'
        ),
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 6: Build analytics model
    ######################################################################

    build_analytics_model = BashOperator(
        task_id="07_build_analytics_model",
        bash_command=(
            f'export PGPASSWORD="{Postgres_Password}"; '
            f'"{PSQL}" -w '
            f'-h {Postgres_Host} -p {Postgres_Port} -U {Postgres_User} -d "{Postgres_Database}" '
            "-v ON_ERROR_STOP=1 "
            f'-f "{WAREHOUSE_SQL_DIR}/07_build_analytics_model.sql"'
        ),
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 7: Analytics business queries
    ######################################################################

    analytics_business_queries = BashOperator(
        task_id="08_analytics_business_queries",
        bash_command=(
            f'export PGPASSWORD="{Postgres_Password}"; '
            f'"{PSQL}" -w '
            f'-h {Postgres_Host} -p {Postgres_Port} -U {Postgres_User} -d "{Postgres_Database}" '
            "-v ON_ERROR_STOP=1 "
            f'-f "{WAREHOUSE_SQL_DIR}/08_analytics_business_queries.sql"'
        ),
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 8: Generate analytics visualizations (data-aware)
    ######################################################################

    generate_visuals = BashOperator(
        task_id="09_generate_visuals_if_changed",
        bash_command=f'"{PYTHON_BIN}" "{PIPELINE_SCRIPTS_DIR}/generate_visuals.py"',
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 9: Q4 statistics (Postgres-based)
    ######################################################################

    q4_statistics = BashOperator(
        task_id="10_q4_statistics",
        bash_command=f'"{PYTHON_BIN}" "{PIPELINE_SCRIPTS_DIR}/09_statistics_from_csv_q4_test.py"',
        env=COMMON_ENV,
    )

    ######################################################################
    # Task 10: Q4 regression (Postgres-based)
    ######################################################################

    q4_regression = BashOperator(
        task_id="11_q4_regression_with_order_cont",
        bash_command=f'"{PYTHON_BIN}" "{PIPELINE_SCRIPTS_DIR}/10_q4_regression_with_order_control.py"',
        env=COMMON_ENV,
    )

    ######################################################################
    # Dependencies
    ######################################################################

    (
        create_schemas
        >> create_raw_table
        >> raw_data_profiling
        >> raw_to_staging_sync
        >> staging_validation_checks
        >> build_analytics_model
        >> analytics_business_queries
        >> generate_visuals
        >> q4_statistics
        >> q4_regression
    )