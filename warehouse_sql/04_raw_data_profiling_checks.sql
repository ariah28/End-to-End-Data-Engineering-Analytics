-- ============================================================
-- raw_data_profiling.sql
-- Dataset: Online Retail II
-- Purpose: Profile raw.online_retail before staging
-- ============================================================

-- 0) Total row count
SELECT COUNT(*) AS total_rows
FROM raw.online_retail;

-- 1) NULL profiling (critical fields)
SELECT
    COUNT(*) FILTER (WHERE invoice IS NULL)        AS null_invoice,
    COUNT(*) FILTER (WHERE stockcode IS NULL)      AS null_stockcode,
    COUNT(*) FILTER (WHERE description IS NULL)    AS null_description,
    COUNT(*) FILTER (WHERE quantity IS NULL)       AS null_quantity,
    COUNT(*) FILTER (WHERE price IS NULL)          AS null_price,
    COUNT(*) FILTER (WHERE customer_id IS NULL)    AS null_customer_id
FROM raw.online_retail;

-- 2) Description spacing issues (leading or trailing spaces)
SELECT COUNT(*) AS rows_with_spacing_issues
FROM raw.online_retail
WHERE description LIKE ' %'
   OR description LIKE '% ';

-- 3) Negative and zero value checks
SELECT
    COUNT(*) FILTER (WHERE quantity < 0) AS negative_quantity,
    COUNT(*) FILTER (WHERE quantity = 0) AS zero_quantity,
    COUNT(*) FILTER (WHERE price < 0)    AS negative_price,
    COUNT(*) FILTER (WHERE price = 0)    AS zero_price
FROM raw.online_retail;

-- 4) Cancelled invoices (invoice starts with 'C')
SELECT COUNT(*) AS cancelled_invoices
FROM raw.online_retail
WHERE invoice LIKE 'C%';

-- 5) Invoice date range
SELECT
    MIN(invoicedate) AS min_invoicedate,
    MAX(invoicedate) AS max_invoicedate
FROM raw.online_retail;

-- 6) Country distribution
SELECT country, COUNT(*) AS cnt
FROM raw.online_retail
GROUP BY country
ORDER BY cnt DESC;

-- 7) Duplicate business rows (sample)
SELECT invoice, stockcode, invoicedate, COUNT(*) AS cnt
FROM raw.online_retail
GROUP BY invoice, stockcode, invoicedate
HAVING COUNT(*) > 1
ORDER BY cnt DESC
LIMIT 50;

-- 8) Price outliers
SELECT
    MIN(price) AS min_price,
    MAX(price) AS max_price
FROM raw.online_retail;

-- 9) Quantity outliers
SELECT
    MIN(quantity) AS min_quantity,
    MAX(quantity) AS max_quantity
FROM raw.online_retail;

-- 10) Extreme quantities (largest magnitude)
SELECT invoice, stockcode, quantity, price
FROM raw.online_retail
ORDER BY ABS(quantity) DESC
LIMIT 10;

-- 11) Extreme prices (highest values)
SELECT invoice, stockcode, quantity, price
FROM raw.online_retail
ORDER BY price DESC
LIMIT 10;

-- 12) Negative price inspection
SELECT invoice, stockcode, quantity, price
FROM raw.online_retail
WHERE price < 0
ORDER BY price
LIMIT 50;

-- 13) Non-product / financial rows
SELECT stockcode, description, COUNT(*) AS cnt
FROM raw.online_retail
WHERE stockcode = 'M'
   OR description IN ('BANK CHARGES', 'AMAZONFEE')
GROUP BY stockcode, description
ORDER BY cnt DESC;
