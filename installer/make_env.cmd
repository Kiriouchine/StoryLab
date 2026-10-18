@echo off
rem Story Lab - builds Story Lab's own Python inside its folder (run by the installer).
rem   make_env.cmd venv       Python 3.11 + an empty environment in .venv
rem   make_env.cmd torch      PyTorch, CPU build (the voices run on the processor)
rem   make_env.cmd packages   everything else, pinned (requirements.txt)
rem Exit code 0 = done. The output goes to setup\make_env.log.
setlocal
for %%I in ("%~dp0..") do set "APP=%%~fI"
set "UV=%APP%\tools\uv.exe"
set "UV_PYTHON_INSTALL_DIR=%APP%\python"
set "UV_CACHE_DIR=%APP%\.cache\uv"
rem the Windows certificate store: some antivirus programs inspect HTTPS, and
rem uv's own certificate list would refuse them
set "UV_SYSTEM_CERTS=true"
set "UV_LINK_MODE=copy"
set "UV_PYTHON_PREFERENCE=only-managed"
set "PY=%APP%\.venv\Scripts\python.exe"
set "LOG=%APP%\setup\make_env.log"

echo ==== %date% %time% %1 >> "%LOG%"
rem v12.4: the junction uv makes for "Python 3.11" (python\cpython-3.11-...)
rem is refused by Windows when this script runs under Setup (error 448,
rem "untrusted mount point" - Inno Setup's protection against junction
rem tricks reaches the programs it starts), and uv looks at it whenever it
rem meets this Python. Without it uv uses the real folder. Removing a junction
rem removes only the link, never the Python it points to.
for /d %%J in ("%APP%\python\cpython-3.11-windows-x86_64-none") do rmdir "%%~fJ" >> "%LOG%" 2>&1
if /I "%1"=="venv" goto venv
if /I "%1"=="torch" goto torch
if /I "%1"=="packages" goto packages
exit /b 2

:venv
rem v12.4: uv downloads Python 3.11 into python\, and Python's OWN venv module
rem makes .venv from the real interpreter. uv's venv was dropped: its
rem python.exe is a trampoline with the path of uv's "Python 3.11" JUNCTION
rem (python\cpython-3.11-...) built in, and Windows refuses that junction when
rem this script runs under Setup (error 448, "untrusted mount point" - Inno
rem Setup's protection against junction tricks reaches the programs it
rem starts). The 12.4 test installs failed exactly so at the torch step.
"%UV%" python install 3.11 >> "%LOG%" 2>&1
rem (it may report that it could not make the junction - the interpreter is
rem unpacked all the same)
set "PYEXE="
for /d %%D in ("%APP%\python\cpython-3.11.*-windows-x86_64-none") do set "PYEXE=%%~fD\python.exe"
if not defined PYEXE exit /b 11
for /d %%J in ("%APP%\python\cpython-3.11-windows-x86_64-none") do rmdir "%%~fJ" >> "%LOG%" 2>&1
"%PYEXE%" -m venv --without-pip "%APP%\.venv" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 11
"%PY%" -c "import sys; print('venv python', sys.version.split()[0], sys.base_prefix)" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 11
exit /b 0

:torch
"%UV%" pip install --python "%PY%" "torch==2.12.1" --index-url https://download.pytorch.org/whl/cpu >> "%LOG%" 2>&1
if errorlevel 1 exit /b 12
exit /b 0

:packages
"%UV%" pip install --python "%PY%" -r "%APP%\requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 13
"%PY%" -c "import customtkinter, kokoro, misaki, spacy, en_core_web_sm, ollama, httpx, sounddevice, truststore" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 14
rem the download cache (about 0.9 GB) is not needed once everything is in
"%UV%" cache clean >> "%LOG%" 2>&1
exit /b 0
