-- ============================================================
-- 07_build_analytics_model.sql
-- Online Retail II — Analytics Layer (Star Schema)
--
-- This file includes EVERYTHING used to build analytics:
-- 1) Create analytics schema + tables (dim + fact)
-- 2) Load dims + fact from staging.online_retail_clean (rebuildable)
-- 3) Validation checks (row counts + revenue sanity)
--
-- How to use:
-- - Run this file after staging.online_retail_clean is populated.
-- - The load section TRUNCATES analytics tables to avoid duplicates.
-- ============================================================


-- ============================================================
-- STEP 1) Create analytics schema
-- Purpose: keep analysis-ready tables separate from raw and staging.
-- ============================================================
CREATE SCHEMA IF NOT EXISTS analytics;


-- ============================================================
-- STEP 2) Create dimension tables
-- Purpose: define stable reference tables used for group-bys and joins.
-- ============================================================

-- 2.1 dim_date
-- Purpose: one row per calendar date + date attributes for time analysis.
CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_key     int PRIMARY KEY,          -- YYYYMMDD
    full_date    date NOT NULL UNIQUE,
    day          int NOT NULL,
    day_of_week  int NOT NULL,             -- 1=Monday; 7=Sunday (ISO)
    day_name     text NOT NULL,
    week_of_year int NOT NULL,
    quarter      int NOT NULL,
    month        int NOT NULL,
    month_name   text NOT NULL,
    year         int NOT NULL
);

-- 2.2 dim_country
-- Purpose: normalize country names and generate a numeric key for joins.
CREATE TABLE IF NOT EXISTS analytics.dim_country (
    country_id bigserial PRIMARY KEY,
    country    text NOT NULL UNIQUE
);

-- 2.3 dim_product
-- Purpose: one row per product (stockcode) for consistent product reporting.
CREATE TABLE IF NOT EXISTS analytics.dim_product (
    stockcode    text PRIMARY KEY,
    product_name text
);

-- 2.4 dim_customer
-- Purpose: one row per known customer + first/last activity dates.
CREATE TABLE IF NOT EXISTS analytics.dim_customer (
    customer_id     integer PRIMARY KEY,
    first_seen_date date,
    last_seen_date  date
);


-- ============================================================
-- STEP 3) Create fact table
-- Purpose: store invoice-line transactions linked to dimensions.
-- ============================================================
CREATE TABLE IF NOT EXISTS analytics.fact_sales (
    fact_id     bigserial PRIMARY KEY,

    -- Natural identifiers from the dataset
    invoice     text NOT NULL,
    stockcode   text NOT NULL,
    customer_id integer,

    -- Dimension keys
    country_id  bigint NOT NULL,
    date_key    int NOT NULL,

    -- Measures
    quantity    int NOT NULL,
    price       numeric(12,2) NOT NULL,
    total_price numeric(14,2) NOT NULL,

    -- Timestamp retained for time-of-day analysis
    invoice_ts  timestamp NOT NULL,

    -- Foreign keys ensure facts connect to valid dimensions
    CONSTRAINT fk_fact_date     FOREIGN KEY (date_key)    REFERENCES analytics.dim_date(date_key),
    CONSTRAINT fk_fact_country  FOREIGN KEY (country_id)  REFERENCES analytics.dim_country(country_id),
    CONSTRAINT fk_fact_product  FOREIGN KEY (stockcode)   REFERENCES analytics.dim_product(stockcode),
    CONSTRAINT fk_fact_customer FOREIGN KEY (customer_id) REFERENCES analytics.dim_customer(customer_id)
);

-- Performance indexes (optional but recommended)
CREATE INDEX IF NOT EXISTS idx_fact_sales_date_key ON analytics.fact_sales(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_invoice  ON analytics.fact_sales(invoice);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer ON analytics.fact_sales(customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_sales_stock    ON analytics.fact_sales(stockcode);
CREATE INDEX IF NOT EXISTS idx_fact_sales_country  ON analytics.fact_sales(country_id);


-- ============================================================
-- STEP 4) Load analytics tables from STAGING (rebuildable)
-- Purpose: keep analytics reproducible by rebuilding from staging.
-- ============================================================
BEGIN;

-- Rebuild strategy:
-- Clear all analytics tables together (avoids FK truncate errors)
TRUNCATE TABLE
  analytics.fact_sales,
  analytics.dim_country,
  analytics.dim_product,
  analytics.dim_customer,
  analytics.dim_date
RESTART IDENTITY
CASCADE;


-- 4.1 Load dim_date
INSERT INTO analytics.dim_date (
    date_key,
    full_date,
    day,
    day_of_week,
    day_name,
    week_of_year,
    quarter,
    month,
    month_name,
    year
)
SELECT DISTINCT
    (EXTRACT(YEAR FROM invoicedate)::int * 10000 +
     EXTRACT(MONTH FROM invoicedate)::int * 100 +
     EXTRACT(DAY FROM invoicedate)::int)        AS date_key,
    invoicedate::date                            AS full_date,
    EXTRACT(DAY FROM invoicedate)::int           AS day,
    EXTRACT(ISODOW FROM invoicedate)::int        AS day_of_week,
    TRIM(TO_CHAR(invoicedate, 'Day'))            AS day_name,
    EXTRACT(WEEK FROM invoicedate)::int          AS week_of_year,
    EXTRACT(QUARTER FROM invoicedate)::int       AS quarter,
    EXTRACT(MONTH FROM invoicedate)::int         AS month,
    TRIM(TO_CHAR(invoicedate, 'Month'))          AS month_name,
    EXTRACT(YEAR FROM invoicedate)::int          AS year
FROM staging.online_retail_clean
WHERE invoicedate IS NOT NULL;


-- 4.2 Load dim_country
INSERT INTO analytics.dim_country (country)
SELECT DISTINCT TRIM(country) AS country
FROM staging.online_retail_clean
WHERE NULLIF(TRIM(country), '') IS NOT NULL
ORDER BY 1;


-- 4.3 Load dim_product
INSERT INTO analytics.dim_product (stockcode, product_name)
SELECT
    TRIM(stockcode) AS stockcode,
    MAX(NULLIF(description, '')) AS product_name
FROM staging.online_retail_clean
WHERE NULLIF(TRIM(stockcode), '') IS NOT NULL
GROUP BY TRIM(stockcode);


-- 4.4 Load dim_customer
INSERT INTO analytics.dim_customer (
    customer_id,
    first_seen_date,
    last_seen_date
)
SELECT
    customer_id,
    MIN(invoicedate::date) AS first_seen_date,
    MAX(invoicedate::date) AS last_seen_date
FROM staging.online_retail_clean
WHERE customer_id IS NOT NULL
GROUP BY customer_id;


-- 4.5 Load fact_sales
INSERT INTO analytics.fact_sales (
    invoice,
    stockcode,
    customer_id,
    country_id,
    date_key,
    quantity,
    price,
    total_price,
    invoice_ts
)
SELECT
    s.invoice,
    TRIM(s.stockcode) AS stockcode,
    s.customer_id,
    c.country_id,
    (EXTRACT(YEAR FROM s.invoicedate)::int * 10000 +
     EXTRACT(MONTH FROM s.invoicedate)::int * 100 +
     EXTRACT(DAY FROM s.invoicedate)::int) AS date_key,
    s.quantity,
    s.price,
    s.total_price,
    s.invoicedate
FROM staging.online_retail_clean s
JOIN analytics.dim_country c
  ON c.country = TRIM(s.country)
WHERE s.invoice IS NOT NULL
  AND NULLIF(TRIM(s.stockcode), '') IS NOT NULL
  AND s.invoicedate IS NOT NULL
  AND NULLIF(TRIM(s.country), '') IS NOT NULL;

COMMIT;


-- ============================================================
-- STEP 5) Validation checks
-- Purpose: confirm the analytics layer loaded correctly.
-- ============================================================

-- 5.1 Staging vs Fact row counts (fact_rows should be <= staging_rows if some rows excluded)
SELECT
  (SELECT COUNT(*) FROM staging.online_retail_clean) AS staging_rows,
  (SELECT COUNT(*) FROM analytics.fact_sales)        AS fact_rows;

-- 5.2 Dimension row counts
SELECT
  (SELECT COUNT(*) FROM analytics.dim_date)     AS dim_date_rows,
  (SELECT COUNT(*) FROM analytics.dim_country)  AS dim_country_rows,
  (SELECT COUNT(*) FROM analytics.dim_product)  AS dim_product_rows,
  (SELECT COUNT(*) FROM analytics.dim_customer) AS dim_customer_rows;

-- 5.3 Revenue sanity check (net revenue includes returns)
SELECT ROUND(SUM(total_price), 2) AS net_revenue
FROM analytics.fact_sales;
