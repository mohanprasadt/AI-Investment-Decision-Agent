# Data Ingestion and Cache

> **Status:** IMPLEMENTED  
> **Key risk:** yfinance is an unofficial API with no SLA. Rate-limiting is the primary reliability risk.

---

## How data is fetched

All financial data comes from Yahoo Finance via the `yfinance` Python library. There is no other data source.

**What yfinance provides:**
- Company info (name, sector, currency, exchange, market cap)
- Income statement (annual, quarterly)
- Balance sheet (annual, quarterly)
- Cash flow statement (annual, quarterly)
- Price history (daily/weekly/monthly)

**What yfinance does NOT reliably provide:**
- Continuing-operations net income (separate from total NI) — available for some tickers, not all
- D&A and working capital separately — often embedded in cash flow statement totals
- Peer valuation data — not available
- Dividend reinvestment price history — approximated from price history

---

## Cache structure

Each ticker has its own subdirectory with three JSON files:

```
data/cache/
├── ITC.NS/
│   ├── info.json         ← company info (TTL: 24h)
│   ├── financials.json   ← income statement, balance sheet, cash flows (TTL: 48h)
│   └── history.json      ← price history (TTL: 24h)
├── TD.TO/
│   ├── info.json
│   ├── financials.json
│   └── history.json
└── ...
```

Each JSON file has a `_fetched_at` timestamp. The fetcher checks this against the TTL before deciding whether to re-fetch.

---

## Cache TTLs

| File | TTL | Rationale |
|------|-----|-----------|
| `info.json` | 24 hours | Company info changes infrequently |
| `financials.json` | 48 hours | Financial statements change only at earnings releases |
| `history.json` | 24 hours | Price data is daily; refresh daily for accuracy |

After a TTL expires, the next analysis for that ticker will attempt a live fetch. If the live fetch fails (e.g., 429 rate limit), the analysis fails with a friendly error message rather than serving stale data.

---

## What is and is NOT cached

| Data | Cached? | Reason |
|------|---------|--------|
| Successful fetches | ✅ Yes | Avoid re-hitting Yahoo Finance |
| Failed fetches | ❌ No | Would poison future reads with empty data |
| Empty financials (no rows) | ❌ No | Same as above — Phase 10.x fix |
| Empty price history (0 rows) | ❌ No | Phase 10.x fix |

This is the critical Phase 10.x fix. Before Phase 10.x, failed fetches were being cached, which meant a subsequent read would serve an empty cache as if it were valid data.

---

## Force Refresh

The `force_refresh` flag bypasses the TTL check and fetches live data regardless of cache freshness. It is useful after earnings releases when the cached financials are known to be stale.

**How it works:**
1. UI checkbox sets `force_refresh=True`
2. `app.py` passes it to `ConversationManager.run_analysis()`
3. `ConversationManager` passes it to `run_analysis_pipeline()`
4. `pipeline.py` passes it to `load_ticker()`
5. `fetcher.fetch_ticker()` ignores the cache and makes a live request

This wiring was broken before Phase 10.5 — the flag was passed in the function signature but not actually reaching `fetch_ticker()`. Fixed in Phase 10.5.

---

## Rate limiting (HTTP 429)

Yahoo Finance rate-limits requests aggressively. The system handles this differently in the interactive path vs the pre-warm path:

### Interactive path (user-triggered analysis)

**Decision:** FAIL FAST — no retry.

**Why:** A 30–60 second retry loop during an interactive session is a poor experience. If Yahoo Finance is rate-limiting, retrying doesn't help because the rate limit applies to the same IP for several minutes.

**What happens:**
1. `yfinance` raises an exception containing "429" or similar
2. `fetcher.py` propagates the exception
3. `pipeline.py` catches it → `PipelineResult(ok=False, is_rate_limited=True)`
4. `conversation/manager.py` formats a friendly error message
5. UI displays: "Live data could not be retrieved for [TICKER] because market data sources are temporarily limiting requests..."

**What the user should do:** Wait a few minutes and try again, or select a ticker that has cached data.

### Pre-warm path (`scripts/prewarm_mvp.py`)

**Decision:** Retry with delays — up to [30, 60] seconds between attempts.

**Why:** Pre-warming is a background operation. The user is not waiting for it interactively. A retry is appropriate here.

**Windows compatibility:** The pre-warm script is sequential (not parallel) to avoid Windows multiprocessing issues. Each ticker is fetched with a 35-second delay to avoid triggering rate limits.

---

## The `is_rate_limited` flag

`PipelineResult.is_rate_limited` is set `True` when a 429 is detected. This allows the UI to show a specific, actionable message rather than a generic error.

```python
# In pipeline.py
if is_rate_limit_error(e):
    return PipelineResult(ok=False, is_rate_limited=True, error=str(e))
```

---

## Data status panel

The UI shows a data status panel (collapsible) before analysis runs. For each ticker, it shows:

| Component | Status |
|-----------|--------|
| Info | ✅ Fresh / ⚠️ Stale / ⬜ Not cached |
| Financials | ✅ Fresh / ⚠️ Stale / ⬜ Not cached |
| Price history | ✅ Fresh / ⚠️ Stale / ⬜ Not cached |

This is powered by `ui/data_status.py`, which reads the cache directory without fetching live data.

---

## Pre-warming the cache

Before a demo or planned analysis session, run:

```bash
python scripts/prewarm_mvp.py
```

This sequentially fetches all 33 MVP tickers with 35-second delays between each. Expected total time: approximately 20–35 minutes. After completion, 32–33 tickers will be fully cached and ready for offline analysis.

**Why not all 33?** Occasionally one ticker is unavailable from yfinance (temporary outage, symbol change). The pre-warm script continues past failures rather than stopping.

---

## ETF handling

The tickers in `KNOWN_ETFS` (currently: `CGL.C.TO`, `QGOLDHALF.NS`, `HDFCMFGETF.NS`) are fetched differently because ETFs do not have income statements, balance sheets, or earnings per share. They are excluded from the financial quality and valuation pipeline — only price history is fetched.

ETFs are not in the 33 MVP tickers. If encountered as a custom ticker, the system handles them with a simplified fetch.

---

## Known yfinance limitations

1. **No SLA.** yfinance is an unofficial library that scrapes/uses Yahoo Finance APIs that are not documented or guaranteed.

2. **Field name changes.** Yahoo Finance occasionally changes internal field names without notice, causing `KeyError` in the normalizer. This requires a code fix.

3. **Inconsistent field availability.** Some tickers return different fields depending on market (US vs Canada vs India). Some fields like `continuingOperationsIncome` are available for some tickers but not others.

4. **Data accuracy.** Yahoo Finance data occasionally has errors (wrong currency, wrong period labelling, zero values for non-zero items). The normalizer does basic sanity checks but cannot catch all cases.

5. **Rate limiting frequency.** Rate limits can be triggered by running analysis on too many tickers in quick succession, running the pre-warm script too fast, or simply by high traffic to Yahoo Finance. There is no reliable way to predict when rate limiting will occur.
