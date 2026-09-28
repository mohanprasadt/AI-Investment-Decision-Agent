@echo off
cd /d "C:\Users\itsmo\OneDrive\Desktop\Projects\AI-Investment-Decision-Agent"
echo Running Phase 10.x Follow-up Diagnostic...
echo.
echo This script will:
echo   - Inspect cache state (immediate)
echo   - Test each yfinance endpoint for each ticker (with delays)
echo   - Test the full application fetch path (with delays)
echo.
echo Estimated total time: 5-10 minutes (due to deliberate delays between requests)
echo.
python diagnostic_phase10x_2.py
echo.
echo Done. Output written to diagnostic_output_2.json
pause
