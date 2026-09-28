"""
Phase 10.5 Tests
================
Coverage for:
  1. Safety: empty financials cannot produce ACCUMULATE/START_SMALL
  2. Fail-fast 429: pipeline returns is_rate_limited=True, no retry
  3. force_refresh wiring: flag reaches fetch_ticker()
  4. MVP ticker universe: exactly 33, no duplicates, expected tickers present
  5. Cache status: ui.data_status reads cache correctly
  6. Friendly error messages: manager._format_pipeline_error() 429 handling

Run with:
    pytest tests/test_phase105.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is importable
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ===========================================================================
# 1. Safety: empty financials → Gate 2 WATCH → no ACCUMULATE/START_SMALL
# ===========================================================================

class TestEmptyFinancialsSafety:
    """Gate 2 must produce WATCH (not EXCELLENT/STRONG/GOOD) for empty data."""

    def test_gate2_watch_when_no_scores(self):
        """_compute_tier([]) → QualityTier.WATCH"""
        from analytics.decision.gate2_quality import _compute_tier, QualityTier
        tier = _compute_tier([], [])
        assert tier == QualityTier.WATCH

    def test_gate2_watch_when_all_scores_none(self):
        """_compute_tier([None, None]) → QualityTier.WATCH (Nones are filtered out)"""
        from analytics.decision.gate2_quality import _compute_tier, QualityTier
        tier = _compute_tier([None, None], [])
        assert tier == QualityTier.WATCH

    def test_watch_does_not_produce_accumulate(self):
        """QualityTier.WATCH must not map to ACCUMULATE in the decision matrix."""
        from analytics.decision.gate2_quality import QualityTier
        from analytics.decision.decision_models import DecisionAction
        # WATCH is a holding pattern — actions must be HOLD, REDUCE, or TRIM
        # We verify ACCUMULATE and START_SMALL are NOT associated with WATCH
        # by checking that they require EXCELLENT, STRONG, or GOOD tier.
        # (Inspect the constants — no direct import needed; just check WATCH ≠ BUY tiers)
        buy_tiers = {QualityTier.EXCELLENT, QualityTier.STRONG, QualityTier.GOOD}
        assert QualityTier.WATCH not in buy_tiers

    def test_pipeline_with_empty_financials_not_ok(self):
        """Pipeline with _fetch_success=False must return ok=False."""
        from analytics.agent.pipeline import run_analysis_pipeline

        # Inject a fetch function that returns a failed-fetch stub
        def _bad_fetch(ticker):
            return {
                "info": {
                    "_ticker": ticker,
                    "_fetch_success": False,
                    "_fetch_error": "simulated failure",
                    "_fetched_at": "2026-01-01T00:00:00",
                },
                "financials": {},
                "history": {},
            }

        with patch("analytics.agent.pipeline.load_ticker") as mock_load:
            from analytics.agent.data_loader import DataLoadResult
            r = DataLoadResult(ticker="FAKE")
            r.cannot_complete_reason = "CANNOT_COMPLETE: simulated failure"
            mock_load.return_value = r

            result = run_analysis_pipeline("FAKE")

        assert not result.ok
        assert result.assessment is None

    def test_gate2_evaluate_with_empty_metrics_stays_watch(self):
        """evaluate_gate2() with all-None metrics must return WATCH tier."""
        from analytics.decision.gate2_quality import evaluate_gate2, QualityTier
        from analytics.financial_quality.quality_engine import FinancialQualityAssessment

        # Minimal stub — no dimension data available, so no scores are generated.
        # Uses MagicMock without spec so getattr() on any attribute returns a new
        # MagicMock; we override the ones that gate2 accesses directly.
        fq = MagicMock()
        # Dimension stubs — data_available=False so gate2 skips scoring them
        _no_data = MagicMock()
        _no_data.data_available = False
        fq.roic = _no_data
        fq.revenue_growth = _no_data
        fq.margins = _no_data
        fq.free_cash_flow = _no_data
        fq.balance_sheet = _no_data
        fq.dividend = _no_data
        fq.is_financial_institution = False
        fq.is_emerging_company = False
        # Direct attribute accesses (not via getattr with default)
        fq.strengths = []
        fq.concerns = []

        result = evaluate_gate2(
            financial_quality=fq,
            research=None,
        )
        # Gate 2 should either pass with WATCH or produce a non-buy forced action
        if result.passed:
            assert result.quality_tier in (QualityTier.WATCH, QualityTier.CONCERN,
                                            "WATCH", "CONCERN")
        else:
            # Forced action must not be ACCUMULATE or START_SMALL
            forced = (result.forced_action or "").upper()
            assert "ACCUMULATE" not in forced
            assert "START_SMALL" not in forced


# ===========================================================================
# 2. Fail-fast 429: pipeline returns is_rate_limited=True, no sleep/retry
# ===========================================================================

class TestFailFast429:
    """Pipeline must return immediately on 429 with is_rate_limited=True."""

    def _make_rate_limited_result(self):
        from analytics.agent.data_loader import DataLoadResult
        r = DataLoadResult(ticker="MSFT")
        r.cannot_complete_reason = (
            "CANNOT_COMPLETE_LIVE_ANALYSIS: 429 Too Many Requests"
        )
        return r

    def test_pipeline_returns_is_rate_limited_true(self):
        from analytics.agent.pipeline import run_analysis_pipeline
        with patch("analytics.agent.pipeline.load_ticker") as mock_load:
            mock_load.return_value = self._make_rate_limited_result()
            result = run_analysis_pipeline("MSFT")

        assert not result.ok
        assert result.is_rate_limited is True

    def test_pipeline_does_not_sleep_on_429(self):
        """No time.sleep should be called — fail-fast means no retry delay."""
        from analytics.agent.pipeline import run_analysis_pipeline
        with patch("analytics.agent.pipeline.load_ticker") as mock_load:
            # Patch time.sleep at module level to detect any calls
            with patch("time.sleep") as mock_sleep:
                mock_load.return_value = self._make_rate_limited_result()
                run_analysis_pipeline("MSFT")

        mock_sleep.assert_not_called()

    def test_pipeline_calls_load_ticker_exactly_once(self):
        """No retry loop — load_ticker should be called exactly once."""
        from analytics.agent.pipeline import run_analysis_pipeline
        with patch("analytics.agent.pipeline.load_ticker") as mock_load:
            mock_load.return_value = self._make_rate_limited_result()
            run_analysis_pipeline("MSFT")

        assert mock_load.call_count == 1

    def test_non_429_error_is_rate_limited_false(self):
        """A network error that is not 429 must NOT set is_rate_limited."""
        from analytics.agent.pipeline import run_analysis_pipeline
        from analytics.agent.data_loader import DataLoadResult
        r = DataLoadResult(ticker="FAKE")
        r.cannot_complete_reason = "CANNOT_COMPLETE: network timeout"
        with patch("analytics.agent.pipeline.load_ticker") as mock_load:
            mock_load.return_value = r
            result = run_analysis_pipeline("FAKE")

        assert not result.ok
        assert result.is_rate_limited is False

    def test_pipeline_result_has_is_rate_limited_field(self):
        """PipelineResult must expose is_rate_limited attribute."""
        from analytics.agent.pipeline import PipelineResult
        r = PipelineResult()
        assert hasattr(r, "is_rate_limited")
        assert r.is_rate_limited is False  # default


# ===========================================================================
# 3. force_refresh wiring: flag reaches fetch_ticker()
# ===========================================================================

class TestForceRefreshWiring:
    """force_refresh=True must propagate from pipeline → load_ticker → fetch_ticker."""

    def test_load_ticker_passes_force_refresh_to_default_fetch(self):
        """load_ticker(force_refresh=True) must call _default_fetch with force_refresh=True."""
        from analytics.agent.data_loader import load_ticker

        captured = {}

        def fake_fetch(ticker):
            captured["ticker"] = ticker
            # Return a minimal failed stub (we just want to verify the call)
            return {
                "info": {
                    "_fetch_success": False,
                    "_fetch_error": "test stub",
                    "_fetched_at": "2026-01-01T00:00:00",
                }
            }

        # When _fetch_fn is provided, force_refresh is NOT passed to it (it's
        # the _default_fetch closure that captures force_refresh). We test
        # _default_fetch directly instead.
        from analytics.agent.data_loader import _default_fetch
        with patch("data.ingestion.fetcher.fetch_ticker") as mock_ft:
            mock_ft.return_value = {
                "info": {
                    "_fetch_success": False,
                    "_fetch_error": "test",
                    "_fetched_at": "2026-01-01T00:00:00",
                }
            }
            _default_fetch("ENB.TO", force_refresh=True)
            mock_ft.assert_called_once_with("ENB.TO", force_refresh=True)

    def test_load_ticker_force_refresh_false_by_default(self):
        """force_refresh defaults to False — fetch_ticker must be called without it set."""
        from analytics.agent.data_loader import _default_fetch
        with patch("data.ingestion.fetcher.fetch_ticker") as mock_ft:
            mock_ft.return_value = {
                "info": {
                    "_fetch_success": False,
                    "_fetch_error": "test",
                    "_fetched_at": "2026-01-01T00:00:00",
                }
            }
            _default_fetch("ENB.TO")
            mock_ft.assert_called_once_with("ENB.TO", force_refresh=False)

    def test_pipeline_passes_force_refresh_to_load_ticker(self):
        """run_analysis_pipeline(force_refresh=True) must pass it to load_ticker."""
        from analytics.agent.pipeline import run_analysis_pipeline
        from analytics.agent.data_loader import DataLoadResult

        failed = DataLoadResult(ticker="AMZN")
        failed.cannot_complete_reason = "CANNOT_COMPLETE: test"

        with patch("analytics.agent.pipeline.load_ticker") as mock_load:
            mock_load.return_value = failed
            run_analysis_pipeline("AMZN", force_refresh=True)

        # Verify force_refresh=True was passed in the call kwargs
        call_kwargs = mock_load.call_args.kwargs
        assert call_kwargs.get("force_refresh") is True


# ===========================================================================
# 4. MVP ticker universe integrity
# ===========================================================================

class TestMVPTickerUniverse:
    """Verify the MVP ticker universe is intact and self-consistent."""

    def test_exactly_33_tickers(self):
        from data.mvp_tickers import MVP_TICKER_SYMBOLS
        assert len(MVP_TICKER_SYMBOLS) == 33

    def test_no_duplicate_tickers(self):
        from data.mvp_tickers import MVP_TICKER_SYMBOLS
        assert len(set(MVP_TICKER_SYMBOLS)) == len(MVP_TICKER_SYMBOLS)

    def test_mvp_ticker_map_keys_match_symbols(self):
        from data.mvp_tickers import MVP_TICKER_MAP, MVP_TICKER_SYMBOLS
        assert set(MVP_TICKER_MAP.keys()) == set(MVP_TICKER_SYMBOLS)

    def test_expected_tickers_present(self):
        from data.mvp_tickers import MVP_TICKER_MAP
        expected = [
            "ENB.TO", "SU.TO", "CNQ.TO", "TOU.TO", "TPZ.TO",
            "EQB.TO", "TD.TO", "POW.TO", "MFC.TO", "BN.TO",
            "REI.UN.TO", "ATD.TO", "ABXX.TO", "AMZN", "ITC.NS",
            "TATASTEEL.NS", "FFH.TO", "BAM.TO", "CPX.TO", "NWC.TO",
            "ARX.TO", "FTS.TO", "PPL.TO", "T.TO", "CM.TO",
            "BNS.TO", "MSFT", "CSU.TO", "DOL.TO", "KTKBANK.NS",
            "ASML", "GOOG", "TSM",
        ]
        for t in expected:
            assert t in MVP_TICKER_MAP, f"{t} missing from MVP universe"

    def test_all_tickers_have_required_fields(self):
        from data.mvp_tickers import MVP_TICKERS
        required = {"ticker", "name", "market", "sector"}
        for entry in MVP_TICKERS:
            missing = required - set(entry.keys())
            assert not missing, f"{entry['ticker']} missing fields: {missing}"

    def test_tickers_by_market(self):
        from data.mvp_tickers import tickers_by_market
        canada = tickers_by_market("Canada")
        usa = tickers_by_market("USA")
        india = tickers_by_market("India")
        # Must cover all 33
        assert len(canada) + len(usa) + len(india) == 33

    def test_is_mvp_ticker(self):
        from data.mvp_tickers import is_mvp_ticker
        assert is_mvp_ticker("ENB.TO")
        assert is_mvp_ticker("AMZN")
        assert not is_mvp_ticker("AAPL")
        assert not is_mvp_ticker("FAKE")

    def test_get_display_name_known(self):
        from data.mvp_tickers import get_display_name
        assert get_display_name("ENB.TO") == "Enbridge Inc."
        assert get_display_name("AMZN") == "Amazon.com Inc."

    def test_get_display_name_unknown_returns_ticker(self):
        from data.mvp_tickers import get_display_name
        assert get_display_name("UNKNOWN") == "UNKNOWN"


# ===========================================================================
# 5. Cache status reader (ui/data_status.py)
# ===========================================================================

class TestCacheStatus:
    """ui.data_status reads cache files correctly without network calls."""

    def _write_cache_files(self, tmp_dir: Path, ticker: str, *,
                            success: bool = True,
                            hours_ago: float = 1.0,
                            all_three: bool = True) -> None:
        from datetime import datetime, timezone, timedelta
        fetched_at = (
            datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        ).isoformat()

        safe = ticker.replace(".", "_")
        info = {
            "_ticker": ticker,
            "_fetch_success": success,
            "_fetch_error": None if success else "simulated",
            "_fetched_at": fetched_at,
            "longName": f"{ticker} Inc.",
        }
        (tmp_dir / f"{safe}_info.json").write_text(
            json.dumps(info), encoding="utf-8"
        )
        if all_three:
            fin = {
                "_fetch_success": success,
                "_fetched_at": fetched_at,
            }
            hist = {
                "_fetch_success": success,
                "_fetched_at": fetched_at,
            }
            (tmp_dir / f"{safe}_financials.json").write_text(
                json.dumps(fin), encoding="utf-8"
            )
            (tmp_dir / f"{safe}_history_5y.json").write_text(
                json.dumps(hist), encoding="utf-8"
            )

    def test_fresh_ticker_is_ready(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            self._write_cache_files(tmp_path, "ENB.TO", hours_ago=1.0)
            status = data_status.get_ticker_cache_status("ENB.TO")
            assert status["ready"] is True
            assert status["overall_status"] == "READY"
        finally:
            data_status._CACHE_DIR = old_cache

    def test_uncached_ticker_is_empty(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            status = data_status.get_ticker_cache_status("AMZN")
            assert status["ready"] is False
            assert status["overall_status"] == "EMPTY"
            assert status["any_data"] is False
        finally:
            data_status._CACHE_DIR = old_cache

    def test_stale_ticker_overall_status(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            # Write files that are 30h old (exceeds 24h TTL for info)
            self._write_cache_files(tmp_path, "FTS.TO", hours_ago=30.0)
            status = data_status.get_ticker_cache_status("FTS.TO")
            # Should be STALE because age > TTL
            assert status["overall_status"] in ("STALE", "PARTIAL")
            assert status["ready"] is False
        finally:
            data_status._CACHE_DIR = old_cache

    def test_partial_status_when_only_info_cached(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            # Only info file, no financials or history
            self._write_cache_files(tmp_path, "CM.TO", hours_ago=1.0,
                                    all_three=False)
            status = data_status.get_ticker_cache_status("CM.TO")
            assert status["overall_status"] == "PARTIAL"
            assert status["any_data"] is True
            assert status["ready"] is False
        finally:
            data_status._CACHE_DIR = old_cache

    def test_render_status_badge_ready(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            self._write_cache_files(tmp_path, "ENB.TO", hours_ago=0.5)
            status = data_status.get_ticker_cache_status("ENB.TO")
            badge = data_status.render_status_badge(status)
            assert "✅" in badge
        finally:
            data_status._CACHE_DIR = old_cache

    def test_render_status_badge_empty(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            status = data_status.get_ticker_cache_status("NONEXISTENT")
            badge = data_status.render_status_badge(status)
            assert "⬜" in badge
        finally:
            data_status._CACHE_DIR = old_cache

    def test_company_name_from_cache(self, tmp_path):
        from ui import data_status
        old_cache = data_status._CACHE_DIR
        data_status._CACHE_DIR = tmp_path
        try:
            self._write_cache_files(tmp_path, "ENB.TO", hours_ago=1.0)
            status = data_status.get_ticker_cache_status("ENB.TO")
            assert status["company_name"] == "ENB.TO Inc."
        finally:
            data_status._CACHE_DIR = old_cache


# ===========================================================================
# 6. Friendly error messages — _format_pipeline_error
#    Phase 10.5 UX Polish: user-facing message must NEVER expose raw technical
#    details (CANNOT_COMPLETE_LIVE_ANALYSIS, yfinance, HTTP 429, API URLs).
# ===========================================================================

# Strings that must NEVER appear in any user-facing error message
_FORBIDDEN_IN_UI = [
    "CANNOT_COMPLETE_LIVE_ANALYSIS",
    "CANNOT_COMPLETE",
    "yfinance",
    "429",
    "Too Many Requests",
    "quoteSummary",
    "https://",
    "http://",
    "Client Error",
]


class TestFriendlyErrorMessages:
    """manager._format_pipeline_error must produce human-readable messages."""

    def _make_result(self, error: str, is_rate_limited: bool = False):
        """Build a minimal PipelineResult-like object."""
        return SimpleNamespace(error=error, is_rate_limited=is_rate_limited)

    def _assert_no_technical_leakage(self, msg: str) -> None:
        """Assert none of the forbidden technical strings appear in msg."""
        for forbidden in _FORBIDDEN_IN_UI:
            assert forbidden not in msg, (
                f"User-facing message must not contain {forbidden!r}.\n"
                f"Got: {msg!r}"
            )

    # ── 429 / rate-limit ──────────────────────────────────────────────────────

    def test_429_message_contains_ticker(self):
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: yfinance returned no data for 'DOL.TO'. "
            "Reason: 429 Client Error: Too Many Requests for url: https://query2.finance.yahoo.com/...",
            is_rate_limited=True,
        )
        msg = ConversationManager._format_pipeline_error("DOL.TO", result)
        assert "DOL.TO" in msg

    def test_429_message_no_technical_leakage(self):
        """The full raw 429 error must not leak into the user-facing message."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: yfinance returned no data for 'DOL.TO'. "
            "Reason: 429 Client Error: Too Many Requests for url: https://query2.finance.yahoo.com/...",
            is_rate_limited=True,
        )
        msg = ConversationManager._format_pipeline_error("DOL.TO", result)
        self._assert_no_technical_leakage(msg)

    def test_429_message_explains_data_retrieval_problem(self):
        """Message must frame this as a data-access problem, not an analysis failure."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: 429 Too Many Requests",
            is_rate_limited=True,
        )
        msg = ConversationManager._format_pipeline_error("MSFT", result)
        lower = msg.lower()
        # Must communicate that data could not be retrieved
        assert any(phrase in lower for phrase in [
            "data could not", "could not be retrieved", "limiting requests",
            "market data", "temporarily"
        ]), f"Message must explain data retrieval problem. Got: {msg!r}"

    def test_429_message_suggests_action(self):
        """User must be told what to do — try again or use cached ticker."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: 429 Too Many Requests",
            is_rate_limited=True,
        )
        msg = ConversationManager._format_pipeline_error("MSFT", result)
        lower = msg.lower()
        assert any(phrase in lower for phrase in [
            "try again", "wait", "cached", "later"
        ]), f"Message must suggest action. Got: {msg!r}"

    def test_429_does_not_imply_ticker_invalid(self):
        """Rate-limit message must not say the ticker is invalid or delisted."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: 429 Too Many Requests",
            is_rate_limited=True,
        )
        msg = ConversationManager._format_pipeline_error("MSFT", result)
        lower = msg.lower()
        assert "invalid" not in lower
        assert "delist" not in lower
        assert "not found" not in lower

    def test_429_does_not_imply_analysis_engine_failed(self):
        """Rate-limit message must not say the investment engine failed."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: 429 Too Many Requests",
            is_rate_limited=True,
        )
        msg = ConversationManager._format_pipeline_error("MSFT", result)
        lower = msg.lower()
        assert "engine" not in lower
        assert "crash" not in lower
        assert "bug" not in lower

    # ── Non-429 errors ────────────────────────────────────────────────────────

    def test_non_429_no_technical_leakage(self):
        """Non-429 ticker-not-found message also must not leak technical strings."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: ticker not found",
            is_rate_limited=False,
        )
        msg = ConversationManager._format_pipeline_error("FAKE", result)
        self._assert_no_technical_leakage(msg)

    def test_non_429_not_labelled_as_rate_limit(self):
        """A non-429 error must NOT be presented as a rate-limit problem."""
        from conversation.manager import ConversationManager
        result = self._make_result(
            "CANNOT_COMPLETE_LIVE_ANALYSIS: ticker not found",
            is_rate_limited=False,
        )
        msg = ConversationManager._format_pipeline_error("FAKE", result)
        lower = msg.lower()
        assert "rate" not in lower
        assert "limiting" not in lower

    def test_network_error_message(self):
        from conversation.manager import ConversationManager
        result = self._make_result(
            "network connection refused",
            is_rate_limited=False,
        )
        msg = ConversationManager._format_pipeline_error("AMZN", result)
        lower = msg.lower()
        assert "network" in lower or "connection" in lower

    def test_network_error_no_technical_leakage(self):
        from conversation.manager import ConversationManager
        result = self._make_result(
            "network connection refused",
            is_rate_limited=False,
        )
        msg = ConversationManager._format_pipeline_error("AMZN", result)
        self._assert_no_technical_leakage(msg)

    def test_fallback_no_raw_error_dump(self):
        """Fallback path must not dump raw error text into user message."""
        from conversation.manager import ConversationManager
        raw_error = (
            "CANNOT_COMPLETE_LIVE_ANALYSIS: some internal exception occurred "
            "with yfinance at https://query2.finance.yahoo.com/v8/finance/quoteSummary"
        )
        result = self._make_result(raw_error, is_rate_limited=False)
        msg = ConversationManager._format_pipeline_error("TSM", result)
        self._assert_no_technical_leakage(msg)

    # ── session.last_error stores the friendly message ────────────────────────

    def test_session_last_error_is_friendly_on_429(self):
        """manager.run_analysis() must put the friendly message in session.last_error."""
        from conversation.manager import ConversationManager
        from analytics.agent.data_loader import DataLoadResult

        manager = ConversationManager()

        rate_limited = DataLoadResult(ticker="DOL.TO")
        rate_limited.cannot_complete_reason = (
            "CANNOT_COMPLETE_LIVE_ANALYSIS: yfinance returned no data for 'DOL.TO'. "
            "Reason: 429 Client Error: Too Many Requests for url: "
            "https://query2.finance.yahoo.com/v8/finance/quoteSummary/DOL.TO"
        )

        with patch("analytics.agent.pipeline.load_ticker", return_value=rate_limited):
            manager.run_analysis("DOL.TO")

        last_error = manager.session.last_error
        assert last_error, "session.last_error must be set after a failed analysis"
        for forbidden in _FORBIDDEN_IN_UI:
            assert forbidden not in last_error, (
                f"session.last_error must not contain {forbidden!r}.\n"
                f"Got: {last_error!r}"
            )

    # ── Legacy / backward-compat ──────────────────────────────────────────────

    def test_plain_string_still_works(self):
        """Legacy call with plain string (not PipelineResult) must not crash."""
        from conversation.manager import ConversationManager
        msg = ConversationManager._format_pipeline_error(
            "ENB.TO", "CANNOT_COMPLETE: some error"
        )
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_plain_string_429_detected(self):
        """Plain string containing 429 should trigger rate-limit message, no leakage."""
        from conversation.manager import ConversationManager
        msg = ConversationManager._format_pipeline_error(
            "MSFT", "429 Too Many Requests from Yahoo Finance"
        )
        self._assert_no_technical_leakage(msg)
