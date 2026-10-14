@echo off
setlocal enabledelayedexpansion
title KaWuXing Android - push to GitHub
cd /d "%~dp0.."

echo ==================================================
echo   KaWuXing Android  -  push code to GitHub
echo ==================================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [X] git not found. Install "Git for Windows" first:
    echo     https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

rem ---- 1. local repository (already prepared) ----
if not exist ".git" (
    echo [*] no local repository yet, creating one ...
    git init -b main
    git add -A
    git commit -m "KaWuXing Android v1"
)
echo [i] Local repository is ready:
git --no-pager log --oneline
echo.

rem ---- 2. target repository ----
echo Your GitHub user name, press Enter to use [chengxiaofeng-prog]
set /p GHUSER=
if "%GHUSER%"=="" set GHUSER=chengxiaofeng-prog

echo Repository name, press Enter to use [kawuxing-android]
set /p GHREPO=
if "%GHREPO%"=="" set GHREPO=kawuxing-android

echo.
echo [i] Target: https://github.com/%GHUSER%/%GHREPO%.git
echo.
echo IMPORTANT: create this EMPTY repository on github.com FIRST:
echo    https://github.com/new
echo    name = %GHREPO%   ,  do NOT tick "Add a README file"
echo.
pause

git remote remove origin >nul 2>nul
git remote add origin https://github.com/%GHUSER%/%GHREPO%.git

rem ---- 3. proxy auto-detect (for accelerators like Watt Toolkit) ----
set PROXY_OK=0
for %%P in (26561 7890 10809 10808 1080 8889) do (
    if "!PROXY_OK!"=="0" (
        powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',%%P);$c.Close();exit 0}catch{exit 1}" >nul 2>nul
        if not errorlevel 1 (
            echo [i] found a local proxy on port %%P, telling git to use it ...
            git config --global http.proxy http://127.0.0.1:%%P
            git config --global https.proxy http://127.0.0.1:%%P
            set PROXY_OK=1
        )
    )
)
if "!PROXY_OK!"=="0" (
    echo [i] no local proxy detected, pushing directly.
    git config --global --unset http.proxy >nul 2>nul
    git config --global --unset https.proxy >nul 2>nul
)

rem ---- 4. push ----
echo.
echo [*] pushing ... a browser window may pop up to sign in to GitHub.
echo     That is Git Credential Manager: sign in once, it is remembered.
echo.
git push -u origin main

if errorlevel 1 (
    echo.
    echo [X] Push failed. Most likely one of these:
    echo.
    echo     1. github.com still unreachable from this network
    echo        - Try the browser first. If the browser works but git does not,
    echo          your accelerator (Watt Toolkit) only proxies the browser.
    echo          Check the proxy port inside the accelerator, then run:
    echo            git config --global http.proxy http://127.0.0.1:PORT
    echo          To undo later:
    echo            git config --global --unset http.proxy
    echo.
    echo     2. the empty repository does not exist on github.com yet
    echo        - Create it at https://github.com/new   name: %GHREPO%
    echo.
    echo     3. sign-in was cancelled, or wrong user name
    echo        - Check: https://github.com/%GHUSER%
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Code is on GitHub:
echo      https://github.com/%GHUSER%/%GHREPO%
echo.
echo      Next: open  https://github.com/%GHUSER%/%GHREPO%/actions
echo      First build takes 20-40 minutes, then download the APK
echo      from the "Artifacts" section of that run.
echo.
pause
