// MSystem.dll: pad key names and the platform switch (see ../patches/rename_pad_keys.py).
//
// CScanKey::ms_ScanCodeNames holds 12-byte entries { code, code, char* name }.
// The pad buttons get a single Latin-1 donor character as their name; the fonts
// carry the matching button icon on that character (fontgen.cpp), so every text
// that spells out a key name - info boxes, tutorials, the binding page - shows
// the icon inline. The axes keep a written name.
#include "common.h"
#include <string.h>

// The donor characters are letters no language of the game uses, in its string
// tables, dialogues or credits, in either case where that could be had: the
// first choice (n-tilde, the inverted marks, the accented i) turned every Spanish
// "n~" into a B button. Counted over all five languages; the last two (0xCE, 0xCF)
// are capitals whose small form French does use, so they carry the d-pad.
// fontgen.cpp paints the icons onto exactly these characters.
struct PadIcon { uint32_t code; const char* name; };
static const PadIcon kIcons[] = {
    { 0xA0, "\xF0" },   // A
    { 0xA1, "\xFD" },   // B
    { 0xA2, "\xE6" },   // X
    { 0xA3, "\xF8" },   // Y
    { 0xA4, "\xEB" },   // START
    { 0xA5, "\xE3" },   // BACK
    { 0xA6, "\xF5" },   // L3
    { 0xA7, "\xD5" },   // R3
    { 0xA8, "\xD8" },   // LB
    { 0xA9, "\xD0" },   // RB
    { 0xAA, "\xC3" },   // LT
    { 0xAB, "\xC6" },   // RT
    { 0xB0, "\xDD" },   // d-pad up
    { 0xB1, "\xCB" },   // d-pad right
    { 0xB2, "\xCE" },   // d-pad down
    { 0xB3, "\xCF" },   // d-pad left
};

// stick directions, written out: en de fr it es
enum { kEn, kDe, kFr, kIt, kEs, kLangCount };
struct AxisName { uint32_t code; const char* name[kLangCount]; };
static const AxisName kAxes[] = {
    { 0x80, { "Left stick right",  "Linker Stick rechts",  "Stick gauche vers la droite", "Levetta sinistra a destra",   "Stick izquierdo a la derecha" } },
    { 0x81, { "Left stick left",   "Linker Stick links",   "Stick gauche vers la gauche", "Levetta sinistra a sinistra", "Stick izquierdo a la izquierda" } },
    { 0x82, { "Left stick up",     "Linker Stick hoch",    "Stick gauche vers le haut",   "Levetta sinistra in alto",    "Stick izquierdo arriba" } },
    { 0x83, { "Left stick down",   "Linker Stick runter",  "Stick gauche vers le bas",    "Levetta sinistra in basso",   "Stick izquierdo abajo" } },
    { 0x84, { "Right stick right", "Rechter Stick rechts", "Stick droit vers la droite",  "Levetta destra a destra",     "Stick derecho a la derecha" } },
    { 0x85, { "Right stick left",  "Rechter Stick links",  "Stick droit vers la gauche",  "Levetta destra a sinistra",   "Stick derecho a la izquierda" } },
    { 0x86, { "Right stick up",    "Rechter Stick hoch",   "Stick droit vers le haut",    "Levetta destra in alto",      "Stick derecho arriba" } },
    { 0x87, { "Right stick down",  "Rechter Stick runter", "Stick droit vers le bas",     "Levetta destra in basso",     "Stick derecho abajo" } },
};

// name pool of the table in the shipped MSystem (preferred base 0x10000000)
static const uint32_t kPoolLo = 0x10300000, kPoolHi = 0x10301000;

// [Prompts] AxisNames: auto follows the game's language (LANGUAGE in Environment.cfg)
static int AxisLanguage(const char** shown)
{
    static const char* const kTag[kLangCount] = { "en", "de", "fr", "it", "es" };
    static const char* const kGame[kLangCount] = { "ENG", "GER", "FRE", "ITA", "SPA" };
    wchar_t ini[MAX_PATH], b[16];
    swprintf_s(ini, L"%s\\AodaFix.ini", g_dllDir);
    GetPrivateProfileStringW(L"Prompts", L"AxisNames", L"auto", b, 16, ini);
    int lang = kEn;
    bool found = false;
    for (int i = 0; i < kLangCount; ++i) {
        wchar_t w[4] = { (wchar_t)kTag[i][0], (wchar_t)kTag[i][1], 0 };
        if (!_wcsicmp(b, w)) { lang = i; found = true; }
    }
    if (!found) {
        std::string game = EnvCfg_Language();
        for (int i = 0; i < kLangCount; ++i) if (!_stricmp(game.c_str(), kGame[i])) lang = i;
    }
    *shown = kTag[lang];
    return lang;
}

static void RenamePadKeys(HMODULE ms)
{
    intptr_t delta = (intptr_t)(uintptr_t)ms - (intptr_t)PreferredBase(ms);
    const char* tag = "en";
    int lang = AxisLanguage(&tag);
    struct Entry { uint32_t code; const char* name; };
    std::vector<Entry> names;
    for (auto& i : kIcons) names.push_back({ i.code, i.name });
    for (auto& a : kAxes) names.push_back({ a.code, a.name[lang] });
    std::vector<uint32_t**> slot(names.size(), nullptr);
    for (size_t i = 0; i < names.size(); ++i) {
        uint32_t pat[2] = { names[i].code, names[i].code };
        int hits = 0;
        for (uint8_t* p : FindAll(ms, (const uint8_t*)pat, 8)) {
            if (!InModule(ms, p + 8, 4)) continue;
            uintptr_t ptr = *(uint32_t*)(p + 8);
            // the table may already point at our strings (second start in one process: never)
            if (ptr - delta >= kPoolLo && ptr - delta < kPoolHi) { slot[i] = (uint32_t**)(p + 8); ++hits; }
        }
        if (hits != 1) {
            Log("msystem: WARNING key name table entry 0x%02X found %d times - names left alone", names[i].code, hits);
            return;
        }
    }
    for (size_t i = 0; i < names.size(); ++i) WriteMem(slot[i], &names[i].name, 4);
    Log("msystem: %u pad key names replaced (axes %s)", (unsigned)names.size(), tag);
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
    HelpKey_HookConsole(ms);
    KeyText_Hook(ms);
    Hotplug_Hook(ms);
}
