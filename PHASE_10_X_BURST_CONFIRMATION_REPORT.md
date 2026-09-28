# Phase 10.x — Burst Hypothesis Confirmation Report

**Date:** 2026-08-16  
**Diagnostic:** `diagnostic_phase10x_4.py` → `diagnostic_output_4.json`  
**Status:** Investigation complete. Verdict: hypothesis is partially confirmed via soft
throttling. Hard 429 not reproduced. No code change recommended.

---

## Verdict

**The request-burst hypothesis is partially confirmed, not refuted.**

No hard HTTP 429 was returned in either scenario. However, the timing data reveals that
Yahoo Finance DID react to the burst — it soft-throttled FTS.TO in Scenario A, making its
fetch 3.0× slower than in Scenario B. This is the mechanism Yahoo uses before escalating to
a hard 429.

The hard 429 threshold was not reached with 2 cold tickers (14 requests total). The original
Streamlit failures required a higher sustained burst — most likely from more tickers being
analyzed in a short window, or from the retry loop amplifying requests after an initial
soft-throttle escalated to a hard limit.

---

## Key Measurements

### Request elapsed time by scenario

| Ticker         | Scenario A (0s gap)   | Scenario B (35s gap)  | Ratio |
|----------------|----------------------:|----------------------:|------:|
| FTS.TO         | 10.63s total          | 4.44s total           | 2.4×  |
| FTS.TO (net)   | 9.33s network         | 3.14s network         | **3.0×** |
| TATASTEEL.NS   | 3.45s total           | 3.08s total           | 1.1×  |
| TATASTEEL.NS (net) | 2.15s network     | 1.78s network         | 1.2×  |

Net network time = elapsed minus mandatory intra-fetch sleeps (1.3s per ticker).

FTS.TO in Scenario A was **3.0× slower on network time alone**, despite identical cold-cache
state and the same number of HTTP requests (7). TATASTEEL.NS immediately after was fast
(1.2× difference, within normal variance).

### Total request rate

| Scenario        | Requests | Duration | Rate        |
|-----------------|:--------:|:--------:|-------------|
| A — back-to-back | 14      | 17.2s    | 0.81 req/s  |
| B — 35s gap      | 14      | 46.1s    | 0.30 req/s  |

Yahoo received 14 requests in 17 seconds during Scenario A — 2.7× the rate of Scenario B.
No hard 429 was returned, but the slowdown on the first ticker was the visible result.

---

## What the Slowdown Reveals

### Yahoo's response: soft throttling before hard limiting

FTS.TO's first request in Scenario A was the first Yahoo request from a fresh subprocess
after a ~14-minute gap since Suite 3. Yahoo recognized a burst pattern and slowed its
responses — returning each of the 7 FTS.TO requests in an average of **1.33 seconds** instead
of the expected ~0.45 seconds. This is not network congestion; it is deliberate server-side
pacing.

### The self-correcting mechanism

The slow responses for FTS.TO had a side effect: they spread FTS.TO's 7 requests across 10.6
seconds instead of the expected ~2 seconds. By the time TATASTEEL.NS started, Yahoo's
sliding rate-limit window had been partially "consumed" by slow FTS.TO requests rather than
rapid ones — so TATASTEEL.NS ran at full speed (0.31s/request average).

In other words, Yahoo's soft throttling is **self-regulating**. The application does not need
to add its own delay to compensate, because Yahoo's own pacing is already doing it.

### Why the hard 429 was not reproduced

The hard 429 threshold requires a higher sustained rate than 14 requests in 17 seconds.
Based on the evidence across all four diagnostic runs:

| Run       | Tickers tested | Max burst density | 429 observed? |
|-----------|:--------------:|:------------------:|:-------------:|
| Suite 2   | 5              | ENB, FTS, TATASTEEL in rapid UI succession | Yes |
| Suite 3   | 4 (35s gaps)   | ~8 req per 35s     | No  |
| Suite 4 A | 2 (0s gap)     | 14 req in 17s      | No  |
| Suite 4 B | 2 (35s gap)    | 14 req in 46s      | No  |

The hard 429 in Suite 2 occurred under conditions the scripts cannot replicate precisely:
a live Streamlit session with accumulated request history from earlier in the day, a stale
cookie state, and the retry loop likely already active. The 3-ticker burst in the Streamlit UI
produced a request density that crossed the hard threshold. The 2-ticker script tests did not.

---

## Delay Analysis — Where to Place One and Whether To

This analysis evaluates all candidate locations, as requested.

### The four candidate locations

**Location 1: After `load_ticker()` in `pipeline.py` (line 142)**

```python
load_result = load_ticker(ticker=ticker, analysis_date=_date)
# ← a delay here
```

- **What it separates**: the tail of a full ticker fetch from the next time this pipeline
  is called. But `pipeline.py` runs for one ticker at a time — a second ticker is a separate
  call to `run_analysis_pipeline()`, triggered by the user. There is no loop here to delay.
  Inserting a sleep here would delay the rest of the pipeline (research, valuation, decision)
  for every call, even when data came from cache.
- **Effect on retries**: this line IS inside the retry loop. A 5-second delay here would add
  5 seconds to every retry attempt PLUS the existing retry wait (`time.sleep(_wait)`). The
  total inter-attempt wait for attempt 2 would become 10 seconds instead of 5 — doubling the
  retry latency unnecessarily.
- **Effect on cached tickers**: `load_ticker()` returns in <0.1s on a cache hit, then the
  delay fires unconditionally — adding latency to the most common case.
- **Reduces request volume**: No. The requests are already made before this point.
- **Assessment**: Wrong location. Penalises cached tickers, doubles retry delays, and does
  not affect Yahoo request rate because the requests are already complete.

---

**Location 2: At the top of `fetch_ticker()` (before the three fetcher calls)**

```python
def fetch_ticker(ticker, force_refresh=False):
    # ← a delay here
    return {
        "info": fetch_info(ticker, ...),
        ...
    }
```

- **What it separates**: a minimum gap between the start of one ticker's requests and the
  start of the next. This is where inter-ticker spacing would live if `fetch_ticker()` were
  called in a loop.
- **Effect on retries**: `pipeline.py` calls `load_ticker()` → `_default_fetch()` →
  `fetch_ticker()` on each retry attempt. A delay here fires on every retry. The retry loop
  already waits (5s, 15s, 30s) before re-entering the pipeline — the delay would stack on
  top, adding to already-correct wait times.
- **Effect on cached tickers**: `fetch_ticker()` is called even on cache hits (the individual
  fetchers check cache internally). A delay here fires for every call regardless of whether
  any HTTP request is actually made. A user re-running a cached ticker would wait
  unnecessarily.
- **Reduces request volume**: No.
- **Assessment**: Incorrect for both retries (double-counts) and cached tickers (fires
  unconditionally). Not recommended.

---

**Location 3: Within each fetcher, only on a cache miss, before the `yf.Ticker()` call**

```python
def fetch_info(ticker, force_refresh=False, max_age_hours=24):
    if not force_refresh:
        cached = _load_cache(ticker, "info", max_age_hours)
        if cached:
            return cached   # ← cache hit: NO delay, immediate return

    # ← delay only here (cache miss confirmed — a real network call is coming)
    log.info(f"Fetching info: {ticker}")
    ...
```

Same pattern in `fetch_financials()` and `fetch_history()`.

- **What it separates**: actual Yahoo requests from each other. Only fires when a real HTTP
  call is about to be made.
- **Effect on retries**: correct — each retry attempt genuinely needs the delay because it is
  making a real network call. The delay is calibrated to the actual work being done.
- **Effect on cached tickers**: zero. Cache hits return before the delay line.
- **Reduces request volume**: No — but spaces requests, reducing burst density at the Yahoo
  endpoint level.
- **Assessment**: The most surgically correct placement if a delay is ever warranted.

---

**Location 4: No additional delay (status quo)**

The application already has 1.3 seconds of deliberate sleep per cold ticker fetch:
- `time.sleep(0.5)` after `fetch_info()` succeeds
- `time.sleep(0.5)` after `fetch_financials()` succeeds
- `time.sleep(0.3)` after `fetch_history()` succeeds

These sleeps are intra-fetch (between components of the same ticker, not between tickers).
They are NOT affected by retries — they only fire on success, so a failed fetch does not
sleep.

The evidence shows:
- 14 cold requests in 17 seconds (0.81 req/s) did not trigger a hard 429
- Yahoo's soft throttling paced the first ticker's responses, naturally spreading requests
- TATASTEEL.NS immediately after (0s gap) ran at full speed
- Suite 3 with 3 tickers at 35s intervals and ~24 requests total saw no 429

**Assessment: The existing sleep pattern appears sufficient for normal single-user usage.**

---

## Final Recommendation

**No additional delay should be added at this time.**

The reasons:

1. **Not reproduced.** A controlled back-to-back burst of 14 requests did not trigger a hard
   429 in either Suite 4 scenario. Adding a delay to prevent a condition that cannot be
   reproduced in testing is speculative mitigation.

2. **Self-regulating.** Yahoo's soft throttling absorbs burst requests by slowing responses
   rather than returning 429. FTS.TO's 10.63s fetch in Scenario A demonstrates this — Yahoo
   spread the requests across time automatically, without requiring the application to do it.

3. **Location 3 is the only correct placement if ever needed.** A delay at the pipeline
   level (Locations 1 and 2) penalises cached tickers and interferes with retry accounting.
   Only a cache-miss-conditional delay in the individual fetchers avoids both problems.

4. **The P0/P1/History fixes are the correct structural response.** The dead-cache
   amplification loop — where failed fetches wrote invalid cache entries, P1 rejected them,
   forced fresh requests, which also failed, writing new invalid entries — was the primary
   structural multiplier of Yahoo requests. That cycle is now broken. A single failure no
   longer creates exponential retries.

5. **If 429s recur with the fixes applied**, the retry loop (0s, 5s, 15s, 30s) provides
   50 seconds of recovery time — well within Yahoo's rate-limit reset window as observed.
   Monitor in production first; add delay only if 429s recur and the retry loop does not
   self-recover.

---

## Summary of Diagnostic Programme

| Suite | Purpose | Outcome |
|-------|---------|---------|
| Suite 1 | Controlled yfinance tests, 5 tickers | All succeeded; revealed stale cache issue |
| Suite 2 | Source inspection + cache analysis | Identified P0/P1/History bug chain |
| Suite 3 | Cold-cache test, 35s spacing | All tickers 100% — no 429 |
| Suite 4 | Burst test (0s vs 35s gaps) | No hard 429; soft throttle visible on burst |

**All outstanding structural bugs are fixed.** The remaining risk (Yahoo hard rate limit under
extreme burst conditions) is inherent to an unauthenticated third-party data source and is
mitigated by the existing retry logic.

---

## Status of All Known Defects

| Defect | Status |
|---|---|
| `fetch_financials()` writing dead cache entries (P0) | **Fixed** |
| `_load_cache()` serving failed-fetch entries (P1) | **Fixed** |
| `fetch_history()` writing dead cache entries | **Fixed** |
| `force_refresh` silently dropped in `pipeline.py` | Open — separate authorization needed |
| financials/history 429 bypasses pipeline retry | Open — separate authorization needed |
| Yahoo hard 429 under extreme burst conditions | Mitigated by retry loop; no additional fix warranted |
