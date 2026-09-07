"""
scan_alerts.py

Step 3: turn the z-score column from Step 2 into a real, persisted alert
log. This is the "early warning system" part of the project.

Why a persisted alerts table instead of just printing anomalies each time:
- The dashboard (Step 4) can just read `alerts` directly, rather than
  recomputing z-scores on every page load.
- You keep a historical record of what was flagged and when, which lets
  you later ask "how many alerts did we generate last month, and did they
  matter?" -- a real question a risk/monitoring team would ask.
- UNIQUE(ticker, date) means re-running this daily never double-logs the
  same day.

On threshold choice:
A z-score threshold is a precision/recall tradeoff, not a fixed truth:
- Lower threshold (e.g. 1.5) -> catches more real moves, but also more
  false alarms from ordinary day-to-day noise (statistically, ~13% of
  days would cross 1.5 sigma by chance alone on a normal distribution).
- Higher threshold (e.g. 3.0) -> only very extreme, rare moves get
  flagged, but you might miss moderately unusual ones.
- 2.0-2.5 is a common starting point (roughly the top ~1-5% of days),
  but the "right" number depends on how much noise you're willing to
  tolerate for how much signal. Worth tuning based on how many alerts
  come out over a few weeks of real running.

Usage:
    python scan_alerts.py                  # scan with default threshold 2.0
    python scan_alerts.py --threshold 2.5  # stricter, fewer alerts
    python scan_alerts.py --days 30        # only scan the last 30 days
"""

import argparse
import sqlite3

DB_PATH = "../data/prices.db"


def load_views(conn):
    with open("../sql/analysis_views.sql") as f:
        conn.executescript(f.read())


def scan(threshold, days):
    conn = sqlite3.connect(DB_PATH)
    load_views(conn)

    candidates = conn.execute(
        """
        SELECT ticker, date, pct_change, return_zscore
        FROM return_zscores
        WHERE ABS(return_zscore) >= ?
        AND date >= (SELECT date(MAX(date), '-' || ? || ' days') FROM return_zscores)
        ORDER BY date DESC, ABS(return_zscore) DESC
        """,
        (threshold, days),
    ).fetchall()

    if not candidates:
        print(f"No moves crossed |z| >= {threshold} in the last {days} days.")
        conn.close()
        return

    new_alerts = 0
    for ticker, dt, pct_change, zscore in candidates:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO alerts (ticker, date, pct_change, return_zscore, threshold_used)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticker, dt, pct_change, zscore, threshold),
        )
        if cur.rowcount > 0:
            new_alerts += 1
            print(f"  NEW ALERT: {ticker:<8} {dt}  move={pct_change:+.2f}%  z={zscore:+.2f}")

    conn.commit()

    total_alerts = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    print(f"\n{new_alerts} new alert(s) logged this run. {total_alerts} total alerts in the log.")

    print("\nAlert counts by ticker (all-time):")
    for ticker, cnt in conn.execute(
        "SELECT ticker, COUNT(*) AS cnt FROM alerts GROUP BY ticker ORDER BY cnt DESC"
    ):
        print(f"  {ticker:<8} {cnt}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan for anomalous price moves and log alerts")
    parser.add_argument("--threshold", type=float, default=2.0,
                         help="Z-score threshold to flag as an alert (default 2.0)")
    parser.add_argument("--days", type=int, default=14,
                         help="How many recent days to scan (default 14)")
    args = parser.parse_args()

    scan(args.threshold, args.days)