-- Load 2009–2010
\copy raw.online_retail (
  invoice,
  stockcode,
  description,
  quantity,
  invoicedate,
  price,
  customer_id,
  country
)
FROM 'Year_2009-2010_online_retail_II.csv'
WITH (FORMAT csv, HEADER true);

-- Load 2010–2011
\copy raw.online_retail (
  invoice,
  stockcode,
  description,
  quantity,
  invoicedate,
  price,
  customer_id,
  country
)
FROM 'Year_2010-2011_online_retail_II.csv'
WITH (FORMAT csv, HEADER true);
