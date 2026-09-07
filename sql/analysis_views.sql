-- Step 2: SQL analysis layer
-- All of this is plain SQL (SQLite window functions) on top of the raw
-- `prices` table. Views recompute live off whatever's in `prices`, so as
-- Step 1 keeps feeding new days in, these numbers update automatically.

-- ---------------------------------------------------------------------
-- 1. Daily returns
-- Day-over-day % change in closing price per ticker.
-- LAG() looks at the previous row within the same ticker's date-ordered
-- sequence -- this is the single most useful window function for time
-- series and comes up constantly in DS/analyst interviews.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS daily_returns;
CREATE VIEW daily_returns AS
SELECT
    ticker,
    date,
    close,
    LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
    ROUND(
        (close - LAG(close) OVER (PARTITION BY ticker ORDER BY date))
        / LAG(close) OVER (PARTITION BY ticker ORDER BY date) * 100.0,
    3) AS pct_change
FROM prices;


-- ---------------------------------------------------------------------
-- 2. Moving averages
-- 7-day and 30-day trailing average closing price per ticker.
-- ROWS BETWEEN N PRECEDING AND CURRENT ROW defines the trailing window.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS moving_averages;
CREATE VIEW moving_averages AS
SELECT
    ticker,
    date,
    close,
    ROUND(AVG(close) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS ma_7,
    ROUND(AVG(close) OVER (
        PARTITION BY ticker ORDER BY date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ), 2) AS ma_30
FROM prices;


-- ---------------------------------------------------------------------
-- 3. Rolling volatility (30-day trailing standard deviation of daily returns)
-- SQLite has no built-in STDEV, so we derive it from the identity:
--   variance = E[x^2] - (E[x])^2
-- computed with two AVG() window aggregates over the same trailing frame,
-- then take the square root.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS rolling_volatility;
CREATE VIEW rolling_volatility AS
WITH returns AS (
    SELECT ticker, date, pct_change
    FROM daily_returns
    WHERE pct_change IS NOT NULL
),
windowed AS (
    SELECT
        ticker,
        date,
        pct_change,
        AVG(pct_change) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS avg_return,
        AVG(pct_change * pct_change) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS avg_sq_return,
        COUNT(*) OVER (
            PARTITION BY ticker ORDER BY date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS n_obs
    FROM returns
)
SELECT
    ticker,
    date,
    pct_change,
    n_obs,
    ROUND(
        SQRT(MAX(avg_sq_return - avg_return * avg_return, 0.0)),
    3) AS volatility_30d   -- trailing 30-obs std dev of daily % returns
FROM windowed;


-- ---------------------------------------------------------------------
-- 4. Z-scored daily moves
-- How many standard deviations today's move is from that ticker's own
-- recent normal -- this is the exact building block Step 3 (anomaly
-- detection) will threshold on.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS return_zscores;
CREATE VIEW return_zscores AS
SELECT
    r.ticker,
    r.date,
    r.pct_change,
    v.volatility_30d,
    CASE
        WHEN v.volatility_30d > 0 THEN ROUND(r.pct_change / v.volatility_30d, 2)
        ELSE NULL
    END AS return_zscore
FROM daily_returns r
JOIN rolling_volatility v ON r.ticker = v.ticker AND r.date = v.date
WHERE r.pct_change IS NOT NULL;


-- ---------------------------------------------------------------------
-- 5. Week-over-week % change by ticker (using the most recent trading
-- day available vs. 5 trading days prior -- a simple analyst-style KPI)
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS week_over_week;
CREATE VIEW week_over_week AS
SELECT
    ticker,
    date,
    close,
    LAG(close, 5) OVER (PARTITION BY ticker ORDER BY date) AS close_5d_ago,
    ROUND(
        (close - LAG(close, 5) OVER (PARTITION BY ticker ORDER BY date))
        / LAG(close, 5) OVER (PARTITION BY ticker ORDER BY date) * 100.0,
    2) AS wow_pct_change
FROM prices;