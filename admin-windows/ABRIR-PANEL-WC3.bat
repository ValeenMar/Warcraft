@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0abrir-panel-wc3.ps1"
if errorlevel 1 pause

