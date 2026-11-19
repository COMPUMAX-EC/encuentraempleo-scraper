@echo off
rem Corrida diaria de las plataformas que no necesitan sesion: la lanza la tarea programada
rem "Encuentra Empleo - plataformas diaria" (20:30). Lee los JSON del sitio de Oportunidades y el buscador de
rem BecasChamba (plataformas.py todas) y alimenta la tabla observaciones de salida\ofertas.db.
rem Encuentra Empleo no entra aqui: necesita iniciar sesion a mano (semanal.ps1).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.>> salida\datos\log_diaria.txt
echo ===== %date% %time:~0,5% =====>> salida\datos\log_diaria.txt
".venv\Scripts\python.exe" -u plataformas.py todas >> salida\datos\log_diaria.txt 2>&1
