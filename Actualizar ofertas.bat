@echo off
rem Abre el panel de ofertas en el navegador. Cierra esta ventana para apagarlo.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" panel.py
) else (
  python panel.py
)
pause
