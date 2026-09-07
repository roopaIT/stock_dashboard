"""
fetch_prices.py

Step 1 of the real-time stock market dashboard: incremental ingestion.

What it does:
1. For each ticker, checks the local database for the most recent date
   already stored (so re-running this daily only pulls NEW days).
2. Pulls daily OHLCV (open/high/low/close/volume) data via yfinance.
3. Upserts into a local SQLite database (safe to re-run - no duplicates).
4. Logs the run into `ingestion_log`.

This uses yfinance, a free, no-API-key wrapper around Yahoo Finance's
public data. Because it doesn't depend on a single small agency's API
(which can and did change under us in an earlier version of this project),
it's a more stable foundation for a "runs every day without babysitting"
pipeline.

Run it manually first:
    python fetch_prices.py --test                       # sanity check, no DB writes
    python fetch_prices.py --days-back 180               # first-ever backfill
    python fetch_prices.py                                # daily incremental run

Customize the watchlist with --tickers, e.g.:
    python fetch_prices.py --tickers AAPL,MSFT,NVDA,TSLA,SPY
"""

import argparse
import sqlite3
import sys
from datetime import date, timedelta

import yfinance as yf

DB_PATH = "../data/prices.db"
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "SPY"]  # SPY = S&P 500 ETF, useful as a market baseline


def get_last_date(conn, ticker):
    row = conn.execute(
        "SELECT MAX(date) FROM prices WHERE ticker = ?", (ticker,)
    ).fetchone()
    if row and row[0]:
        return row[0]
    return None


def fetch_ticker_history(ticker, start_date, end_date):
    """Returns a pandas DataFrame with Date index and OHLCV columns, or None on failure."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(start=start_date, end=end_date, interval="1d")
        if df.empty:
            return None
        return df
    except Exception as e:
        print(f"  WARNING: failed to fetch {ticker}: {e}", file=sys.stderr)
        return None


def upsert_prices(conn, ticker, df):
    if df is None or df.empty:
        return 0
    rows = []
    for idx, row in df.iterrows():
        rows.append((
            ticker,
            idx.strftime("%Y-%m-%d"),
            float(row["Open"]) if row["Open"] == row["Open"] else None,   # NaN check
            float(row["High"]) if row["High"] == row["High"] else None,
            float(row["Low"]) if row["Low"] == row["Low"] else None,
            float(row["Close"]) if row["Close"] == row["Close"] else None,
            int(row["Volume"]) if row["Volume"] == row["Volume"] else None,
        ))

    conn.executemany(
        """
        INSERT INTO prices (ticker, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, volume=excluded.volume
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def run(tickers, days_back, test_mode):
    conn = sqlite3.connect(DB_PATH)
    with open("../sql/schema.sql") as f:
        conn.executescript(f.read())

    today = date.today()
    total_fetched = 0
    total_upserted = 0
    date_min_overall = None
    date_max_overall = str(today)

    for ticker in tickers:
        last_date = get_last_date(conn, ticker)
        if last_date:
            # yfinance's `start` is inclusive, so start the day after what we have
            start = (date.fromisoformat(last_date) + timedelta(days=1)).isoformat()
        else:
            start = (today - timedelta(days=days_back)).isoformat()

        if date_min_overall is None or start < date_min_overall:
            date_min_overall = start

        print(f"Fetching {ticker} from {start} to {today}...")
        df = fetch_ticker_history(ticker, start, str(today + timedelta(days=1)))

        if test_mode:
            if df is not None:
                print(df.tail(3))
            else:
                print(f"  No data returned for {ticker} (may be up to date, or ticker invalid).")
            continue

        n = upsert_prices(conn, ticker, df)
        total_fetched += n
        total_upserted += n
        print(f"  upserted {n} rows for {ticker}")

    if not test_mode:
        conn.execute(
            """INSERT INTO ingestion_log (tickers, date_range_from, date_range_to, rows_fetched, rows_upserted)
               VALUES (?, ?, ?, ?, ?)""",
            (",".join(tickers), date_min_overall, date_max_overall, total_fetched, total_upserted),
        )
        conn.commit()
        print(f"\nDone. Upserted {total_upserted} total rows across {len(tickers)} tickers.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch daily stock prices into local SQLite DB")
    parser.add_argument("--tickers", type=str, default=",".join(DEFAULT_TICKERS),
                         help="Comma-separated tickers, e.g. AAPL,MSFT,TSLA")
    parser.add_argument("--days-back", type=int, default=180,
                         help="On first run (empty DB), how many days of history to backfill")
    parser.add_argument("--test", action="store_true",
                         help="Fetch and print without writing to the database")
    args = parser.parse_args()

    ticker_list = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    run(ticker_list, args.days_back, args.test)
