@echo off
rem AodaFix - winmm.dll drop-in, 32 bit (Dark Athena is a 32-bit game).
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x86 >nul || exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
python tools\gen_proxy.py src || exit /b 1
python tools\check_escapes.py src | findstr /c:"bad escapes: 0" >nul || (python tools\check_escapes.py src & exit /b 1)
cl /nologo /O2 /MT /EHsc /W3 /std:c++17 /DUNICODE /D_UNICODE /D_CRT_SECURE_NO_WARNINGS /Fobuild\ /c src\*.cpp || exit /b 1
link /nologo /DLL /SAFESEH:NO /OUT:build\winmm.dll /DEF:src\winmm.def build\*.obj user32.lib kernel32.lib psapi.lib advapi32.lib gdi32.lib shell32.lib || exit /b 1
rem offline self-test host (tools\selftest.py); its object stays out of build\*.obj
if not exist build\host mkdir build\host
cl /nologo /O2 /MT /EHsc /W3 /DUNICODE /D_UNICODE /Fobuild\host\ /Febuild\selftest_host.exe tools\selftest_host.cpp || exit /b 1
echo BUILD OK
