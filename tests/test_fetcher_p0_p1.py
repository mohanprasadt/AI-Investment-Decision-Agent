"""
Phase 10.x — Tests for P0/P1/history fixes in data/ingestion/fetcher.py

P0: fetch_financials() treats all-empty DataFrames as a failed fetch
    and does not cache the result.
P1: _load_cache() treats a cached _fetch_success=False entry as a miss.
History fix: fetch_history() mirrors P0 — empty DataFrame is not cached;
    only successful (non-empty) history is written to cache.

All tests are fully deterministic — no network calls (yf.Ticker is mocked
or cache files are written directly).
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data.ingestion.fetcher as fetcher_module
from data.ingestion.fetcher import _load_cache, fetch_financials, fetch_history


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    """What yfinance returns when the endpoint is rate-limited / unavailable."""
    return pd.DataFrame()


def _income_df() -> pd.DataFrame:
    """Minimal income-statement-style DataFrame (fields × dates)."""
    cols = pd.to_datetime(["2024-12-31", "2023-12-31"])
    return pd.DataFrame(
        [[2_000_000_000, 1_800_000_000],
         [300_000_000,   260_000_000]],
        index=["Total Revenue", "Net Income"],
        columns=cols,
    )


def _balance_df() -> pd.DataFrame:
    cols = pd.to_datetime(["2024-12-31", "2023-12-31"])
    return pd.DataFrame(
        [[4_000_000_000, 3_800_000_000],
         [600_000_000,   580_000_000]],
        index=["Total Assets", "Total Debt"],
        columns=cols,
    )


def _cashflow_df() -> pd.DataFrame:
    cols = pd.to_datetime(["2024-12-31", "2023-12-31"])
    return pd.DataFrame(
        [[500_000_000, 450_000_000],
         [-80_000_000, -75_000_000]],
        index=["Operating Cash Flow", "Capital Expenditure"],
        columns=cols,
    )


def _mock_ticker(income=None, balance=None, cashflow=None) -> MagicMock:
    """Build a mock yf.Ticker with controllable statement DataFrames."""
    m = MagicMock()
    m.financials    = income   if income   is not None else _empty_df()
    m.balance_sheet = balance  if balance  is not None else _empty_df()
    m.cashflow      = cashflow if cashflow is not None else _empty_df()
    return m


# ---------------------------------------------------------------------------
# Fixture: redirect CACHE_DIR to a temp path for the test
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_cache(tmp_path, monkeypatch):
    """Redirect CACHE_DIR to an isolated temp directory."""
    monkeypatch.setattr(fetcher_module, "CACHE_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# P0 tests — fetch_financials() empty-DataFrame detection
# ---------------------------------------------------------------------------

class TestP0AllEmptyIsFailed:
    """P0: all three statements empty → _fetch_success=False, no cache file."""

    def test_all_empty_returns_failure(self, tmp_cache):
        """All three statements empty → _fetch_success=False."""
        ticker_mock = _mock_ticker()   # all three default to _empty_df()
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_financials("ENB.TO", force_refresh=True)

        assert result["_fetch_success"] is False, (
            "All-empty DataFrames must produce _fetch_success=False"
        )

    def test_all_empty_sets_fetch_error(self, tmp_cache):
        """All three statements empty → _fetch_error is populated."""
        ticker_mock = _mock_ticker()
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_financials("ENB.TO", force_refresh=True)

        assert result["_fetch_error"], (
            "_fetch_error must be set when all statements are empty"
        )
        assert "empty" in result["_fetch_error"].lower()

    def test_all_empty_not_cached(self, tmp_cache):
        """All three statements empty → no cache file written."""
        ticker_mock = _mock_ticker()
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_financials("ENB.TO", force_refresh=True)

        cache_file = tmp_cache / "ENB_TO_financials.json"
        assert not cache_file.exists(), (
            "A failed (all-empty) financials fetch must not create a cache file"
        )


class TestP0ValidDataCached:
    """P0: valid DataFrames → _fetch_success=True, cache file written."""

    def test_valid_data_returns_success(self, tmp_cache):
        """Full data → _fetch_success=True."""
        ticker_mock = _mock_ticker(
            income=_income_df(), balance=_balance_df(), cashflow=_cashflow_df()
        )
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_financials("ITC.NS", force_refresh=True)

        assert result["_fetch_success"] is True

    def test_valid_data_written_to_cache(self, tmp_cache):
        """Full data → cache file exists after fetch."""
        ticker_mock = _mock_ticker(
            income=_income_df(), balance=_balance_df(), cashflow=_cashflow_df()
        )
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_financials("ITC.NS", force_refresh=True)

        cache_file = tmp_cache / "ITC_NS_financials.json"
        assert cache_file.exists(), "Successful fetch must write a cache file"

    def test_valid_data_cache_has_correct_content(self, tmp_cache):
        """Cached file has _fetch_success=True and non-empty income_stmt."""
        ticker_mock = _mock_ticker(
            income=_income_df(), balance=_balance_df(), cashflow=_cashflow_df()
        )
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_financials("ITC.NS", force_refresh=True)

        cache_file = tmp_cache / "ITC_NS_financials.json"
        with open(cache_file) as f:
            cached = json.load(f)

        assert cached["_fetch_success"] is True
        assert cached["income_stmt"]    # non-empty dict
        assert "Total Revenue" in cached["income_stmt"]

    def test_second_call_uses_cache(self, tmp_cache):
        """Second call within TTL returns cache hit; yfinance not called again."""
        ticker_mock = _mock_ticker(
            income=_income_df(), balance=_balance_df(), cashflow=_cashflow_df()
        )
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock) as mock_cls:
            fetch_financials("ITC.NS", force_refresh=True)   # first: hits yfinance
            fetch_financials("ITC.NS")                        # second: should use cache

        assert mock_cls.call_count == 1, (
            "yf.Ticker should only be called once; second call should use cache"
        )


class TestP0PartialData:
    """P0: partial data (at least one non-empty statement) → success."""

    def test_income_only_is_success(self, tmp_cache):
        """Income stmt populated, balance and cash flow empty → success (partial data)."""
        ticker_mock = _mock_ticker(
            income=_income_df(),   # has data
            balance=_empty_df(),   # empty
            cashflow=_empty_df(),  # empty
        )
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_financials("PARTIAL.TO", force_refresh=True)

        assert result["_fetch_success"] is True, (
            "Partial data (income only) must still be treated as success"
        )
        assert result["income_stmt"], "income_stmt should be populated"
        assert not result["balance_sheet"], "balance_sheet should be empty"

    def test_income_only_is_cached(self, tmp_cache):
        """Partial success must be written to cache."""
        ticker_mock = _mock_ticker(income=_income_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_financials("PARTIAL.TO", force_refresh=True)

        cache_file = tmp_cache / "PARTIAL_TO_financials.json"
        assert cache_file.exists(), "Partial success must be cached"

    def test_balance_only_is_success(self, tmp_cache):
        """Balance sheet only → success."""
        ticker_mock = _mock_ticker(balance=_balance_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_financials("PARTIAL2.TO", force_refresh=True)

        assert result["_fetch_success"] is True
        assert result["balance_sheet"]
        assert not result["income_stmt"]

    def test_cashflow_only_is_success(self, tmp_cache):
        """Cash flow only → success."""
        ticker_mock = _mock_ticker(cashflow=_cashflow_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_financials("PARTIAL3.TO", force_refresh=True)

        assert result["_fetch_success"] is True
        assert result["cash_flow"]
        assert not result["income_stmt"]


class TestP0ExceptionPath:
    """P0: yfinance raises → existing exception-path behavior unchanged."""

    def test_exception_returns_failure(self, tmp_cache):
        """Exception from yfinance → _fetch_success=False, _fetch_error set."""
        with patch("data.ingestion.fetcher.yf.Ticker", side_effect=RuntimeError("network error")):
            result = fetch_financials("ERR.TO", force_refresh=True)

        assert result["_fetch_success"] is False
        assert "network error" in result["_fetch_error"]

    def test_exception_not_cached(self, tmp_cache):
        """Exception from yfinance → no cache file (existing behavior)."""
        with patch("data.ingestion.fetcher.yf.Ticker", side_effect=RuntimeError("network error")):
            fetch_financials("ERR.TO", force_refresh=True)

        cache_file = tmp_cache / "ERR_TO_financials.json"
        assert not cache_file.exists()


# ---------------------------------------------------------------------------
# P1 tests — _load_cache() treats _fetch_success=False as cache miss
# ---------------------------------------------------------------------------

class TestP1CacheMissOnFailure:
    """P1: a cached entry with _fetch_success=False is treated as a miss."""

    def _write_cache_entry(self, tmp_cache, ticker, data_type, fetch_success, extra=None):
        """Write a controlled cache entry directly to the temp cache dir."""
        safe = ticker.replace(".", "_")
        path = tmp_cache / f"{safe}_{data_type}.json"
        entry = {
            "_ticker": ticker,
            "_fetched_at": datetime.utcnow().isoformat(),
            "_fetch_success": fetch_success,
            "_fetch_error": None if fetch_success else "prior failure",
            "income_stmt": {},
            "balance_sheet": {},
            "cash_flow": {},
        }
        if extra:
            entry.update(extra)
        with open(path, "w") as f:
            json.dump(entry, f)
        return path

    def test_failed_cache_returns_none(self, tmp_cache):
        """_load_cache returns None for a _fetch_success=False entry within TTL."""
        self._write_cache_entry(tmp_cache, "ENB.TO", "financials", fetch_success=False)

        result = _load_cache("ENB.TO", "financials", max_age_hours=48)
        assert result is None, (
            "_load_cache must return None (cache miss) for _fetch_success=False entries"
        )

    def test_successful_cache_still_returned(self, tmp_cache):
        """_load_cache returns the entry for a _fetch_success=True entry within TTL."""
        self._write_cache_entry(
            tmp_cache, "ITC.NS", "financials", fetch_success=True,
            extra={"income_stmt": {"Total Revenue": {2024: 1e9}}}
        )

        result = _load_cache("ITC.NS", "financials", max_age_hours=48)
        assert result is not None, "Successful cache entry must still be returned"
        assert result["_fetch_success"] is True

    def test_failed_history_cache_returns_none(self, tmp_cache):
        """P1 applies to history cache as well."""
        safe = "ENB_TO"
        path = tmp_cache / f"{safe}_history_5y.json"
        entry = {
            "_ticker": "ENB.TO",
            "_fetched_at": datetime.utcnow().isoformat(),
            "_fetch_success": False,
            "_fetch_error": "empty history",
            "dates": [],
            "closes": [],
        }
        with open(path, "w") as f:
            json.dump(entry, f)

        result = _load_cache("ENB.TO", "history_5y", max_age_hours=24)
        assert result is None, "Failed history cache must also be treated as a miss"

    def test_expired_cache_still_returns_none(self, tmp_cache):
        """Expired successful cache → None (existing TTL behavior unchanged)."""
        safe = "OLD_TO"
        path = tmp_cache / f"{safe}_financials.json"
        old_time = (datetime.utcnow() - timedelta(hours=50)).isoformat()
        entry = {
            "_ticker": "OLD.TO",
            "_fetched_at": old_time,
            "_fetch_success": True,
            "income_stmt": {"Total Revenue": {2024: 1e9}},
        }
        with open(path, "w") as f:
            json.dump(entry, f)

        result = _load_cache("OLD.TO", "financials", max_age_hours=48)
        assert result is None, "Expired cache must return None regardless of _fetch_success"

    def test_no_cache_file_returns_none(self, tmp_cache):
        """No cache file → None (unchanged behavior)."""
        result = _load_cache("NOCACHE.TO", "financials", max_age_hours=48)
        assert result is None

    def test_missing_fetch_success_key_treated_as_success(self, tmp_cache):
        """Entry with no _fetch_success key → treated as success (backward-compatible)."""
        safe = "LEGACY_TO"
        path = tmp_cache / f"{safe}_financials.json"
        entry = {
            "_ticker": "LEGACY.TO",
            "_fetched_at": datetime.utcnow().isoformat(),
            # _fetch_success key intentionally absent (old cache format)
            "income_stmt": {"Total Revenue": {2024: 1e9}},
        }
        with open(path, "w") as f:
            json.dump(entry, f)

        result = _load_cache("LEGACY.TO", "financials", max_age_hours=48)
        assert result is not None, (
            "Cache entries without _fetch_success key must be treated as "
            "successful (backward-compatible with old cache format)"
        )


# ---------------------------------------------------------------------------
# Integration: P0 + P1 together
# ---------------------------------------------------------------------------

class TestP0P1Integration:
    """End-to-end: failed fetch → no cache written → next call retries yfinance."""

    def test_failed_fetch_then_retry(self, tmp_cache):
        """
        First call: all-empty → not cached.
        Second call: yfinance now returns real data → success cached.
        """
        empty_ticker = _mock_ticker()   # all empty
        real_ticker  = _mock_ticker(
            income=_income_df(), balance=_balance_df(), cashflow=_cashflow_df()
        )

        with patch("data.ingestion.fetcher.yf.Ticker") as mock_cls:
            mock_cls.side_effect = [empty_ticker, real_ticker]

            r1 = fetch_financials("ENB.TO", force_refresh=True)
            r2 = fetch_financials("ENB.TO")   # no force_refresh — tests cache path

        assert r1["_fetch_success"] is False, "First call (empty) must fail"
        assert r2["_fetch_success"] is True,  "Second call (real data) must succeed"
        assert mock_cls.call_count == 2, (
            "yf.Ticker must be called twice — first failed result was not cached, "
            "so second call must hit yfinance again"
        )

    def test_existing_dead_cache_entry_triggers_retry(self, tmp_cache):
        """
        Pre-existing _fetch_success=False cache file (e.g. from before P0 fix).
        P1 must treat it as a miss, causing yfinance to be called.
        """
        # Write a dead cache entry directly (simulates pre-P0 state)
        safe = "FTS_TO"
        path = tmp_cache / f"{safe}_financials.json"
        dead_entry = {
            "_ticker": "FTS.TO",
            "_fetched_at": datetime.utcnow().isoformat(),
            "_fetch_success": True,   # old bug: was marked True even though 0 rows
            "income_stmt": {},
            "balance_sheet": {},
            "cash_flow": {},
        }
        with open(path, "w") as f:
            json.dump(dead_entry, f)

        # This dead entry has _fetch_success=True but empty data — simulates the
        # old bug.  P1 only checks _fetch_success, so this entry IS served (True).
        # Separately verify P1 handles _fetch_success=False entries correctly.
        dead_false_entry = dead_entry.copy()
        dead_false_entry["_fetch_success"] = False
        path2 = tmp_cache / "CNQ_TO_financials.json"
        with open(path2, "w") as f:
            json.dump(dead_false_entry, f)

        # P1: _fetch_success=False → cache miss → yfinance called
        real_ticker = _mock_ticker(income=_income_df(), balance=_balance_df(), cashflow=_cashflow_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=real_ticker) as mock_cls:
            result = fetch_financials("CNQ.TO")

        assert result["_fetch_success"] is True
        assert mock_cls.call_count == 1, (
            "P1 must cause a cache miss on the _fetch_success=False entry, "
            "prompting a fresh yfinance call"
        )


# ---------------------------------------------------------------------------
# History fix tests — fetch_history() mirrors P0: empty result not cached
# ---------------------------------------------------------------------------

def _history_df() -> "pd.DataFrame":
    """Non-empty price history DataFrame (dates × Close)."""
    dates  = pd.date_range("2024-01-02", periods=10, freq="B")
    closes = [100.0 + i for i in range(10)]
    return pd.DataFrame({"Close": closes}, index=dates)


def _mock_ticker_history(hist_df) -> MagicMock:
    """Build a mock yf.Ticker whose .history() returns hist_df."""
    m = MagicMock()
    m.history.return_value = hist_df
    return m


class TestHistoryEmptyNotCached:
    """History fix: empty history DataFrame → _fetch_success=False, not cached."""

    def test_empty_history_returns_failure(self, tmp_cache):
        """Empty history DataFrame → _fetch_success=False."""
        ticker_mock = _mock_ticker_history(_empty_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_history("FTS.TO", force_refresh=True)

        assert result["_fetch_success"] is False, (
            "Empty history must produce _fetch_success=False"
        )

    def test_empty_history_sets_error(self, tmp_cache):
        """Empty history DataFrame → _fetch_error is populated."""
        ticker_mock = _mock_ticker_history(_empty_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_history("FTS.TO", force_refresh=True)

        assert result["_fetch_error"], "_fetch_error must be set on empty history"
        assert "empty" in result["_fetch_error"].lower()

    def test_empty_history_not_cached(self, tmp_cache):
        """Empty history → no cache file written."""
        ticker_mock = _mock_ticker_history(_empty_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_history("FTS.TO", force_refresh=True)

        cache_file = tmp_cache / "FTS_TO_history_5y.json"
        assert not cache_file.exists(), (
            "A failed (empty) history fetch must not create a cache file"
        )

    def test_empty_history_no_dates(self, tmp_cache):
        """Empty history → dates and closes lists are empty."""
        ticker_mock = _mock_ticker_history(_empty_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_history("FTS.TO", force_refresh=True)

        assert result["dates"] == []
        assert result["closes"] == []


class TestHistorySuccessCached:
    """History fix: valid history → _fetch_success=True, cached correctly."""

    def test_valid_history_returns_success(self, tmp_cache):
        """Non-empty history DataFrame → _fetch_success=True."""
        ticker_mock = _mock_ticker_history(_history_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_history("ENB.TO", force_refresh=True)

        assert result["_fetch_success"] is True

    def test_valid_history_populates_dates(self, tmp_cache):
        """Non-empty history → dates and closes lists populated."""
        ticker_mock = _mock_ticker_history(_history_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            result = fetch_history("ENB.TO", force_refresh=True)

        assert len(result["dates"]) == 10
        assert len(result["closes"]) == 10

    def test_valid_history_written_to_cache(self, tmp_cache):
        """Non-empty history → cache file exists after fetch."""
        ticker_mock = _mock_ticker_history(_history_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_history("ENB.TO", force_refresh=True)

        cache_file = tmp_cache / "ENB_TO_history_5y.json"
        assert cache_file.exists(), "Successful history must write a cache file"

    def test_valid_history_cache_content(self, tmp_cache):
        """Cache file for valid history has correct content."""
        ticker_mock = _mock_ticker_history(_history_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock):
            fetch_history("ENB.TO", force_refresh=True)

        with open(tmp_cache / "ENB_TO_history_5y.json") as f:
            cached = json.load(f)

        assert cached["_fetch_success"] is True
        assert len(cached["dates"]) == 10
        assert len(cached["closes"]) == 10

    def test_second_call_uses_cache(self, tmp_cache):
        """Second call within TTL returns cache hit; yfinance not called again."""
        ticker_mock = _mock_ticker_history(_history_df())
        with patch("data.ingestion.fetcher.yf.Ticker", return_value=ticker_mock) as mock_cls:
            fetch_history("ENB.TO", force_refresh=True)   # first: hits yfinance
            fetch_history("ENB.TO")                        # second: should use cache

        assert mock_cls.call_count == 1, (
            "yf.Ticker should be called once; second call must use cache"
        )


class TestHistoryExceptionNotCached:
    """History fix: exception path — existing behavior preserved (no cache write)."""

    def test_exception_returns_failure(self, tmp_cache):
        """Exception from yfinance → _fetch_success=False, _fetch_error set."""
        with patch("data.ingestion.fetcher.yf.Ticker",
                   side_effect=RuntimeError("connection refused")):
            result = fetch_history("ERR.TO", force_refresh=True)

        assert result["_fetch_success"] is False
        assert "connection refused" in result["_fetch_error"]

    def test_exception_not_cached(self, tmp_cache):
        """Exception from yfinance → no cache file written."""
        with patch("data.ingestion.fetcher.yf.Ticker",
                   side_effect=RuntimeError("connection refused")):
            fetch_history("ERR.TO", force_refresh=True)

        cache_file = tmp_cache / "ERR_TO_history_5y.json"
        assert not cache_file.exists()


class TestHistoryP1Interaction:
    """Verify that P1 still rejects any pre-existing ok=False history cache entries."""

    def test_p1_rejects_preexisting_dead_history_cache(self, tmp_cache):
        """
        A pre-existing ok=False history cache (written before this fix was deployed)
        must still be treated as a cache miss by P1 so yfinance is retried.
        """
        # Write a dead entry directly (simulates a file written by old buggy code)
        path = tmp_cache / "AAPL_history_5y.json"
        dead_entry = {
            "_ticker": "AAPL",
            "_fetched_at": datetime.utcnow().isoformat(),
            "_fetch_success": False,
            "_fetch_error": "prior empty result",
            "dates": [],
            "closes": [],
        }
        with open(path, "w") as f:
            json.dump(dead_entry, f)

        # P1 must reject this, causing yfinance to be called
        good_ticker = _mock_ticker_history(_history_df())
        with patch("data.ingestion.fetcher.yf.Ticker",
                   return_value=good_ticker) as mock_cls:
            result = fetch_history("AAPL")

        assert result["_fetch_success"] is True, (
            "After P1 rejects the dead cache, the fresh fetch must succeed"
        )
        assert mock_cls.call_count == 1, (
            "P1 must cause a cache miss, prompting one fresh yfinance call"
        )

    def test_p1_serves_valid_history_from_cache(self, tmp_cache):
        """A valid ok=True history cache must be served without calling yfinance."""
        path = tmp_cache / "ITC_NS_history_5y.json"
        good_entry = {
            "_ticker": "ITC.NS",
            "_fetched_at": datetime.utcnow().isoformat(),
            "_fetch_success": True,
            "_fetch_error": None,
            "dates": ["2024-01-02", "2024-01-03"],
            "closes": [278.0, 279.5],
        }
        with open(path, "w") as f:
            json.dump(good_entry, f)

        with patch("data.ingestion.fetcher.yf.Ticker") as mock_cls:
            result = fetch_history("ITC.NS")

        assert result["_fetch_success"] is True
        assert mock_cls.call_count == 0, "Valid cache must be served without hitting yfinance"


class TestHistoryRetryBehaviourAfterFix:
    """
    Verify that after the history fix, the failed→retry→success path works:
    empty history on attempt 1 (not cached) → real history on attempt 2 → cached.
    """

    def test_empty_then_success_retries_yfinance(self, tmp_cache):
        """
        First call: empty history → not cached.
        Second call (no force_refresh): no cache file, so yfinance called again.
        Second call succeeds → cached.
        """
        empty_ticker = _mock_ticker_history(_empty_df())
        real_ticker  = _mock_ticker_history(_history_df())

        with patch("data.ingestion.fetcher.yf.Ticker") as mock_cls:
            mock_cls.side_effect = [empty_ticker, real_ticker]

            r1 = fetch_history("FTS.TO", force_refresh=True)
            r2 = fetch_history("FTS.TO")   # no force_refresh: cache miss → retry

        assert r1["_fetch_success"] is False, "First call (empty) must fail"
        assert r2["_fetch_success"] is True,  "Second call (real data) must succeed"
        assert mock_cls.call_count == 2, (
            "yf.Ticker must be called twice — empty result was not cached, "
            "so second call retries yfinance"
        )

    def test_empty_history_allows_immediate_retry(self, tmp_cache):
        """
        Because empty history is not cached, a second force_refresh=True call
        goes straight to yfinance without any P1 rejection detour.
        """
        empty_ticker = _mock_ticker_history(_empty_df())
        real_ticker  = _mock_ticker_history(_history_df())

        with patch("data.ingestion.fetcher.yf.Ticker") as mock_cls:
            mock_cls.side_effect = [empty_ticker, real_ticker]
            r1 = fetch_history("FTS.TO", force_refresh=True)
            r2 = fetch_history("FTS.TO", force_refresh=True)  # bypass cache check

        assert r1["_fetch_success"] is False
        assert r2["_fetch_success"] is True


# ---------------------------------------------------------------------------
# fetch_ticker() short-circuit tests
# Fix: when fetch_info() fails, fetch_financials() and fetch_history() are
# skipped entirely to avoid extending Yahoo's rate-limit window.
# ---------------------------------------------------------------------------

class TestFetchTickerShortCircuit:
    """
    Verify the short-circuit behaviour introduced in fetch_ticker():
    - info failure → financials and history NOT called (no extra Yahoo requests)
    - returned structure is valid and clearly marked as skipped
    - info success → proceeds to financials and history normally
    """

    def test_info_failure_does_not_call_financials(self, tmp_cache):
        """When fetch_info() fails, fetch_financials() must not be called."""
        failed_info = {"_ticker": "SU.TO", "_fetch_success": False,
                       "_fetch_error": "429 Too Many Requests"}

        with patch("data.ingestion.fetcher.fetch_info", return_value=failed_info) as mock_info, \
             patch("data.ingestion.fetcher.fetch_financials") as mock_fin, \
             patch("data.ingestion.fetcher.fetch_history") as mock_hist:
            fetcher_module.fetch_ticker("SU.TO", force_refresh=True)

        mock_fin.assert_not_called()

    def test_info_failure_does_not_call_history(self, tmp_cache):
        """When fetch_info() fails, fetch_history() must not be called."""
        failed_info = {"_ticker": "SU.TO", "_fetch_success": False,
                       "_fetch_error": "429 Too Many Requests"}

        with patch("data.ingestion.fetcher.fetch_info", return_value=failed_info), \
             patch("data.ingestion.fetcher.fetch_financials") as mock_fin, \
             patch("data.ingestion.fetcher.fetch_history") as mock_hist:
            fetcher_module.fetch_ticker("SU.TO", force_refresh=True)

        mock_hist.assert_not_called()

    def test_info_failure_returns_valid_structure(self, tmp_cache):
        """Skipped result has all required top-level keys."""
        failed_info = {"_ticker": "SU.TO", "_fetch_success": False,
                       "_fetch_error": "429 Too Many Requests"}

        with patch("data.ingestion.fetcher.fetch_info", return_value=failed_info), \
             patch("data.ingestion.fetcher.fetch_financials"), \
             patch("data.ingestion.fetcher.fetch_history"):
            result = fetcher_module.fetch_ticker("SU.TO", force_refresh=True)

        assert "info" in result
        assert "financials" in result
        assert "history" in result
        assert "is_etf" in result

    def test_info_failure_stubs_financials_as_failed(self, tmp_cache):
        """Skipped financials component is marked _fetch_success=False."""
        failed_info = {"_ticker": "SU.TO", "_fetch_success": False,
                       "_fetch_error": "429 Too Many Requests"}

        with patch("data.ingestion.fetcher.fetch_info", return_value=failed_info), \
             patch("data.ingestion.fetcher.fetch_financials"), \
             patch("data.ingestion.fetcher.fetch_history"):
            result = fetcher_module.fetch_ticker("SU.TO", force_refresh=True)

        fin = result["financials"]
        assert fin["_fetch_success"] is False
        assert fin["_fetch_error"]   # non-empty reason
        assert fin["income_stmt"]   == {}
        assert fin["balance_sheet"] == {}
        assert fin["cash_flow"]     == {}

    def test_info_failure_stubs_history_as_failed(self, tmp_cache):
        """Skipped history component is marked _fetch_success=False."""
        failed_info = {"_ticker": "SU.TO", "_fetch_success": False,
                       "_fetch_error": "429 Too Many Requests"}

        with patch("data.ingestion.fetcher.fetch_info", return_value=failed_info), \
             patch("data.ingestion.fetcher.fetch_financials"), \
             patch("data.ingestion.fetcher.fetch_history"):
            result = fetcher_module.fetch_ticker("SU.TO", force_refresh=True)

        hist = result["history"]
        assert hist["_fetch_success"] is False
        assert hist["_fetch_error"]   # non-empty reason
        assert hist["dates"]  == []
        assert hist["closes"] == []

    def test_info_failure_preserves_failed_info_result(self, tmp_cache):
        """The failed info dict returned by fetch_info() is passed through unchanged."""
        failed_info = {"_ticker": "SU.TO", "_fetch_success": False,
                       "_fetch_error": "429 Too Many Requests",
                       "someExtraKey": "preserved"}

        with patch("data.ingestion.fetcher.fetch_info", return_value=failed_info), \
             patch("data.ingestion.fetcher.fetch_financials"), \
             patch("data.ingestion.fetcher.fetch_history"):
            result = fetcher_module.fetch_ticker("SU.TO", force_refresh=True)

        assert result["info"] is failed_info
        assert result["info"]["someExtraKey"] == "preserved"

    def test_info_success_calls_financials(self, tmp_cache):
        """When fetch_info() succeeds, fetch_financials() is still called."""
        good_info = {"_ticker": "ENB.TO", "_fetch_success": True,
                     "longName": "Enbridge Inc.", "currentPrice": 70.0}
        fin_result = {"_ticker": "ENB.TO", "_fetch_success": True,
                      "income_stmt": {"Revenue": {2024: 1e9}},
                      "balance_sheet": {}, "cash_flow": {}}
        hist_result = {"_ticker": "ENB.TO", "_fetch_success": True,
                       "dates": ["2024-01-02"], "closes": [60.0]}

        with patch("data.ingestion.fetcher.fetch_info", return_value=good_info), \
             patch("data.ingestion.fetcher.fetch_financials",
                   return_value=fin_result) as mock_fin, \
             patch("data.ingestion.fetcher.fetch_history",
                   return_value=hist_result):
            fetcher_module.fetch_ticker("ENB.TO", force_refresh=True)

        mock_fin.assert_called_once()

    def test_info_success_calls_history(self, tmp_cache):
        """When fetch_info() succeeds, fetch_history() is still called."""
        good_info = {"_ticker": "ENB.TO", "_fetch_success": True,
                     "longName": "Enbridge Inc.", "currentPrice": 70.0}
        fin_result = {"_ticker": "ENB.TO", "_fetch_success": True,
                      "income_stmt": {}, "balance_sheet": {}, "cash_flow": {}}
        hist_result = {"_ticker": "ENB.TO", "_fetch_success": True,
                       "dates": ["2024-01-02"], "closes": [60.0]}

        with patch("data.ingestion.fetcher.fetch_info", return_value=good_info), \
             patch("data.ingestion.fetcher.fetch_financials",
                   return_value=fin_result), \
             patch("data.ingestion.fetcher.fetch_history",
                   return_value=hist_result) as mock_hist:
            fetcher_module.fetch_ticker("ENB.TO", force_refresh=True)

        mock_hist.assert_called_once()

    def test_info_success_returns_real_financials_and_history(self, tmp_cache):
        """When info succeeds, the returned financials/history come from the real fetchers."""
        good_info = {"_ticker": "ENB.TO", "_fetch_success": True,
                     "longName": "Enbridge Inc.", "currentPrice": 70.0}
        fin_result = {"_ticker": "ENB.TO", "_fetch_success": True,
                      "income_stmt": {"Revenue": {2024: 1e9}},
                      "balance_sheet": {}, "cash_flow": {}}
        hist_result = {"_ticker": "ENB.TO", "_fetch_success": True,
                       "dates": ["2024-01-02"], "closes": [60.0]}

        with patch("data.ingestion.fetcher.fetch_info", return_value=good_info), \
             patch("data.ingestion.fetcher.fetch_financials",
                   return_value=fin_result), \
             patch("data.ingestion.fetcher.fetch_history",
                   return_value=hist_result):
            result = fetcher_module.fetch_ticker("ENB.TO", force_refresh=True)

        assert result["financials"] is fin_result
        assert result["history"] is hist_result


# ---------------------------------------------------------------------------
# Pipeline retry schedule tests
# ---------------------------------------------------------------------------

class TestPipelineRetrySchedule:
    """
    Phase 10.5: verify fail-fast 429 behaviour.

    The old retry loop (_RETRY_DELAYS = [30, 60]) was removed in Phase 10.5.
    The interactive pipeline now fails immediately on 429 so the user sees a
    clear error message instead of a 90-second frozen spinner.

    Retry logic lives in scripts/prewarm_mvp.py (non-interactive path).
    """

    def test_no_retry_loop_in_pipeline_source(self):
        """_RETRY_DELAYS must NOT exist in run_analysis_pipeline — retry was removed."""
        import inspect
        import analytics.agent.pipeline as pipeline_mod
        src = inspect.getsource(pipeline_mod.run_analysis_pipeline)
        assert "_RETRY_DELAYS" not in src, (
            "Retry loop (_RETRY_DELAYS) was removed in Phase 10.5 but is still "
            "present in run_analysis_pipeline source. Remove it."
        )

    def test_total_attempts_is_one_on_429(self):
        """On a 429 response, load_ticker must be called exactly once (fail-fast)."""
        from unittest.mock import patch
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE
        from analytics.agent.pipeline import run_analysis_pipeline

        failing_result = DataLoadResult(
            ticker="RATE.XX",
            cannot_complete_reason=f"{CANNOT_COMPLETE}: 429 Too Many Requests",
        )

        call_count = []

        def _failing_load(**kwargs):
            call_count.append(1)
            return failing_result

        with patch("analytics.agent.pipeline.load_ticker",
                   side_effect=_failing_load):
            run_analysis_pipeline("RATE.XX")

        assert len(call_count) == 1, (
            f"Fail-fast: expected exactly 1 attempt on 429, got {len(call_count)}. "
            "The retry loop must have been removed."
        )

    def test_non_429_error_also_one_attempt(self):
        """Non-429 errors also get exactly one attempt (fail-fast applies to all)."""
        from unittest.mock import patch
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE
        from analytics.agent.pipeline import run_analysis_pipeline

        other_failure = DataLoadResult(
            ticker="BAD.XX",
            cannot_complete_reason=f"{CANNOT_COMPLETE}: ticker not found",
        )

        call_count = []

        def _one_shot(**kwargs):
            call_count.append(1)
            return other_failure

        with patch("analytics.agent.pipeline.load_ticker",
                   side_effect=_one_shot):
            run_analysis_pipeline("BAD.XX")

        assert len(call_count) == 1, (
            f"Non-429 error should be one attempt; got {len(call_count)}"
        )

    def test_429_sets_is_rate_limited_true(self):
        """Pipeline must set PipelineResult.is_rate_limited=True on 429."""
        from unittest.mock import patch
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE
        from analytics.agent.pipeline import run_analysis_pipeline

        failing_result = DataLoadResult(
            ticker="SU.TO",
            cannot_complete_reason=f"{CANNOT_COMPLETE}: 429 Too Many Requests",
        )

        with patch("analytics.agent.pipeline.load_ticker",
                   return_value=failing_result):
            result = run_analysis_pipeline("SU.TO")

        assert result.is_rate_limited is True, (
            "is_rate_limited must be True when 429 is in the error reason"
        )
        assert result.ok is False

    def test_no_sleep_on_429(self):
        """time.sleep must NOT be called in the interactive pipeline path."""
        from unittest.mock import patch
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE
        from analytics.agent.pipeline import run_analysis_pipeline

        failing_result = DataLoadResult(
            ticker="SU.TO",
            cannot_complete_reason=f"{CANNOT_COMPLETE}: 429 Too Many Requests",
        )

        with patch("analytics.agent.pipeline.load_ticker",
                   return_value=failing_result), \
             patch("time.sleep") as mock_sleep:
            run_analysis_pipeline("SU.TO")

        mock_sleep.assert_not_called()
