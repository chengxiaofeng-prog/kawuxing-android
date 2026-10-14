@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo ==================================================
echo   KaWuXing Android  -  push code to CNB (cnb.cool)
echo ==================================================
echo.

rem ---------------------------------------------------------------
rem 1. find a git. This machine has no standalone Git for Windows,
rem    but GitHub Desktop ships one - use it as a fallback.
rem ---------------------------------------------------------------
set GIT=
where git >nul 2>nul && set GIT=git

if "%GIT%"=="" (
    set CAND=%LOCALAPPDATA%\GitHubDesktop\app-3.6.7\resources\app\git\cmd\git.exe
    if exist "!CAND!" (
        set GIT="!CAND!"
        echo [i] using the git bundled with GitHub Desktop
    )
)

if "%GIT%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if exist "%%D\resources\app\git\cmd\git.exe" (
            set GIT="%%D\resources\app\git\cmd\git.exe"
            echo [i] using the git bundled with GitHub Desktop: %%D
        )
    )
)

if "%GIT%"=="" (
    echo [X] git not found.
    echo     Either install Git for Windows:  https://git-scm.com/download/win
    echo     or install GitHub Desktop:       https://desktop.github.com
    echo.
    pause
    exit /b 1
)

%GIT% --version
echo.

rem ---------------------------------------------------------------
rem 2. local repository (already prepared in this folder)
rem ---------------------------------------------------------------
if not exist ".git" (
    echo [*] no local repository yet, creating one ...
    %GIT% init -b main
    %GIT% add -A
    %GIT% commit -m "KaWuXing Android v1"
)
echo [i] local commits:
%GIT% --no-pager log --oneline
echo.

rem ---------------------------------------------------------------
rem 3. CNB repository info
rem ---------------------------------------------------------------
echo Open https://cnb.cool , sign in with WeChat, then:
echo    New repository  -^>  name it  kawuxing-android  -^>  keep it PRIVATE
echo.
echo Your CNB user name or group name, e.g. chengxiaofeng
set /p CNBUSER=
if "%CNBUSER%"=="" (
    echo [X] cannot be empty.
    pause
    exit /b 1
)
echo Repository name, press Enter to use [kawuxing-android]
set /p CNBREPO=
if "%CNBREPO%"=="" set CNBREPO=kawuxing-android

set CNBSLUG=%CNBUSER%/%CNBREPO%
echo.
echo [i] Target: https://cnb.cool/%CNBSLUG%.git
echo.
pause

%GIT% remote remove cnb >nul 2>nul
%GIT% remote add cnb https://cnb.cool/%CNBSLUG%.git

rem ---------------------------------------------------------------
rem 4. proxy auto-detect (only needed if you run an accelerator)
rem ---------------------------------------------------------------
set PROXY_OK=0
for %%P in (26561 7890 10809 10808 1080 8889) do (
    if "!PROXY_OK!"=="0" (
        powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',%%P);$c.Close();exit 0}catch{exit 1}" >nul 2>nul
        if not errorlevel 1 (
            echo [i] local proxy found on port %%P, telling git to use it ...
            %GIT% config --global http.proxy http://127.0.0.1:%%P
            %GIT% config --global https.proxy http://127.0.0.1:%%P
            set PROXY_OK=1
        )
    )
)
if "!PROXY_OK!"=="0" (
    echo [i] no local proxy detected, pushing directly.
    %GIT% config --global --unset http.proxy >nul 2>nul
    %GIT% config --global --unset https.proxy >nul 2>nul
)

rem ---------------------------------------------------------------
rem 5. push
rem ---------------------------------------------------------------
echo.
echo [*] pushing to CNB ... a browser window may pop up to sign in.
echo     Sign in with WeChat and authorize once; it is remembered.
echo.
%GIT% push -u cnb main

if errorlevel 1 (
    echo.
    echo [X] Push failed. Check these:
    echo.
    echo     1. the CNB repository does not exist yet
    echo        -^> create it at https://cnb.cool  (name: %CNBREPO%)
    echo     2. user/group name is wrong
    echo        -^> expect: https://cnb.cool/%CNBSLUG%
    echo     3. sign-in cancelled
    echo        -^> run this script again and finish the browser sign-in
    echo     4. old credentials cached from another account
    echo        -^> run:  %GIT% credential reject https://cnb.cool
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Code is on CNB:
echo      https://cnb.cool/%CNBSLUG%
echo.
echo      Next: open  https://cnb.cool/%CNBSLUG%/-/pipeline
echo      The build starts automatically. First run 20-40 min.
echo      Download the APK from the attachments section of that run.
echo.
pause
