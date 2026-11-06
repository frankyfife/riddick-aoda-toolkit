// Offline self test (tools/selftest.py): maps the game modules without running
// them (DONT_RESOLVE_DLL_REFERENCES), applies the patches and dumps the images,
// so the result can be compared with what the Python toolkit writes to disk.
// Also runs the data generators into <out>\cache.
#include "common.h"

extern uint8_t* g_lastCave;
extern size_t g_lastCaveSize;

static void Dump(const std::wstring& p, const void* data, size_t n)
{
    std::vector<uint8_t> v((const uint8_t*)data, (const uint8_t*)data + n);
    HANDLE h = CreateFileW(p.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD wr; WriteFile(h, v.data(), (DWORD)v.size(), &wr, nullptr); CloseHandle(h);
}

#pragma comment(linker, "/EXPORT:AodaFix_SelfTest=_AodaFix_SelfTest@12")
extern "C" int __stdcall AodaFix_SelfTest(const wchar_t* gameRoot, const wchar_t* outDir, int rumble)
{
    wcscpy_s(g_gameRoot, gameRoot);
    swprintf_s(g_cacheDir, L"%s\\cache", outDir);
    CreateDirectoryW(outDir, nullptr);
    CreateDirectoryW(g_cacheDir, nullptr);
    ConfigLoad();
    g_cfg.rumble = rumble;
    // parity with the Python toolkit: no hint resizing (an AodaFix.ini next to the
    // DLL with HintSize set overrides this, to test the extra hook)
    wchar_t ini[MAX_PATH]; swprintf_s(ini, L"%s\\AodaFix.ini", g_dllDir);
    if ((int)GetPrivateProfileIntW(L"Prompts", L"HintSize", -1, ini) < 0) g_cfg.hintSize = 0;
    DataGen_Run();
    FontGen_Run();

    static const wchar_t* const kMods[][2] = {
        { L"System\\Win32_x86\\MSystem.dll", L"MSystem.dll" },
        { L"System\\Win32_x86\\RndrGL.dll", L"RndrGL.dll" },
        { L"Content\\GameClasses_Win32_x86.dll", L"GameClasses_Win32_x86.dll" },
        { L"Content\\GameWorld_Win32_x86.dll", L"GameWorld_Win32_x86.dll" },
    };
    FILE* meta = nullptr;
    _wfopen_s(&meta, (std::wstring(outDir) + L"\\meta.txt").c_str(), L"w");
    for (auto& m : kMods) {
        std::wstring path = std::wstring(gameRoot) + L"\\" + m[0];
        HMODULE h = LoadLibraryExW(path.c_str(), nullptr, DONT_RESOLVE_DLL_REFERENCES);
        if (!h) { Log("selftest: cannot map %ls (%lu)", path.c_str(), GetLastError()); continue; }
        uint32_t size = ImageSize(h);
        std::wstring base = std::wstring(outDir) + L"\\" + m[1];
        Dump(base + L".orig.bin", h, size);
        char name[64]; WideCharToMultiByte(CP_ACP, 0, m[1], -1, name, 64, nullptr, nullptr);
        g_lastCave = nullptr; g_lastCaveSize = 0;
        OnModuleLoaded(h, name);
        Dump(base + L".patched.bin", h, size);
        if (g_lastCave) Dump(base + L".cave.bin", g_lastCave, g_lastCaveSize);
        if (meta) fprintf(meta, "%s base=0x%08X size=0x%X cave=0x%08X cavesize=%u rumble_play=0x%08X\n", name,
                          (unsigned)(uintptr_t)h, size, (unsigned)(uintptr_t)g_lastCave, (unsigned)g_lastCaveSize,
                          (unsigned)(uintptr_t)&Rumble_Play);
        FreeLibrary(h);
    }
    if (meta) fclose(meta);
    return 0;
}
