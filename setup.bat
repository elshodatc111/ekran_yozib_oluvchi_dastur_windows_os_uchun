@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Ekran Yozuvchi: ornatish - birinchi marta ===

where py >nul 2>nul
if errorlevel 1 goto nopython

rem Oldingi muvaffaqiyatsiz urinishdan qolgan muhitni ochirish
if exist ".venv\ok.flag" goto havevenv
if exist ".venv" rmdir /s /q .venv

set PYVER=
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 set PYVER=3.12
if defined PYVER goto mkvenv
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 set PYVER=3.11
if defined PYVER goto mkvenv
py -3.13 -c "import sys" >nul 2>nul
if not errorlevel 1 set PYVER=3.13
if defined PYVER goto mkvenv
goto wrongpython

:mkvenv
echo Python %PYVER% ishlatiladi. Virtual muhit yaratilmoqda...
py -%PYVER% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto novenv

:havevenv
echo Kutubxonalar ornatilmoqda, kuting...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto piperr
echo ok> ".venv\ok.flag"

if exist "ffmpeg\ffmpeg.exe" goto done
echo FFmpeg yuklab olinmoqda...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0get_ffmpeg.ps1"
if not exist "ffmpeg\ffmpeg.exe" goto ffmpegerr

:done
echo.
echo Tayyor! Endi run.bat ni ishga tushiring.
pause
exit /b 0

:nopython
echo Python topilmadi. python.org dan Python 3.12 64-bit ornating va Add python.exe to PATH belgisini qoying.
pause
exit /b 1

:wrongpython
echo Mos Python topilmadi. Sizda boshqa versiya bor ^(masalan 3.14^), kutubxonalar uni qollamaydi.
echo python.org/downloads/release/python-3129/ dan Python 3.12 64-bit ornating, keyin setup.bat ni qayta ishga tushiring.
pause
exit /b 1

:novenv
echo Virtual muhit yaratilmadi. Python ornatilganini tekshiring.
pause
exit /b 1

:piperr
echo Kutubxonalarni ornatishda xato boldi. Yuqoridagi xabarni yuboring.
pause
exit /b 1

:ffmpegerr
echo FFmpeg yuklanmadi. get_ffmpeg.ps1 ni qolda ishga tushiring yoki ffmpeg.exe ni ffmpeg papkasiga qoying.
pause
exit /b 1
