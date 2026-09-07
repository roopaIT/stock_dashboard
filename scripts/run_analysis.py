"""
run_analysis.py

Step 2: loads the SQL views (rolling averages, volatility, z-scores) and
prints a few sample reports so you can see the analysis layer working on
top of whatever's in prices.db so far.

Run from inside scripts/:
    python run_analysis.py
"""

import sqlite3

DB_PATH = "../data/prices.db"


def load_views(conn):
    with open("../sql/analysis_views.sql") as f:
        conn.executescript(f.read())


def print_section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main():
    conn = sqlite3.connect(DB_PATH)
    load_views(conn)

    print_section("Latest moving averages per ticker")
    rows = conn.execute("""
        SELECT ticker, date, close, ma_7, ma_30
        FROM moving_averages
        WHERE (ticker, date) IN (
            SELECT ticker, MAX(date) FROM moving_averages GROUP BY ticker
        )
        ORDER BY ticker
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<8} {r[1]}  close={r[2]:<8}  MA7={r[3]:<8}  MA30={r[4]}")

    print_section("Biggest single-day movers (most recent date in DB)")
    rows = conn.execute("""
        SELECT ticker, date, pct_change
        FROM daily_returns
        WHERE date = (SELECT MAX(date) FROM daily_returns)
        ORDER BY ABS(pct_change) DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<8} {r[1]}  {r[2]:+.2f}%")

    print_section("Week-over-week % change (latest date per ticker)")
    rows = conn.execute("""
        SELECT ticker, date, wow_pct_change
        FROM week_over_week
        WHERE (ticker, date) IN (
            SELECT ticker, MAX(date) FROM week_over_week GROUP BY ticker
        )
        AND wow_pct_change IS NOT NULL
        ORDER BY wow_pct_change DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<8} {r[1]}  {r[2]:+.2f}%")

    print_section("Current 30-day rolling volatility per ticker")
    rows = conn.execute("""
        SELECT ticker, date, volatility_30d
        FROM rolling_volatility
        WHERE (ticker, date) IN (
            SELECT ticker, MAX(date) FROM rolling_volatility GROUP BY ticker
        )
        ORDER BY volatility_30d DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[0]:<8} {r[1]}  volatility={r[2]}")

    print_section("Unusual moves (|z-score| > 2) in the last 10 trading days")
    rows = conn.execute("""
        SELECT ticker, date, pct_change, return_zscore
        FROM return_zscores
        WHERE ABS(return_zscore) > 2
        AND date >= (SELECT date(MAX(date), '-14 days') FROM return_zscores)
        ORDER BY date DESC, ABS(return_zscore) DESC
    """).fetchall()
    if rows:
        for r in rows:
            print(f"  {r[0]:<8} {r[1]}  move={r[2]:+.2f}%  z={r[3]:+.2f}")
    else:
        print("  None found in this window (try again once more history has built up).")

    conn.close()


if __name__ == "__main__":
    main()