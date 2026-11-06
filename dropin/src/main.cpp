// Entry point: winmm.dll proxy + game module tracking
#include "common.h"
#include "proxy_names.h"
#include <psapi.h>
#include <string.h>

extern "C" void* g_proxy_table[PROXY_COUNT] = {};
wchar_t g_dllDir[MAX_PATH];
wchar_t g_gameRoot[MAX_PATH];
wchar_t g_cacheDir[MAX_PATH];
static HMODULE g_self, g_realWinmm;

static void ProxyInit()
{
    wchar_t sys[MAX_PATH];
    GetSystemDirectoryW(sys, MAX_PATH);          // SysWOW64 for a 32-bit process
    wcscat_s(sys, L"\\winmm.dll");
    g_realWinmm = LoadLibraryW(sys);
    for (int i = 0; i < PROXY_COUNT; ++i)
        g_proxy_table[i] = g_realWinmm ? (void*)GetProcAddress(g_realWinmm, g_proxy_names[i]) : nullptr;
}

// ---------------------------------------------------------------------------------
// Every module below the game folder gets its LoadLibrary imports redirected, so
// RndrGL / GameClasses / GameWorld are patched the moment they are mapped.
static HMODULE g_seen[64];
static int g_seenCount;
static CRITICAL_SECTION g_modCs;

static HMODULE WINAPI Hook_LoadLibraryA(LPCSTR name);
static HMODULE WINAPI Hook_LoadLibraryExA(LPCSTR name, HANDLE f, DWORD flags);

static bool IsGameModule(HMODULE m, char* outName, size_t n)
{
    wchar_t path[MAX_PATH];
    if (m == g_self || !GetModuleFileNameW(m, path, MAX_PATH)) return false;
    if (_wcsnicmp(path, g_gameRoot, wcslen(g_gameRoot)) != 0) return false;
    const wchar_t* fn = wcsrchr(path, L'\\');
    WideCharToMultiByte(CP_ACP, 0, fn ? fn + 1 : path, -1, outName, (int)n, nullptr, nullptr);
    return true;
}

static void SafeRun(void (*fn)(), const char* what)
{
    __try { fn(); }
    __except (EXCEPTION_EXECUTE_HANDLER) { Log("WARNING: exception 0x%08lX in %s - skipped", GetExceptionCode(), what); }
}

// A fault while patching one module must never take the process down (inside
// DllMain it would end as 0xC0000142); the module is then simply left as it is.
static void SafePatchModule(HMODULE m, const char* name)
{
    __try {
        PatchIAT(m, "kernel32.dll", "LoadLibraryA", (void*)Hook_LoadLibraryA);
        PatchIAT(m, "kernel32.dll", "LoadLibraryExA", (void*)Hook_LoadLibraryExA);
        OnModuleLoaded(m, name);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        Log("WARNING: exception 0x%08lX while patching %s - module skipped", GetExceptionCode(), name);
    }
}

static void ScanModules()
{
    EnterCriticalSection(&g_modCs);
    HMODULE mods[512]; DWORD needed = 0;
    if (EnumProcessModules(GetCurrentProcess(), mods, sizeof(mods), &needed)) {
        int count = (int)(needed / sizeof(HMODULE));
        for (int i = 0; i < count && i < 512; ++i) {
            bool known = false;
            for (int k = 0; k < g_seenCount; ++k) if (g_seen[k] == mods[i]) { known = true; break; }
            if (known) continue;
            char name[MAX_PATH];
            if (!IsGameModule(mods[i], name, sizeof(name))) continue;
            if (g_seenCount < 64) g_seen[g_seenCount++] = mods[i];
            Log("module %s at %p", name, mods[i]);
            SafePatchModule(mods[i], name);
        }
    }
    LeaveCriticalSection(&g_modCs);
}

static HMODULE WINAPI Hook_LoadLibraryA(LPCSTR name)
{
    HMODULE m = LoadLibraryA(name);
    if (m) ScanModules();
    return m;
}
static HMODULE WINAPI Hook_LoadLibraryExA(LPCSTR name, HANDLE f, DWORD flags)
{
    HMODULE m = LoadLibraryExA(name, f, flags);
    if (m) ScanModules();
    return m;
}

void OnModuleLoaded(HMODULE mod, const char* name)
{
    Files_PatchModule(mod);
    if (!_stricmp(name, "MSystem.dll")) MSystem_Patch(mod);
    else if (!_stricmp(name, "RndrGL.dll")) RndrGL_Patch(mod);
    else if (!_strnicmp(name, "GameClasses", 11) || !_strnicmp(name, "GameWorld", 9)) {
        Glyphs_Patch(mod, name);
        if (g_cfg.textLog) TextLog_Patch(mod, name);
    }
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        g_self = h;
        DisableThreadLibraryCalls(h);
        InitializeCriticalSection(&g_modCs);
        ProxyInit();
        GetModuleFileNameW(h, g_dllDir, MAX_PATH);
        if (wchar_t* p = wcsrchr(g_dllDir, L'\\')) *p = 0;
        // game root = two levels above System\Win32_x86
        wcscpy_s(g_gameRoot, g_dllDir);
        for (int i = 0; i < 2; ++i) if (wchar_t* p = wcsrchr(g_gameRoot, L'\\')) *p = 0;
        swprintf_s(g_cacheDir, L"%s\\AodaFix_cache", g_dllDir);
        CreateDirectoryW(g_cacheDir, nullptr);
        LogInit(g_dllDir);
        if (GetEnvironmentVariableW(L"AODAFIX_SELFTEST", nullptr, 0)) { Log("self-test mode"); return TRUE; }
        Log("AodaFix loaded, game root %ls", g_gameRoot);
        ConfigLoad();
        SafeRun(EnvCfg_Prepare, "envcfg");
        SafeRun(DataGen_Run, "datagen");
        SafeRun(FontGen_Run, "fontgen");
        Rumble_Init();
        ScanModules();
    } else if (reason == DLL_PROCESS_DETACH) {
        Rumble_Shutdown();
        Display_Shutdown();
    }
    return TRUE;
}
