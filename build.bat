@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Ekran Yozuvchi: EkranYozuvchi_Setup.exe yigish ===
if not exist ".venv\Scripts\python.exe" goto nosetup
if not exist "ffmpeg\ffmpeg.exe" goto noffmpeg

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not defined ISCC goto noinno

".venv\Scripts\python.exe" -m pip install pyinstaller
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
".venv\Scripts\python.exe" make_icon.py
if not exist "assets\icon.ico" goto noicon

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --noconsole --onedir --name EkranYozuvchi --icon assets\icon.ico --collect-all dxcam --collect-all pyaudiowpatch --collect-all sounddevice --collect-all mss --hidden-import comtypes main.py
if errorlevel 1 goto pyierr
xcopy /E /I /Y "ffmpeg" "dist\EkranYozuvchi\ffmpeg" >nul

"%ISCC%" installer.iss
if errorlevel 1 goto isserr
echo.
echo TAYYOR: installer_out\EkranYozuvchi_Setup.exe
pause
exit /b 0

:nosetup
echo Avval setup.bat ni ishga tushiring.
pause
exit /b 1

:noffmpeg
echo ffmpeg\ffmpeg.exe topilmadi. Avval setup.bat yoki get_ffmpeg.ps1 ni ishga tushiring.
pause
exit /b 1

:noinno
echo Inno Setup topilmadi. PowerShell da: winget install JRSoftware.InnoSetup
echo Ornatgach build.bat ni qayta ishga tushiring.
pause
exit /b 1

:noicon
echo Ikonka yaratilmadi.
pause
exit /b 1

:pyierr
echo PyInstaller xato bilan tugadi. Yuqoridagi xabarni yuboring.
pause
exit /b 1

:isserr
echo Inno Setup xato bilan tugadi. Yuqoridagi xabarni yuboring.
pause
exit /b 1
