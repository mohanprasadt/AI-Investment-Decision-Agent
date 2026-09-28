@echo off
echo Phase 10.x — Burst Hypothesis Confirmation (Suite 4)
echo =====================================================
echo.
echo BEFORE RUNNING:
echo   1. Close Streamlit if it is running
echo   2. Wait at least 3 minutes since any previous yfinance activity
echo      (Suite 3 must be at least 3 minutes in the past)
echo   3. Do NOT run any other yfinance calls while this is running
echo.
echo The script will:
echo   - Clear only FTS.TO and TATASTEEL.NS from data\cache\
echo   - Run Scenario A (back-to-back, 0s delay) in a subprocess
echo   - Wait 90 seconds
echo   - Run Scenario B (35s delay) in a subprocess
echo   - Save results to diagnostic_output_4.json
echo.
echo Estimated total run time: ~10 minutes
echo.
pause

cd /d "%~dp0"
python diagnostic_phase10x_4.py
pause
