CREATE TABLE IF NOT EXISTS raw.online_retail (
    id BIGSERIAL PRIMARY KEY,
    invoice VARCHAR,
    stockcode VARCHAR,
    description VARCHAR,
    quantity INTEGER,
    invoicedate TIMESTAMP WITHOUT TIME ZONE,
    price NUMERIC(10,2),
    customer_id INTEGER,
    country VARCHAR
);
