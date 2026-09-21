@echo off
setlocal
cd /d "%~dp0"
start "" pythonw RiddickLauncher.pyw
if errorlevel 1 start "" python RiddickLauncher.pyw
