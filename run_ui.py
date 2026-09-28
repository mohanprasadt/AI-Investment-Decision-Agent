"""
run_ui.py — Phase 10 Streamlit Entry Point
===========================================
Launch the AI Investment Decision Agent conversational UI.

Usage:
    streamlit run run_ui.py

Or with options:
    streamlit run run_ui.py -- --server.port 8502

Requirements:
    pip install streamlit anthropic yfinance

Environment:
    ANTHROPIC_API_KEY  — required for qualitative research (Phase 4 / Gate 1).
                         Without it, the pipeline uses the quantitative fallback
                         and Gate 1 produces WAIT_INSUFFICIENT_EVIDENCE.
                         Set in your .env file or shell — never paste into the UI.

Architecture:
    run_ui.py → ui/app.py → conversation/manager.py → analytics/ (unchanged)

Portfolio privacy:
    The UI accepts portfolio weight (%) only.
    Shares, average cost, and account value are never requested or stored.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path before Streamlit imports ui.app
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if python-dotenv is available (optional convenience)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — use shell environment variables

# Import and run the app
from ui.app import main

if __name__ == "__main__":
    main()
