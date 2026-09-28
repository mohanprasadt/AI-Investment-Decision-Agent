# External Dependencies

> **Status:** Current as of Phase 10.6  
> **Source:** `requirements.txt`

---

## Runtime dependencies

| Package | Version constraint | Purpose | Required? |
|---------|-------------------|---------|-----------|
| `yfinance` | ≥ 0.2.0 | Financial data from Yahoo Finance | Required for all data |
| `anthropic` | ≥ 0.20.0 | Claude API for business research | Optional (degraded without) |
| `streamlit` | ≥ 1.32.0 | Web-based UI | Required for UI |
| `pyyaml` | ≥ 6.0 | Load configuration files | Required |
| `pytest` | ≥ 7.0.0 | Test runner | Dev only |

---

## yfinance

### What it is

`yfinance` is an open-source Python library that provides an interface to Yahoo Finance data. It is NOT an official Yahoo Finance product. Yahoo Finance does not publish a public API specification and does not guarantee data availability, accuracy, or continued access.

### Risk level: HIGH

yfinance is the primary data source for all financial analysis. If it stops working, the entire data layer fails.

### Key risks

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| HTTP 429 rate limiting | HIGH (regularly encountered) | Fail-fast + friendly error; pre-warm cache |
| Field name changes | MEDIUM (happened before) | Normalizer requires maintenance; see known-limitations |
| Data accuracy errors | MEDIUM | ITC.NS baseline provides a regression point |
| Yahoo Finance discontinues API access | LOW but catastrophic | No mitigation — would require new data source |
| yfinance package abandonment | LOW | Could pin to last working version |

### How the system handles yfinance failures

1. **HTTP 429 (rate limit):** `PipelineResult(ok=False, is_rate_limited=True)` → friendly UI message
2. **Other network errors:** `PipelineResult(ok=False)` → generic friendly error message
3. **Missing fields:** Logged in `data_quality_notes`; analysis proceeds with reduced confidence
4. **Empty response:** Not cached; analysis fails with clear error

### Installation

```bash
pip install yfinance>=0.2.0
```

### No SLA, no support contract

There is no service-level agreement with Yahoo Finance. Outages, rate limiting, and data errors are unilateral decisions by Yahoo. The product owner should be aware that the system's data reliability is fundamentally bounded by this dependency.

---

## anthropic (Claude API)

### What it is

The official Python client for the Anthropic API. Used for qualitative business research (Gate 1 / business research phase).

### Risk level: MEDIUM

Without the API key, the system degrades gracefully to `WAIT_INSUFFICIENT_EVIDENCE`. This is a correct and safe failure mode.

### Key risks

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| API key not set | Common (dev environments) | Graceful degradation to quantitative fallback |
| API unavailability | LOW | Session fails gracefully; no crash |
| API pricing changes | LOW | No automated action required |
| Model changes affect research quality | MEDIUM | No automated detection; PO review needed |

### Required configuration

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

The key must be set as an environment variable. It is NEVER accepted from the UI, never stored in session state, and never written to any file.

### Without the API key

- Steps 1–3 (data, normalise, quality) run normally
- Step 4 (business research) fails
- Gate 1 fails → `WAIT_INSUFFICIENT_EVIDENCE`
- No valuation, no decision, no conversation

This is the **correct safe failure mode** — not a bug.

---

## streamlit

### What it is

The Python library powering the web-based UI. It handles the browser server, session state, and component rendering.

### Risk level: LOW

Streamlit is well-maintained and widely used. Version changes occasionally require UI code updates.

### Key limitations

- **No persistent session state:** `st.session_state` is in-memory, per-tab. A browser refresh clears all state.
- **No multi-user session isolation:** Two browser tabs in the same Streamlit server share process memory (though `st.session_state` is tab-specific by default in recent versions).
- **No authentication:** Streamlit does not provide authentication. This product is single-user by design.

### Installation and startup

```bash
pip install streamlit>=1.32.0
streamlit run run_ui.py
```

---

## pyyaml

Used to load `config/thresholds.yaml` and `config/valuation_config.yaml`. Low risk — stable library with no expected changes.

---

## Development dependencies

### pytest

Used to run the test suite. Not needed in production.

```bash
pip install pytest>=7.0.0
pytest tests/ -v
```

---

## Python version requirement

**Python 3.10+** is required. The codebase uses:
- Dataclasses with `field(default_factory=...)`
- `from __future__ import annotations` for forward references
- f-strings
- `pathlib.Path`

Python 3.9 may work but is not tested. Python 3.8 and below will not work.

---

## No database dependency

The system uses only the local file system for persistence:
- `data/cache/` — JSON files for financial data
- `config/` — YAML configuration files
- `journal/`, `portfolio/` — template files (not integrated)

There is no SQLite, PostgreSQL, Redis, or any other database. This is a deliberate architectural decision to keep the deployment simple.
