@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 server.py & goto :eof)
where python >nul 2>nul && (python server.py & goto :eof)
echo Python tidak ditemukan. Instal dari https://www.python.org lalu coba lagi.
pause
