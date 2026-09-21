@echo off
rem RiddickRumble.dll bauen - 32 Bit, weil das Spiel 32-bittig ist.
rem Ergebnis landet direkt neben DarkAthena.exe.

setlocal
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat
if not exist "%VCVARS%" (
    echo vcvars32.bat nicht gefunden: "%VCVARS%"
    exit /b 1
)
call "%VCVARS%" >nul
if errorlevel 1 exit /b 1

cd /d "%~dp0"
cl /nologo /O2 /W3 /D_CRT_SECURE_NO_WARNINGS /LD /MT RiddickRumble.c ^
   /link /DLL /DEF:RiddickRumble.def /OUT:RiddickRumble.dll ^
   kernel32.lib user32.lib
if errorlevel 1 exit /b 1

set ZIEL=D:\Games\The Chronicles of Riddick - Assault on Dark Athena\System\Win32_x86
if exist "%ZIEL%\DarkAthena.exe" (
    copy /y RiddickRumble.dll "%ZIEL%\RiddickRumble.dll" >nul
    echo installiert nach %ZIEL%
) else (
    echo Spielordner nicht gefunden - DLL nur gebaut
)

echo.
echo gebaut: %~dp0RiddickRumble.dll
endlocal
