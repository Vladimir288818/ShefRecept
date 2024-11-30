@echo off
taskkill /F /IM ngrok.exe
timeout /t 2
ngrok http 8000
pause