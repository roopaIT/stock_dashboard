# Real-Time Stock Market Monitoring Dashboard

A portfolio project: ingest daily stock price data automatically, detect
unusual price/volume moves, and surface it in a dashboard.

## Why this data source
Uses `yfinance`, a free wrapper around Yahoo Finance's public data. No API
key needed, no rate-limit headaches for this scale of use, and it's a much
more stable foundation than a single small agency's custom API (see the
earlier version of this project using CFPB data, which broke mid-project
when the agency restructured its site).

## Step 1 (this step): Ingestion

**Files:**
- `sql/schema.sql` — SQLite schema (`prices` table + `ingestion_log`)
- `scripts/fetch_prices.py` — pulls new daily OHLCV bars per ticker, upserts into SQLite
- `requirements.txt` — just `yfinance`

**Setup:**
```bash
cd stock_dashboard
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Test it first (no database writes):**
```bash
cd scripts
python fetch_prices.py --test
```
This fetches a few tickers and prints the last few rows so you can confirm
it's working before committing anything to disk.

**First backfill (180 days of history, default watchlist):**
```bash
python fetch_prices.py --days-back 180
```

**Daily incremental runs:**
```bash
python fetch_prices.py
```
Each ticker independently resumes from its own last-stored date — safe to
run daily via cron / Task Scheduler / GitHub Actions with no duplicates.

**Custom watchlist:**
```bash
python fetch_prices.py --tickers AAPL,MSFT,NVDA,TSLA,SPY,BTC-USD
```
(yfinance also supports crypto tickers like `BTC-USD`, `ETH-USD` if you want
to mix in crypto later.)

**Check it worked:**
```bash
sqlite3 ../data/prices.db "SELECT ticker, COUNT(*), MIN(date), MAX(date) FROM prices GROUP BY ticker;"
```

## Step 4: Dashboard + going live

**Files added:**
- `app.py` — the Streamlit dashboard (price trends, moving averages, volatility, alerts panel)
- `.github/workflows/daily_update.yml` — runs the pipeline automatically every weekday after market close and commits the updated database back to the repo

### Run it locally first
```bash
streamlit run app.py
```
This opens in your browser at `localhost:8501`. Confirm it looks right with
your real data before deploying.

### Deploy for real (Streamlit Community Cloud, free)

**1. Push this project to GitHub** (if you haven't already):
```bash
git init
git add .
git commit -m "Initial commit: stock monitoring dashboard"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/stock_dashboard.git
git push -u origin main
```
Make sure `data/prices.db` is included in this push — Streamlit Cloud reads
directly from what's in the repo, not your local machine.

**2. Deploy on Streamlit Community Cloud:**
- Go to https://share.streamlit.io and sign in with GitHub
- Click "New app", pick your `stock_dashboard` repo, branch `main`, main file `app.py`
- Click Deploy — you'll get a public URL like `yourname-stock-dashboard.streamlit.app`

**3. The daily update workflow is already set up** (`.github/workflows/daily_update.yml`):
runs automatically every weekday at 4:30pm ET, re-fetches prices, re-scans for
alerts, and commits the updated `data/prices.db` back to your repo. Streamlit
Cloud auto-redeploys whenever the repo changes, so your live dashboard updates
itself daily with zero manual work.

**To verify the automation is working:** go to your repo's "Actions" tab on
GitHub. You should see "Daily Stock Data Update" listed — click "Run workflow"
to trigger it manually the first time instead of waiting for the schedule.

### What to put on your resume/portfolio
- Link the live Streamlit URL directly
- In your README or a short write-up, mention the *why* behind each design
  choice (upsert for idempotency, z-score threshold as a precision/recall
  tradeoff, pivoting off CFPB's API when it broke) — that reasoning is what
  actually gets discussed in interviews, more than the code itself.
