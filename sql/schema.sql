-- Real-time stock dashboard - local storage schema
-- One row per (ticker, date). Re-running the fetch script upserts on this
-- pair, so it's always safe to run daily without creating duplicates.

CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT NOT NULL,
    date        DATE NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    volume      INTEGER,
    fetched_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

-- Speeds up the trend/anomaly queries in Step 2
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date);
CREATE INDEX IF NOT EXISTS idx_prices_date         ON prices(date);

-- Step 3: persisted anomaly alerts. UNIQUE(ticker, date) means re-running
-- the scan script never double-logs the same day's alert twice, even if
-- you run it multiple times per day.
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    pct_change      REAL,
    return_zscore   REAL,
    threshold_used  REAL,
    triggered_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, date)
);

-- Tracks each ingestion run
CREATE TABLE IF NOT EXISTS ingestion_log (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tickers         TEXT,
    date_range_from DATE,
    date_range_to   DATE,
    rows_fetched    INTEGER,
    rows_upserted   INTEGER
);