@echo off
rem Build the portable UU ball exe (onedir). Run from this folder.
rem PyInstaller lives in _pylib (installed by _whl3.py, no site-packages write needed).
setlocal
set HERE=%~dp0
set PYTHONPATH=%HERE%_pylib
set TMP=%HERE%_tmp
set TEMP=%HERE%_tmp
if not exist "%TMP%" mkdir "%TMP%"

C:\Python315\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "UU加速球" ^
  --distpath "%HERE%dist" --workpath "%HERE%build" --specpath "%HERE%build" ^
  --add-data "%HERE%session.json;." ^
  --add-data "%HERE%uuctl.sh;." ^
  --add-data "%HERE%uu_route.sh;." ^
  --hidden-import uu ^
  --exclude-module paramiko --exclude-module cryptography --exclude-module bcrypt ^
  --exclude-module nacl --exclude-module PIL ^
  "%HERE%uuball.pyw"

echo.
echo dist\UU加速球\UU加速球.exe  <- copy this folder to the target PC
rem note: --onefile builds cannot be verified inside the DSH sandbox
rem (the onefile bootloader stalls while unpacking to TEMP), so we ship onedir.
endlocal
