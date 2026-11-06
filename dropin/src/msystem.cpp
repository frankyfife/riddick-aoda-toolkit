// MSystem.dll: pad key names and the platform switch (see ../patches/rename_pad_keys.py).
//
// CScanKey::ms_ScanCodeNames holds 12-byte entries { code, code, char* name }.
// The pad buttons get a single Latin-1 donor character as their name; the fonts
// carry the matching button icon on that character (fontgen.cpp), so every text
// that spells out a key name - info boxes, tutorials, the binding page - shows
// the icon inline. The axes keep a written name.
#include "common.h"
#include <string.h>

struct NameEntry { uint32_t code; const char* de; const char* en; };
static const NameEntry kNames[] = {
    { 0xA0, "\xF0", "\xF0" },   // A
    { 0xA1, "\xF1", "\xF1" },   // B
    { 0xA2, "\xE6", "\xE6" },   // X
    { 0xA3, "\xF8", "\xF8" },   // Y
    { 0xA4, "\xE5", "\xE5" },   // START
    { 0xA5, "\xE3", "\xE3" },   // BACK
    { 0xA6, "\xF5", "\xF5" },   // L3
    { 0xA7, "\xA1", "\xA1" },   // R3
    { 0xA8, "\xBF", "\xBF" },   // LB
    { 0xA9, "\xD0", "\xD0" },   // RB
    { 0xAA, "\xD1", "\xD1" },   // LT
    { 0xAB, "\xC6", "\xC6" },   // RT
    { 0xB0, "\xEC", "\xEC" },   // d-pad up
    { 0xB1, "\xED", "\xED" },   // d-pad right
    { 0xB2, "\xEE", "\xEE" },   // d-pad down
    { 0xB3, "\xEF", "\xEF" },   // d-pad left
    { 0x80, "Linker Stick rechts", "Left stick right" },
    { 0x81, "Linker Stick links",  "Left stick left" },
    { 0x82, "Linker Stick hoch",   "Left stick up" },
    { 0x83, "Linker Stick runter", "Left stick down" },
    { 0x84, "Rechter Stick rechts", "Right stick right" },
    { 0x85, "Rechter Stick links",  "Right stick left" },
    { 0x86, "Rechter Stick hoch",   "Right stick up" },
    { 0x87, "Rechter Stick runter", "Right stick down" },
};

// name pool of the table in the shipped MSystem (preferred base 0x10000000)
static const uint32_t kPoolLo = 0x10300000, kPoolHi = 0x10301000;

static bool GermanAxisNames()
{
    wchar_t ini[MAX_PATH], b[16];
    swprintf_s(ini, L"%s\\AodaFix.ini", g_dllDir);
    GetPrivateProfileStringW(L"Prompts", L"AxisNames", L"de", b, 16, ini);
    return _wcsicmp(b, L"en") != 0;
}

static void RenamePadKeys(HMODULE ms)
{
    intptr_t delta = (intptr_t)(uintptr_t)ms - (intptr_t)PreferredBase(ms);
    bool de = GermanAxisNames();
    uint32_t** slot[_countof(kNames)] = {};
    for (size_t i = 0; i < _countof(kNames); ++i) {
        uint32_t pat[2] = { kNames[i].code, kNames[i].code };
        int hits = 0;
        for (uint8_t* p : FindAll(ms, (const uint8_t*)pat, 8)) {
            if (!InModule(ms, p + 8, 4)) continue;
            uintptr_t ptr = *(uint32_t*)(p + 8);
            // the table may already point at our strings (second start in one process: never)
            if (ptr - delta >= kPoolLo && ptr - delta < kPoolHi) { slot[i] = (uint32_t**)(p + 8); ++hits; }
        }
        if (hits != 1) {
            Log("msystem: WARNING key name table entry 0x%02X found %d times - names left alone", kNames[i].code, hits);
            return;
        }
    }
    for (size_t i = 0; i < _countof(kNames); ++i) {
        const char* s = de ? kNames[i].de : kNames[i].en;
        WriteMem(slot[i], &s, 4);
    }
    Log("msystem: %u pad key names replaced (axes %s)", (unsigned)_countof(kNames), de ? "de" : "en");
}

// One function decides which PLATFORM_ symbols the registry preprocessor defines:
//   mov eax,[eax+0x68] ; add eax,-1 ; cmp eax,4  -> jump table (XBOX, PS2, DOLPHIN, XENON, PS3, else WIN)
// Pinning the index to 3 evaluates the menus exactly like the Xbox 360 build.
static void PlatformSwitch(HMODULE ms)
{
    if (g_cfg.menuPlatform != 3 && g_cfg.menuPlatform != 4) return;
    auto hits = FindAllHex(ms, "8b 40 68 83 c0 ff 83 f8 04");
    if (hits.size() != 1) { Log("msystem: WARNING platform switch found %u times", (unsigned)hits.size()); return; }
    uint8_t code[6] = { 0xB8, (uint8_t)(g_cfg.menuPlatform == 3 ? 3 : 4), 0, 0, 0, 0x90 };
    WriteMem(hits[0], code, 6);
    Log("msystem: registry platform = %s", g_cfg.menuPlatform == 3 ? "XENON (Xbox 360 menus)" : "PS3");
}

void MSystem_Patch(HMODULE ms)
{
    if (g_cfg.xboxPrompts && g_cfg.colorIcons) RenamePadKeys(ms);   // the names are icon characters
    PlatformSwitch(ms);
}
