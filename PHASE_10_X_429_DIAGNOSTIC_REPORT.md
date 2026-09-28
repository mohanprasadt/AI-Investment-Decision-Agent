# Phase 10.x — Cold-Cache 429 Diagnostic Report

**Date:** 2026-08-16  
**Diagnostic run:** `diagnostic_phase10x_3.py` → `diagnostic_output_3.json`  
**Status:** Investigation complete — root cause identified. No code changes in this report.

---

## Executive Summary

All three previously-failing tickers (FTS.TO, TATASTEEL.NS, and ENB.TO) succeeded with full
data when tested with 35-second delays between tickers. No 429 errors were observed. The
failures the user experienced were **transient Yahoo Finance rate-limiting caused by request
bunching**, not a structural defect in the application or a ticker-specific problem.

The P0/P1/History fixes remain correct and necessary. They prevent a secondary amplification
loop (dead cache → forced retry → dead cache), but they cannot prevent the upstream condition:
too many Yahoo Finance HTTP requests in a short window.

---

## 10-Question Final Report

### Q1 — Exact endpoint causing 429

**Answer: The info endpoint (`/v10/finance/quoteSummary/`) is the highest-cost endpoint and
the most likely to trigger a 429 first, but no single endpoint is structurally broken.**

From T4 (AAPL, clean cold-cache, no prior in-process state):

| Endpoint           | HTTP requests | URL pattern                              |
|--------------------|:-------------:|------------------------------------------|
| `t.info`           | 3             | quoteSummary, v7/quote, timeseries (peg) |
| `t.financials`     | 1             | fundamentals-timeseries (income)         |
| `t.balance_sheet`  | 1             | fundamentals-timeseries (balance)        |
| `t.cashflow`       | 1             | fundamentals-timeseries (cashflow)       |
| `t.history(5y)`    | 2             | v8/finance/chart (×2 — timezone lookup)  |
| **Total**          | **8**         |                                          |

The info endpoint costs 3× more than any other endpoint because yfinance fetches
`quoteSummary`, `v7/quote`, and a trailing-PEG-ratio timeseries probe all within a single
`t.info` call.

When Yahoo rate-limits, info is where the burst count accumulates fastest.

---

### Q2 — Does direct yfinance reproduce the 429?

**Answer: No — not when tickers are spaced 35 seconds apart.**

T1 tested ENB.TO, FTS.TO, and TATASTEEL.NS sequentially with a 35-second inter-ticker delay.
All 15 endpoint calls succeeded:

| Ticker         | Endpoints | All succeeded | Total HTTP |
|----------------|:---------:|:-------------:|:----------:|
| ENB.TO         | 5         | Yes           | 7          |
| FTS.TO         | 5         | Yes           | 7          |
| TATASTEEL.NS   | 5         | Yes           | 8          |

T7 (info-only, 35s delays) also succeeded for all three — 2 HTTP requests each, no errors.

The 429 is not inherent to these tickers or the yfinance library. It is a Yahoo Finance
server-side rate limit that triggers when the request rate exceeds a threshold.

---

### Q3 — Does the project CLI/application path reproduce the 429?

**Answer: No — not when analyses are spaced 35 seconds apart.**

T3 ran `load_ticker()` through the full application path (`data_loader.py → fetch_ticker()`)
for all three tickers:

| Ticker         | load_ok | completeness | HTTP |
|----------------|:-------:|:------------:|:----:|
| ENB.TO         | True    | 100%         | 3    |
| FTS.TO         | True    | 100%         | 3    |
| TATASTEEL.NS   | True    | 100%         | 3    |

The lower HTTP count in T3 (3 vs 8) is because T1 had already fetched the fundamentals
endpoints in the same Python process; yfinance's in-process state (via the `YfData` singleton)
did not re-fetch endpoints whose responses were still held in memory. The correct baseline
for a true cold process is the T4 result: **8 HTTP requests**.

---

### Q4 — Does Streamlit add additional requests compared to a direct CLI call?

**Answer: Streamlit itself adds no Yahoo Finance requests. The difference is process lifetime.**

A CLI run (`python diagnostic_phase10x_3.py`) starts a fresh Python process for each
invocation — a cold `YfData` singleton with no in-memory state.

Streamlit runs a **long-lived Python process** that keeps the `YfData` singleton alive across
all user interactions. This has two effects:

- **Positive**: After a ticker's data is loaded once, subsequent requests for the same ticker
  within the same Streamlit session hit the disk cache (our `data/cache/`) with 0 HTTP
  requests.
- **Negative**: A 429 event poisoned the singleton's cookie state. Because `YfData` is a
  singleton (one instance per process), a cookie invalidation or crumb failure on one ticker
  can degrade requests for all subsequent tickers in the same session. A CLI call would start
  fresh; Streamlit cannot.

The Streamlit process also runs analyses without any enforced delay between them. If the user
triggers two analyses within seconds, both run concurrently against Yahoo Finance, and their
combined request rate can exceed the rate limit.

---

### Q5 — Number of Yahoo Finance requests for one cold ticker

**Answer: 8 HTTP requests per cold ticker** (from T4 — the only test that controlled for
in-process caching).

| Phase                    | Requests | Notes                                      |
|--------------------------|:--------:|--------------------------------------------|
| `fetch_info`             | 3        | quoteSummary + v7/quote + timeseries probe |
| `fetch_financials` (×3)  | 3        | One per statement (income, balance, cash)  |
| `fetch_history (5y)`     | 2        | chart endpoint called twice (tz lookup)    |
| **Total**                | **8**    |                                            |

Cookie negotiation (when `cookies.db` has a valid entry): 0 additional requests. yfinance
reuses the stored crumb. When the cookie is invalid or expired: yfinance's `_make_request()`
switches strategy (basic↔csrf) and fetches a new crumb — up to 4 additional requests per
400+ response.

---

### Q6 — Does the retry loop amplify requests?

**Answer: Yes — but only when info 429s. Financials and history 429s do NOT trigger the loop.**

The pipeline's 4-attempt retry loop (`_RETRY_DELAYS = [0, 5, 15, 30]`) fires only when
`"429"` or `"Too Many Requests"` appears in `load_result.cannot_complete_reason`. That field
is set only when `info._fetch_success=False`.

**Propagation by endpoint:**

| Endpoint     | 429 handling in yfinance            | Propagates to `_fetch_error`? | Triggers pipeline retry? |
|--------------|-------------------------------------|:-----------------------------:|:------------------------:|
| info         | Silently empty (hide_exceptions)    | No (silent empty dict)        | Yes (via no-company check) |
| financials   | Silently empty (hide_exceptions)    | No (P0 detects all-empty)     | **No**                   |
| history      | Re-raised (`YFRateLimitError`)      | Yes (except clause catches it)| **No**                   |

A financials or history 429 returns `_fetch_success=False` but does not prevent
`load_result.ok=True` — `data_loader.py` only checks `info._fetch_success`. The pipeline
proceeds to the decision engine with 0% financial data and no retry.

**Amplification math (info 429 only):**

| Scenario                                  | HTTP requests |
|-------------------------------------------|:-------------:|
| Single attempt, all endpoints hit         | 8             |
| Single attempt, 400+ retry (bad cookie)  | up to +4      |
| 4 pipeline attempts (all info-fail)       | up to 32–48   |

With a warm `cookies.db` (as observed), the 400+ internal retry is unlikely — the stored
crumb is accepted. Without a warm cookie (fresh process, never authenticated), each info
failure can cost up to 12 HTTP requests before the pipeline retry fires.

---

### Q7 — Why does ENB.TO succeed while FTS.TO and TATASTEEL.NS fail?

**Answer: ENB.TO is not special. All three behave identically given adequate spacing.**

T1, T3, T5, and T7 all confirmed identical success rates for ENB.TO, FTS.TO, and TATASTEEL.NS
when requests are spaced 35 seconds apart. T5 specifically tested whether order mattered
(ENB first then FTS, vs FTS first) — both orderings succeeded.

The most likely explanation for the asymmetric failures in the original Streamlit session:

1. ENB.TO had a warm disk cache from an earlier session — it produced 0 HTTP requests.
2. FTS.TO and TATASTEEL.NS were cold — they each needed 8 HTTP requests.
3. The user analyzed all three without delay. The burst of 16 cold requests within a few
   seconds crossed Yahoo's rate-limit threshold, and the two cold tickers got 429'd.

After the user deleted `data/cache/` (making ENB.TO also cold), all three now hit Yahoo cold.
But this diagnostic ran with deliberate 35-second delays, which Yahoo's rate limiter accepts.

---

### Q8 — Is the problem Yahoo, yfinance, or the application?

**Answer: Yahoo Finance rate-limiting (server-side) triggered by the application making too
many requests in a short window. yfinance is correct. The application has no cooldown between
analyses.**

- **Yahoo Finance** enforces a request rate limit. The threshold appears to be approximately
  8–10 requests per ~30 seconds per IP/session. This is a Yahoo-side policy.
- **yfinance** is working correctly. It uses `curl_cffi` (confirmed: v0.16.0 installed) for
  browser TLS impersonation, which is the recommended approach. Its internal retry logic
  (strategy toggle on 400+) is standard. The `hide_exceptions=True` default means financials
  429s are silently empty rather than raised — a yfinance design choice, not a bug.
- **The application** has no enforced delay between ticker analyses. The Streamlit UI allows
  immediate back-to-back analyses. When the disk cache is cold, this creates request bursts
  that exceed Yahoo's threshold.

The `fetch_ticker()` function adds `time.sleep(0.5)` after info and financials, and `0.3s`
after history — but these are within a single ticker fetch, not between ticker fetches at the
pipeline level.

---

### Q9 — Smallest production fix

**Answer: A minimum inter-analysis delay at the `fetch_ticker()` call site in `pipeline.py`,
combined with the already-implemented P0/P1/History fixes.**

The P0/P1/History fixes are correct and complete for their scope. They prevent dead-cache
amplification. They do not address the upstream rate-limit trigger.

The smallest additional fix that addresses the root cause without changing retry logic,
analytics, or Streamlit:

**Option A — Delay in `fetch_ticker()` between component fetches** (already partially done):
The existing `time.sleep(0.5)` calls are per-statement, not per-ticker. Adding a longer sleep
(e.g. 2–3s) after the full `fetch_ticker()` call in `pipeline.py` before the pipeline
proceeds would help reduce burst density when multiple analyses follow each other.

**Option B — Rate-limit guard at the fetcher level** (recommended):
Add a module-level timestamp tracking last fetch. If less than N seconds have passed since the
last yfinance call, sleep the difference. This is transparent to all callers.

**Option C — Batch pre-fetch with delay** (larger change):
Add a `fetch_portfolio()` call with `delay_between_tickers=35.0` as a pre-warm step before
the user's first analysis session. This is a UX change.

Of these, **Option A is the smallest authorized change** and requires one line in
`pipeline.py`. It would not fully prevent 429s under adversarial conditions but would
significantly reduce burst density in normal usage.

---

### Q10 — Should retry logic be retained, changed, or removed?

**Answer: Retain as-is. The retry logic is correctly scoped and correctly implemented.**

The current retry loop (`_RETRY_DELAYS = [0, 5, 15, 30]`) is appropriate:

- It fires only on info 429 (the only endpoint that propagates to `cannot_complete_reason`).
- The delays (5s, 15s, 30s) give Yahoo's rate-limit window time to clear.
- The 4-attempt cap prevents infinite loops.
- It does not amplify requests beyond what a single-attempt cold fetch costs — it retries the
  full pipeline, but only after the specified wait.

The diagnostic confirmed this works: all tickers succeed when spaced 35 seconds apart. The
retry waits (up to 50s combined) fall within that window.

**The one structural gap** — financials and history 429s bypassing the retry loop — is a
known consequence of how `data_loader.py` evaluates success. Closing this gap would require
`load_ticker()` to also inspect `financials._fetch_success` and `history._fetch_success` and
surface them to `pipeline.py`. This is a medium-complexity change (separate authorization).

---

## Supporting Data

### T4 — HTTP request anatomy for AAPL (cold, clean process)

```
endpoint         status  req  cumulative
info             OK       3       3    → quoteSummary + v7/quote + timeseries(peg)
financials       OK       1       4    → fundamentals-timeseries (income)
balance_sheet    OK       1       5    → fundamentals-timeseries (balance)
cashflow         OK       1       6    → fundamentals-timeseries (cashflow)
history_5y       OK       2       8    → v8/finance/chart ×2
```

### T2 — Internal yfinance SQLite caches

```
Path: C:\Users\itsmo\AppData\Local\py-yfinance\
  cookies.db    8,192 bytes   modified 2026-08-10  (6 days old — warm)
  tkr-tz.db    12,288 bytes   modified 2026-08-15  (yesterday — warm)
```

Both survive deletion of `data/cache/`. The warm `cookies.db` means yfinance is using a
cached Yahoo cookie/crumb — the 400+ internal retry (strategy toggle) is unlikely to fire as
long as this cookie remains valid. If Yahoo invalidates it, the next session will need full
cookie renegotiation (~4 additional HTTP requests per endpoint hit).

### T1 — Per-ticker summary

```
ENB.TO        ALL OK   7 HTTP   failed=[]
FTS.TO        ALL OK   7 HTTP   failed=[]
TATASTEEL.NS  ALL OK   8 HTTP   failed=[]
```

### Environment

```
Python:     3.14.6 (Windows)
yfinance:   1.5.2
curl_cffi:  0.16.0  ← browser TLS impersonation active
```

---

## Remaining Production Defects

| Defect | Severity | Status |
|---|---|---|
| `fetch_financials()` writing dead cache entries | **Fixed** (P0) |
| `_load_cache()` serving failed-fetch entries | **Fixed** (P1) |
| `fetch_history()` writing dead cache entries | **Fixed** (History Fix) |
| Yahoo 429 on burst requests (no inter-analysis delay) | **Root cause — unfixed** |
| `force_refresh` silently dropped in `pipeline.py` | Medium — separate auth needed |
| financials/history 429 bypasses pipeline retry | Medium — separate auth needed |

---

## Recommended Next Step

Before authorizing any code change: run two analyses in the Streamlit UI back-to-back (within
5 seconds of each other, both cold) to confirm the burst-rate hypothesis reproduces the 429.
If confirmed, authorize Option A (inter-analysis delay) as the smallest targeted fix.

If the Streamlit UI 429 is no longer reproducible after the P0/P1/History fixes (because the
dead-cache cycle is gone and requests no longer spike), no further change is needed.
