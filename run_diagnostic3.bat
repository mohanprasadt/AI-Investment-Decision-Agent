@echo off
echo Phase 10.x Cold-Cache 429 Diagnostic Suite 3
echo =============================================
echo.
echo BEFORE RUNNING:
echo   1. Delete entire data\cache\ folder
echo   2. Wait 5+ minutes with NO yfinance activity
echo   3. Close Streamlit if it is running
echo.
echo Estimated run time: ~12 minutes (tickers tested with delays)
echo.
pause

cd /d "%~dp0"
python diagnostic_phase10x_3.py
pause
