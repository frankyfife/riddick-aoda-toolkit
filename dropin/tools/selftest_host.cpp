// 32-bit host for the offline self test: selftest_host.exe <winmm.dll> <game root> <out dir> <rumble 0|1>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int wmain(int argc, wchar_t** argv)
{
    if (argc < 5) { fwprintf(stderr, L"usage: selftest_host <winmm.dll> <game root> <out dir> <rumble>\n"); return 2; }
    SetEnvironmentVariableW(L"AODAFIX_SELFTEST", L"1");
    HMODULE h = LoadLibraryW(argv[1]);
    if (!h) { fwprintf(stderr, L"cannot load %s (%lu)\n", argv[1], GetLastError()); return 1; }
    typedef int(__stdcall* Fn)(const wchar_t*, const wchar_t*, int);
    Fn f = (Fn)GetProcAddress(h, "AodaFix_SelfTest");
    if (!f) { fwprintf(stderr, L"no AodaFix_SelfTest export\n"); return 1; }
    return f(argv[2], argv[3], _wtoi(argv[4]));
}
