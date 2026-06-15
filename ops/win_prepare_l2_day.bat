@echo off
setlocal

set PROJECT_ROOT=D:\market-live-terminal
set PYTHON_EXE=%L2_PYTHON_EXE%
if "%PYTHON_EXE%"=="" set PYTHON_EXE=C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe

pushd "%PROJECT_ROOT%"
"%PYTHON_EXE%" -u backend\scripts\l2_postclose_prepare_day.py %*
set ERR=%ERRORLEVEL%
popd
exit /b %ERR%
