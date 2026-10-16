@echo off
rem Double-click launcher for Windows: runs start.ps1 even when PowerShell scripts are blocked.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
