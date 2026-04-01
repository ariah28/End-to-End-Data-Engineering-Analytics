-- ============================================================
-- analytics_business_queries.sql
-- Online Retail II — Portfolio Analytics Queries
-- These queries demonstrate how the analytics model is used
-- to answer business questions.
-- ============================================================


-- ============================================================
-- 1) Total revenue
-- Purpose: understand overall business performance.
-- ============================================================
SELECT ROUND(SUM(total_price), 2) AS total_revenue
FROM analytics.fact_sales;


-- ============================================================
-- 2) Revenue by year and month
-- Purpose: identify trends and seasonality.
-- ============================================================
SELECT
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(f.total_price), 2) AS monthly_revenue
FROM analytics.fact_sales f
JOIN analytics.dim_date d
  ON d.date_key = f.date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;


-- ============================================================
-- 3) Top 10 products by revenue
-- Purpose: identify best-selling products.
-- ============================================================
SELECT
    p.stockcode,
    p.product_name,
    ROUND(SUM(f.total_price), 2) AS product_revenue
FROM analytics.fact_sales f
JOIN analytics.dim_product p
  ON p.stockcode = f.stockcode
GROUP BY p.stockcode, p.product_name
ORDER BY product_revenue DESC
LIMIT 10;


-- ============================================================
-- 4) Top 10 customers by revenue
-- Purpose: identify high-value customers.
-- ============================================================
SELECT
    c.customer_id,
    ROUND(SUM(f.total_price), 2) AS customer_revenue
FROM analytics.fact_sales f
JOIN analytics.dim_customer c
  ON c.customer_id = f.customer_id
GROUP BY c.customer_id
ORDER BY customer_revenue DESC
LIMIT 10;


-- ============================================================
-- 5) Revenue by country
-- Purpose: analyze geographic performance.
-- ============================================================
SELECT
    co.country,
    ROUND(SUM(f.total_price), 2) AS country_revenue
FROM analytics.fact_sales f
JOIN analytics.dim_country co
  ON co.country_id = f.country_id
GROUP BY co.country
ORDER BY country_revenue DESC;


-- ============================================================
-- 6) Average order value (AOV)
-- Purpose: measure typical invoice size.
-- ============================================================
SELECT
    ROUND(SUM(total_price) / COUNT(DISTINCT invoice), 2) AS avg_order_value
FROM analytics.fact_sales;


-- ============================================================
-- 7) Returns impact (negative quantities)
-- Purpose: quantify revenue loss from returns.
-- ============================================================
SELECT
    ROUND(SUM(total_price), 2) AS return_revenue_impact
FROM analytics.fact_sales
WHERE quantity < 0;


-- ============================================================
-- 8) Weekly revenue trend
-- Purpose: detect short-term seasonality patterns.
-- ============================================================
SELECT
    d.year,
    d.week_of_year,
    ROUND(SUM(f.total_price), 2) AS weekly_revenue
FROM analytics.fact_sales f
JOIN analytics.dim_date d
  ON d.date_key = f.date_key
GROUP BY d.year, d.week_of_year
ORDER BY d.year, d.week_of_year;


