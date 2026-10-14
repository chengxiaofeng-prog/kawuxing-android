@echo off
REM ============================================================
REM  Fix GitHub access on Windows (China network / SNI issue)
REM  Usage: right-click this file -> "Run as administrator"
REM  It adds GitHub IP mappings to the hosts file and flushes DNS.
REM  To undo: open C:\Windows\System32\drivers\etc\hosts and delete
REM  the lines between "# >>> kawuxing github fix" and
REM  "# <<< kawuxing github fix".
REM ============================================================
setlocal
set HOSTS=%WINDIR%\System32\drivers\etc\hosts
set MARK1=# >>> kawuxing github fix
set MARK2=# <<< kawuxing github fix

net session >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Please right-click this file and choose "Run as administrator".
  pause
  exit /b 1
)

echo Backing up hosts to hosts.kawuxing.bak ...
copy /Y "%HOSTS%" "%HOSTS%.kawuxing.bak" >nul

echo Removing previous kawuxing block (if any) ...
findstr /V /C:"%MARK1%" /C:"%MARK2%" "%HOSTS%" > "%TEMP%\hosts_tmp.txt"
findstr /V /C:"github.com" /C:"githubusercontent.com" /C:"githubassets.com" /C:"github.io" "%TEMP%\hosts_tmp.txt" > "%TEMP%\hosts_tmp2.txt"
copy /Y "%TEMP%\hosts_tmp2.txt" "%HOSTS%" >nul

echo Adding GitHub IP mappings ...
echo. >> "%HOSTS%"
(
  echo %MARK1%
  echo # github.com core
  echo 20.205.243.166 github.com
  echo 20.205.243.168 api.github.com
  echo 20.205.243.161 codeload.github.com
  echo # static / raw
  echo 185.199.108.133 raw.githubusercontent.com
  echo 185.199.108.133 objects.githubusercontent.com
  echo 185.199.108.133 avatars.githubusercontent.com
  echo 185.199.108.154 github.githubassets.com
  echo 185.199.108.153 github.io
  echo %MARK2%
) >> "%HOSTS%"

echo Flushing DNS cache ...
ipconfig /flushdns >nul

echo.
echo Done. Now try opening https://github.com in your browser.
echo If it still fails, the TCP port 443 is being blocked by the
echo network (not a DNS problem) - use an accelerator tool or a
echo domestic build platform instead.
echo.
pause
