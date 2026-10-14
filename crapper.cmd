@echo off
rem Run the CRAP tool on Windows, creating a local virtualenv on first use.
rem The venv comes from py -3, or from python when the py launcher is missing.
rem A failed install removes the half-made venv, so the next run tries again.
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if exist "%PY%" goto run
where py >nul 2>nul
if errorlevel 1 goto python
py -3 -m venv "%ROOT%.venv"
goto made
:python
python -m venv "%ROOT%.venv"
:made
if errorlevel 1 goto failed
"%PY%" -m pip install -e "%ROOT%."
if errorlevel 1 goto failed
:run
"%PY%" -m crapper %*
exit /b %ERRORLEVEL%
:failed
set "CODE=%ERRORLEVEL%"
rmdir /s /q "%ROOT%.venv" 2>nul
exit /b %CODE%
