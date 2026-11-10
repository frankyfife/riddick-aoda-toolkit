// AodaFix - drop-in winmm.dll for The Chronicles of Riddick: Assault on Dark Athena (PC, 32 bit)
//
// Everything the Python toolkit (../patches) writes into the game files is done
// here at run time instead: code patches in memory, data files generated into a
// cache folder and served in place of the originals. The installation itself is
// never modified.
#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string>
#include <vector>
#include <algorithm>

// ---- logging -------------------------------------------------------------------
void LogInit(const wchar_t* dir);
void Log(const char* fmt, ...);

// ---- configuration (AodaFix.ini next to the DLL) -------------------------------
struct Config {
    // prompts / menus
    int  xboxPrompts;     // 1 = Xbox 360 button glyphs in hints, menus and texts
    int  helpButton;      // pad code the help bar shows (0xA6 = L3)
    int  menuPlatform;    // 0 = PC cube menu, 3 = Xbox 360 (XENON), 4 = PS3, -1 = keep
    int  menuTexts;       // 1 = "PRESS (A)" on the title screen, no "PAUSE" overlay
    int  colorIcons;      // 1 = coloured button icons inside the fonts
    int  hintSize;        // size tag for the menu button hints (Weiterspielen/Zurueck), 0 = original (35)
    int  hintIconSize;    // visible icon size inside the 32x32 hint texture
    // display
    int  borderless;      // 1 = borderless full-monitor window, no work-area clamp
    int  fullViewport;    // 1 = viewport covers the whole window (no letterbox)
    int  modeList;        // 1 = enumerate up to 4096 display modes (4K becomes visible)
    int  desktopMode;     // 1 = VID_MODE = desktop resolution and refresh rate
    int  gammaRamp;       // 1 = allow, 0 = ignore, -1 = auto (ignore while Windows HDR is on)
    // renderer / gameplay
    int  shaderFix;       // 1 = legal texture2D/textureCube calls in HLInclude_GLSL.xrg
    int  shaderMode;      // -1 = keep (out-of-range values are still fixed), 0..6 force
    int  aimAssist;       // 1 = keep weapon autoaim flags, 0 = remove them
    // rumble
    int  rumble;
    float rumbleGain;
    int  rumbleSwap;
    int  rumbleLog;
    int  fileLog;         // log every data file the engine opens
    int  textLog;         // log every distinct 2D text with scale and caller
};
extern Config g_cfg;
extern wchar_t g_dllDir[MAX_PATH];
extern wchar_t g_gameRoot[MAX_PATH];
extern wchar_t g_cacheDir[MAX_PATH];
void ConfigLoad();

// ---- memory helpers --------------------------------------------------------------
bool  WriteMem(void* dst, const void* src, size_t n);
void* PatchIAT(HMODULE module, const char* importDll, const char* func, void* replacement);
// all matches of `pat` (mask: '?' = any byte, else must match) inside the mapped image
std::vector<uint8_t*> FindAll(HMODULE module, const uint8_t* pat, size_t n, const char* mask = nullptr);
std::vector<uint8_t*> FindAllHex(HMODULE module, const char* hex);   // "8b 44 24 ?? 05"
bool  InModule(HMODULE module, const void* p, size_t n = 1);
uint8_t* RelTarget(uint8_t* at, int opsize = 1);                     // target of a rel32 jmp/call at `at`
uint32_t ImageSize(HMODULE module);
uint32_t PreferredBase(HMODULE module);

// ---- files ------------------------------------------------------------------------
bool ReadFileAll(const std::wstring& p, std::vector<uint8_t>& out);
bool WriteFileAll(const std::wstring& p, const std::vector<uint8_t>& data);
void Files_AddRedirect(const std::string& relLower, const std::wstring& target);
void Files_PatchModule(HMODULE mod);
// Fresh cache entry? The stamp holds source size/time plus a generator version.
bool Cache_IsFresh(const std::wstring& out, const std::wstring& src, const char* version);
void Cache_Stamp(const std::wstring& out, const std::wstring& src, const char* version);

// ---- subsystems -------------------------------------------------------------------
void OnModuleLoaded(HMODULE mod, const char* name);
void MSystem_Patch(HMODULE msys);                 // pad key names, platform switch
void Glyphs_Patch(HMODULE mod, const char* name); // GameClasses / GameWorld button glyphs
void TextLog_Patch(HMODULE mod, const char* name);
void RndrGL_Patch(HMODULE rndr);                  // borderless window, mode list, viewport, gamma
void DataGen_Run();                               // menus, strings, weapons, shader include
void FontGen_Run();                               // coloured button icons inside the fonts
void EnvCfg_Prepare();                            // Environment.cfg sanity
void Rumble_Init();
void __stdcall Rumble_Play(int id);
void Rumble_Shutdown(bool callXInput);   // false on process exit
void Display_Shutdown();
