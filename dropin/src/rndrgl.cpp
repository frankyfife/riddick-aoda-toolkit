// RndrGL.dll: borderless full-monitor window, 4K in the mode list, full viewport,
// HDR-safe gamma ramp (see ../patches/borderless.py for the background).
#include "common.h"
#include <string.h>

static bool Replace(HMODULE m, const char* what, const char* oldHex, const char* newHex)
{
    std::vector<uint8_t> nb;
    for (const char* p = newHex; *p;) {
        while (*p == ' ') ++p;
        if (!*p) break;
        char b[3] = { p[0], p[1], 0 }; nb.push_back((uint8_t)strtoul(b, nullptr, 16)); p += 2;
    }
    auto hits = FindAllHex(m, oldHex);
    if (hits.size() != 1) {
        Log("rndrgl: WARNING %s: %u matches - left alone", what, (unsigned)hits.size());
        return false;
    }
    WriteMem(hits[0], nb.data(), nb.size());
    Log("rndrgl: %s", what);
    return true;
}

// ---- Windows HDR -------------------------------------------------------------------
// Under Windows HDR a legacy gamma ramp disturbs the desktop's colour pipeline,
// and a ramp left behind keeps the desktop washed out after the game is closed.
static bool IsHdrActive()
{
    UINT32 np = 0, nm = 0;
    if (GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, &np, &nm) != ERROR_SUCCESS) return false;
    std::vector<DISPLAYCONFIG_PATH_INFO> paths(np);
    std::vector<DISPLAYCONFIG_MODE_INFO> modes(nm);
    if (QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, &np, paths.data(), &nm, modes.data(), nullptr) != ERROR_SUCCESS) return false;
    for (UINT32 i = 0; i < np; ++i) {
        DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO ci = {};
        ci.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO;
        ci.header.size = sizeof(ci);
        ci.header.adapterId = paths[i].targetInfo.adapterId;
        ci.header.id = paths[i].targetInfo.id;
        if (DisplayConfigGetDeviceInfo(&ci.header) == ERROR_SUCCESS && ci.advancedColorEnabled) return true;
    }
    return false;
}

static bool g_hdr;
static WORD g_origRamp[3][256];
static bool g_haveOrigRamp, g_rampChanged;

static void CaptureRamp()
{
    if (g_haveOrigRamp) return;
    if (HDC dc = GetDC(nullptr)) {
        g_haveOrigRamp = GetDeviceGammaRamp(dc, g_origRamp) != FALSE;
        ReleaseDC(nullptr, dc);
    }
    if (!g_haveOrigRamp)
        for (int c = 0; c < 3; ++c) for (int i = 0; i < 256; ++i) g_origRamp[c][i] = (WORD)(i * 257);
    g_haveOrigRamp = true;
}

static BOOL WINAPI Hook_SetDeviceGammaRamp(HDC dc, LPVOID ramp)
{
    bool allow = g_cfg.gammaRamp == 1 || (g_cfg.gammaRamp == -1 && !g_hdr);
    static int logged;
    if (logged++ < 3) Log("rndrgl: game gamma ramp %s", allow ? "applied" : "ignored");
    if (!allow) return TRUE;
    CaptureRamp();
    g_rampChanged = true;
    return SetDeviceGammaRamp(dc, ramp);
}

void Display_Shutdown()
{
    if (g_rampChanged) {
        if (HDC dc = GetDC(nullptr)) { SetDeviceGammaRamp(dc, g_origRamp); ReleaseDC(nullptr, dc); }
        g_rampChanged = false;
        Log("rndrgl: gamma ramp restored");
    }
}

// ---- display scaling (DPI) ---------------------------------------------------------
// The game declares no DPI awareness, so above 100 % display scaling Windows
// virtualises its window: user32 then reports logical pixels to the engine while the
// display mode it renders at stays physical. Window and back buffer no longer match,
// and the picture reaches past the screen edges, so only part of it is visible.
// Declaring the process DPI aware before it has ever seen a window makes every metric
// physical again. [Display] DpiAware, and it has to happen in DllMain: winmm.dll is a
// static import of DarkAthena.exe, so this runs before the game's entry point.
static UINT SystemDpi()
{
    typedef UINT(WINAPI * GetDpiForSystem_t)(void);
    if (HMODULE u = GetModuleHandleW(L"user32.dll"))
        if (GetDpiForSystem_t f = (GetDpiForSystem_t)GetProcAddress(u, "GetDpiForSystem"))
            return f();
    if (HDC dc = GetDC(nullptr)) {
        UINT d = (UINT)GetDeviceCaps(dc, LOGPIXELSX);
        ReleaseDC(nullptr, dc);
        return d ? d : 96;
    }
    return 96;
}

// Display mode against window metrics: if the two disagree, scaling is in play.
static void LogDisplayMetrics()
{
    DEVMODEW dm = {};
    dm.dmSize = sizeof(dm);
    UINT dpi = SystemDpi();
    int mw = GetSystemMetrics(SM_CXSCREEN), mh = GetSystemMetrics(SM_CYSCREEN);
    if (EnumDisplaySettingsW(nullptr, ENUM_CURRENT_SETTINGS, &dm))
        // An unaware process is told 96 dpi whatever the setting is, but its window
        // metrics still come back scaled down, so the mismatch is what gives it away.
        Log("display: mode %lux%lu @ %lu Hz, metrics %dx%d, %u dpi (%u %%)%s",
            dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency, mw, mh, dpi, dpi * 100 / 96,
            (int)dm.dmPelsWidth != mw ? "  <-- window metrics are virtualised" : "");
    else
        Log("display: metrics %dx%d, %u dpi (%u %%)", mw, mh, dpi, dpi * 100 / 96);
}

// Called from DllMain, so it stays to user32 calls that load nothing: anything that
// may pull in a display driver belongs outside the loader lock (LogDisplayMetrics
// runs later, from RndrGL_Patch).
void Display_DpiAware()
{
    if (!g_cfg.dpiAware) {
        Log("display: DPI awareness left alone (DpiAware=0)");
        return;
    }

    HMODULE u = GetModuleHandleW(L"user32.dll");
    typedef HANDLE(WINAPI * GetThreadCtx_t)(void);
    typedef int(WINAPI * GetAwareness_t)(HANDLE);
    typedef BOOL(WINAPI * SetCtx_t)(HANDLE);
    GetThreadCtx_t getCtx = u ? (GetThreadCtx_t)GetProcAddress(u, "GetThreadDpiAwarenessContext") : nullptr;
    GetAwareness_t getAw = u ? (GetAwareness_t)GetProcAddress(u, "GetAwarenessFromDpiAwarenessContext") : nullptr;
    SetCtx_t setCtx = u ? (SetCtx_t)GetProcAddress(u, "SetProcessDpiAwarenessContext") : nullptr;

    // 0 unaware, 1 system aware, 2 per monitor aware, -1 = cannot tell (before Win10 1607).
    // Already aware means an application manifest or the HIGHDPIAWARE compatibility flag on
    // the exe got there first; setting it again would only fail, so leave it be.
    int aw = (getCtx && getAw) ? getAw(getCtx()) : -1;
    if (aw > 0) {
        Log("display: already DPI aware (%s, from a manifest or the compatibility flag)",
            aw == 2 ? "per monitor" : "system");
        return;
    }

    if (setCtx && setCtx((HANDLE)-4))          // DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        Log("display: DPI aware (per monitor)");
    else if (SetProcessDPIAware())
        Log("display: DPI aware (system)");
    else
        Log("display: WARNING DPI awareness not set (error %lu); above 100 %% display "
            "scaling the picture can reach past the screen edges", GetLastError());
}

// The window the engine really gets, for reports of a cut off or shifted picture.
static HWND WINAPI Hook_CreateWindowExA(DWORD ex, LPCSTR cls, LPCSTR name, DWORD style,
                                        int x, int y, int w, int h, HWND parent,
                                        HMENU menu, HINSTANCE inst, LPVOID param)
{
    HWND wnd = CreateWindowExA(ex, cls, name, style, x, y, w, h, parent, menu, inst, param);
    static int logged;
    if (wnd && logged++ < 2) {
        RECT c = {}, r = {};
        GetClientRect(wnd, &c);
        GetWindowRect(wnd, &r);
        MONITORINFO mi = { sizeof(mi) };
        GetMonitorInfoW(MonitorFromWindow(wnd, MONITOR_DEFAULTTONEAREST), &mi);
        typedef UINT(WINAPI * GetDpiForWindow_t)(HWND);
        UINT dpi = 0;
        if (HMODULE u = GetModuleHandleW(L"user32.dll"))
            if (GetDpiForWindow_t f = (GetDpiForWindow_t)GetProcAddress(u, "GetDpiForWindow"))
                dpi = f(wnd);
        Log("rndrgl: window asked %dx%d, client %ldx%ld at %ld,%ld, monitor %ldx%ld, %u dpi",
            w, h, c.right, c.bottom, r.left, r.top,
            mi.rcMonitor.right - mi.rcMonitor.left, mi.rcMonitor.bottom - mi.rcMonitor.top,
            dpi ? dpi : SystemDpi());
    }
    return wnd;
}

void RndrGL_Patch(HMODULE r)
{
    LogDisplayMetrics();
    g_hdr = IsHdrActive();
    Log("rndrgl: Windows HDR %s", g_hdr ? "ON" : "off");
    PatchIAT(r, "gdi32.dll", "SetDeviceGammaRamp", (void*)Hook_SetDeviceGammaRamp);
    PatchIAT(r, "user32.dll", "CreateWindowExA", (void*)Hook_CreateWindowExA);

    // EnumDisplaySettingsA loop in ModeList_Init stops after 512 modes; a current
    // system reports ~650 and 3840x2160 sits near the end. 512 -> 4096.
    if (g_cfg.modeList)
        Replace(r, "mode list limit 512 -> 4096", "3d 00 02 00 00 89 44 24 18 0f 8c", "3d 00 10 00 00");

    if (g_cfg.borderless) {
        // window style for AdjustWindowRectEx and CreateWindowExA:
        // WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN
        Replace(r, "style for AdjustWindowRectEx = popup", "8b 8c 24 50 09 00 00 6a 00 89 54 24 28 51", "b9 00 00 00 96 90 90");
        Replace(r, "style for CreateWindowExA = popup", "8b 8c 24 4c 09 00 00 6a 00 52", "b9 00 00 00 96 90 90");
        // the window size is clamped to SPI_GETWORKAREA (taskbar) - never clamp
        Replace(r, "no work-area clamp (width)", "3b da 7e 18 8b 96 18 07 00 00", "3b da eb 18");
        Replace(r, "no work-area clamp (height)", "3b fa 7e 18 8b 96 1c 07 00 00", "3b fa eb 18");
        // window size from rcMonitor instead of rcWork
        Replace(r, "window size from the full monitor",
                "8b 44 24 44 2b 44 24 3c 6a 00 89 44 24 5c 8b 44 24 4c 2b 44 24 44 89 44 24 58",
                "8b 44 24 34 2b 44 24 2c 6a 00 89 44 24 5c 8b 44 24 3c 2b 44 24 34 89 44 24 58");
    }

    if (g_cfg.fullViewport)
        // GetViewArea delivers the letterboxed rectangle; overwrite it on the stack
        // with (0,0,width,height) so viewport and projection both use the full surface.
        Replace(r, "full-surface viewport",
                "8b 83 70 3f 00 00 8b 8b 78 3f 00 00 3b c8 7e 02 8b c1 8b 4c 24 2c 8b 74 24 28 8b d1 2b 54 24 24 2b c1 "
                "52 8b 54 24 24 2b f2 56 50 52",
                "c7 44 24 20 00 00 00 00 c7 44 24 24 00 00 00 00 8b 83 6c 3f 00 00 89 44 24 28 8b 8b 70 3f 00 00 "
                "89 4c 24 2c 51 50 6a 00 6a 00 90 90");
}
