-- ============================================================
-- staging_validation_checks.sql
-- Purpose: Validate staging.online_retail_clean correctness
-- ============================================================

-- 0) Row count in staging
SELECT COUNT(*) AS staging_row_count
FROM staging.online_retail_clean;

-- 1) Ensure no negative prices exist
SELECT COUNT(*) AS negative_price_rows
FROM staging.online_retail_clean
WHERE price < 0;

-- 2) Ensure excluded non-product rows are not present
SELECT COUNT(*) AS non_product_rows
FROM staging.online_retail_clean
WHERE stockcode = 'M'
   OR description IN ('BANK CHARGES', 'AMAZONFEE');

-- 3) Ensure descriptions have no leading/trailing spaces
SELECT COUNT(*) AS spacing_issues_remaining
FROM staging.online_retail_clean
WHERE description <> TRIM(description);

-- 4) Validate total_price calculation
SELECT COUNT(*) AS incorrect_total_price_rows
FROM staging.online_retail_clean
WHERE total_price <> (quantity * price);

-- 5) Verify expected staging row count based on raw filters
SELECT COUNT(*) AS expected_staging_rows
FROM raw.online_retail
WHERE quantity IS NOT NULL
  AND price IS NOT NULL
  AND price >= 0
  AND stockcode <> 'M'
  AND COALESCE(description, '') NOT IN ('BANK CHARGES', 'AMAZONFEE');

-- 6) Ensure returns are preserved (negative quantities allowed)
SELECT COUNT(*) AS negative_quantity_rows
FROM staging.online_retail_clean
WHERE quantity < 0;

-- 7) Ensure cancelled invoices are preserved
SELECT COUNT(*) AS cancelled_invoice_rows
FROM staging.online_retail_clean
WHERE invoice LIKE 'C%';

-- 8) Spot-check description cleaning (raw vs staging)
SELECT
    r.id,
    r.description AS raw_description,
    s.description AS staging_description
FROM raw.online_retail r
JOIN staging.online_retail_clean s USING (id)
WHERE r.description <> s.description
LIMIT 20;
