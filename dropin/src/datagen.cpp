// Generated data files: menu definitions, string tables, weapon flags, shader
// include. Ports of ../patches/{rename_pad_keys,enable_buttondesc,pc_button_icons,
// menu_texte,aim_assist}.py, plus the GLSL fix. Sources are read from
// the installation, results go to AodaFix_cache and are served by files.cpp.
// All edits are byte-exact: CRLF line endings are counted before and after.
#include "common.h"
#include <functional>
#include <string.h>

static const char kVersion[] = "datagen 5";

static size_t CountCrlf(const std::string& s)
{
    size_t n = 0;
    for (size_t i = 0; i + 1 < s.size(); ++i) if (s[i] == '\r' && s[i + 1] == '\n') ++n;
    return n;
}

static int ReplaceAll(std::string& s, const std::string& a, const std::string& b)
{
    int n = 0;
    for (size_t p = 0; (p = s.find(a, p)) != std::string::npos; p += b.size(), ++n) s.replace(p, a.size(), b);
    return n;
}

static bool IsSpace(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
static bool IsAlpha(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }

// ---- menu definitions ----------------------------------------------------------------
// The console build declares its menu hints as "*BUTTONDESC1 b,<label>"; the PC
// port has those lines commented out and draws key caps via *OUTSIDEBUTTON.
static int EnableButtonDesc(std::string& s, const char* only)
{
    int n = 0;
    for (size_t p = 0; (p = s.find("//", p)) != std::string::npos; p += 2) {
        size_t q = p + 2;
        while (q < s.size() && IsSpace(s[q])) ++q;
        if (s.compare(q, 11, "*BUTTONDESC") != 0 || q + 12 >= s.size() || s[q + 11] < '0' || s[q + 11] > '3') continue;
        size_t k = q + 12;
        if (k >= s.size() || !IsSpace(s[k])) continue;
        while (k < s.size() && IsSpace(s[k])) ++k;
        size_t comma = s.find(',', k);
        if (comma == std::string::npos || comma == k) continue;
        std::string key = s.substr(k, comma - k);
        while (!key.empty() && IsSpace(key.back())) key.pop_back();
        for (auto& c : key) c = (char)tolower((unsigned char)c);
        if (only && !strstr(only, (key + ",").c_str())) continue;
        // Two of these lines were never hints on the console either (its compiled
        // menu file has neither label), and nothing answers their button on the PC:
        //   y,MENU_DELETE     profile list - "this one is dynamic", but no code sets it;
        //                     the list has its own "delete profile" entry
        //   x,MENU_BACKSPACE  name entry - X only deletes with textinput.cpp. Slot 2 is
        //                     the right-hand one and lies across the cube on a wide
        //                     screen; slot 3 is on the left, above "Back".
        if (s.compare(comma + 1, 13, "\xA7LMENU_DELETE") == 0 && !IsAlpha(s[comma + 14]) && s[comma + 14] != '_') continue;
        if (s.compare(comma + 1, 16, "\xA7LMENU_BACKSPACE") == 0) {
            if (!g_cfg.padDelete) continue;
            s[q + 11] = '3';
        }
        s[p] = ' '; s[p + 1] = ' ';
        ++n;
    }
    return n;
}

// "Back" sits on B in the console layout; a few MENU_BACK hints carry key a.
static int BackOnB(std::string& s)
{
    int n = 0;
    for (size_t p = 0; (p = s.find("*BUTTONDESC0", p)) != std::string::npos; p += 12) {
        size_t q = p + 12;
        if (q >= s.size() || !IsSpace(s[q])) continue;
        while (q < s.size() && IsSpace(s[q])) ++q;
        if (s.compare(q, 2, "a,") == 0 && s.compare(q + 2, 11, "\xA7LMENU_BACK") == 0) { s[q] = 'b'; ++n; }
    }
    return n;
}

static int DisableOutsideButtons(std::string& s)
{
    int n = 0;
    for (size_t p = 0; (p = s.find("*OUTSIDEBUTTON", p)) != std::string::npos; p += 16) {
        if (p > 0 && s[p - 1] == '/') { p -= 2; continue; }
        s.insert(p, "//");
        ++n;
    }
    return n;
}

// The hint labels are drawn without a size tag, i.e. at the full 35-pixel line
// height of the 640x480 canvas; info texts use "§Z16", the game's own A/B pad
// descriptor "§Z20". A size tag in front of the label: "a,§LMENU_BACK" ->
// "a,§Z20§LMENU_BACK" (the menus already combine both, e.g. *FOOTNOTE).
static int SizeButtonLabels(std::string& s, int size)
{
    if (size <= 0) return 0;
    char tag[8]; sprintf_s(tag, "\xA7Z%d", size);
    int n = 0;
    for (size_t p = 0; (p = s.find("*BUTTONDESC", p)) != std::string::npos; p += 11) {
        size_t le = s.find_first_of("\r\n", p);
        size_t c = s.find(',', p);
        if (c == std::string::npos || c > le || c + 1 >= s.size()) continue;
        if (s[c + 1] != '\xA7' || (c + 2 < s.size() && s[c + 2] == 'Z')) continue;   // no §-label, or sized already
        s.insert(c + 1, tag);
        ++n;
    }
    return n;
}

// The hint icons are drawn as a 32x32 box at *ICONPOSITION_n (smaller icon centred
// in the texture, fontgen.cpp). Move the boxes down so the icon centres on the
// smaller label.
static int MoveHintIcons(std::string& s, int iconSize, int textSize)
{
    if (iconSize <= 0 || iconSize >= 32 || textSize <= 0) return 0;
    int dy = (35 - textSize) * 3 / 15;          // 0 at the original size, 3 at §Z20
    int n = 0;
    for (int i = 1; i <= 4; ++i) {
        char key[32]; sprintf_s(key, "*ICONPOSITION_%d", i);
        size_t p = s.find(key);
        if (p == std::string::npos) continue;
        size_t v = p + strlen(key), le = s.find_first_of("\r\n", v);
        int x = 0, y = 0;
        if (sscanf_s(s.substr(v, le - v).c_str(), " %d , %d", &x, &y) != 2) continue;
        y += dy;
        char nv[32]; sprintf_s(nv, " %d, %d", x, y);
        s.replace(v, le - v, nv);
        ++n;
    }
    return n;
}

// The console menus have no profiles of their own: there the gamer profile comes
// from the system. Without a saved profile their start-up ends at "no gamer profile
// selected - continue without saving?", and whichever answer is given, no profile
// can ever be created: a fresh installation is stuck. The PC branch of the same
// window goes to the profile list instead; the console branch now does too. The
// Xbox options page also offers "select storage device", which means nothing on a
// PC; the PC's "Profiles" entry takes its place.
static int ProfilesOnConsoleMenus(std::string& s)
{
    int n = ReplaceAll(s, "\\\"cg_rootmenu('MainMenu')\\\", \\\"cg_rootmenu('cant_save_progress')\\\"",
                          "\\\"cg_rootmenu('MainMenu')\\\", \\\"cg_rootmenu('select_profile')\\\"");
    n += ReplaceAll(s, "*TEXT nc, \xA7LMENU_SELECT_STORAGE\r\n\t\t*SCRIPT_PRESSED \"padlock(); storageselect(); cg_prevmenu()\"",
                       "*TEXT nc, \xA7LMENU_PROFILE\r\n\t\t*SCRIPT_PRESSED \"saveprofile(); cg_submenu(\\\"select_profile_option\\\")\"");
    return n;
}

// [Gameplay] UnlockAll: the developers' menus are still in the menu file - the
// map list ("Zones", X or Space in the main menu), the debug menu (X or Space in
// the pause menu), the generic video page. Each sits behind
//     "cheat(\"<script>\")"
// which runs <script> only with cheats on. The wrapper is taken away; inside it
// quotes are escaped once more (\\\" -> \").
static int OpenCheatMenus(std::string& s)
{
    static const char kOpen[] = "cheat(\\\"";          // cheat(\"
    int n = 0;
    for (size_t p = 0; (p = s.find(kOpen, p)) != std::string::npos;) {
        std::string inner;
        size_t q = p + sizeof(kOpen) - 1, le = s.find_first_of("\r\n", p);
        bool closed = false;
        while (q < le) {
            if (s.compare(q, 4, "\\\\\\\"") == 0) { inner += "\\\""; q += 4; }        // \\\" -> \"
            else if (s.compare(q, 3, "\\\")") == 0) { q += 3; closed = true; break; }     // \")
            else inner += s[q++];
        }
        if (!closed) { p += sizeof(kOpen) - 1; continue; }
        s.replace(p, q - p, inner);
        p += inner.size();
        ++n;
    }
    return n;
}

static bool MenuFile(std::string& s, bool cubeWnd)
{
    size_t crlf = CountCrlf(s);
    int acc = 0, icons = 0, bd = 0, bb = 0, ob = 0, sz = 0;
    // these two are about the console menus themselves, whatever the prompts look like
    int pr = cubeWnd ? ProfilesOnConsoleMenus(s) : 0;
    if (cubeWnd && pr != 2) Log("datagen: WARNING profile entries of the console menus: %d of 2 found", pr);
    // PS3 cube: after the autosave notice the PS3 build installs its trophies
    // (install_trophies -> loadtrophies()); there is nothing to install on PC.
    // Go straight to the main menu, as the Xbox 360 branch does.
    int tr = cubeWnd ? ReplaceAll(s, "*SCRIPT_PRESSED \"cg_rootmenu('install_trophies')\"",
                                     "*SCRIPT_PRESSED \"cg_rootmenu('Menu_ToFork')\"") : 0;
    int ch = (cubeWnd && g_cfg.unlockAll) ? OpenCheatMenus(s) : 0;
    if (ch) Log("datagen: CubeWnd: %d developer menu shortcuts opened (UnlockAll)", ch);
    if (g_cfg.xboxPrompts) {
        if (cubeWnd && g_cfg.colorIcons) {
            // accelerators that name pad keys follow the renamed key names (msystem.cpp)
            acc += ReplaceAll(s, "JOY_BUTTON_02", "\xE6");
            acc += ReplaceAll(s, "JOY_BUTTON_03", "\xF8");
        }
        bd = EnableButtonDesc(s, cubeWnd ? nullptr : "a,b,");   // CubeInv0: arrows overlap the page labels
        bb = BackOnB(s);
        ob = DisableOutsideButtons(s);
        sz = SizeButtonLabels(s, g_cfg.hintSize);
        int mv = (cubeWnd && g_cfg.hintSize > 0) ? MoveHintIcons(s, g_cfg.hintIconSize, g_cfg.hintSize) : 0;
        if (mv) Log("datagen: %d hint icon positions adjusted for %dpx icons", mv, g_cfg.hintIconSize);
        // the paler _32 artwork does not exist on the Xbox 360 - use the full icons
        static const char* const kWnd[][2] = {
            { "*ICONSURFACE_Y \"GUI_Button_Y_32\"", "*ICONSURFACE_Y \"GUI_Button_Y\"" },
            { "*ICONSURFACE_X \"GUI_Button_X_32\"", "*ICONSURFACE_X \"GUI_Button_X\"" },
            { "*ICONSURFACE_B \"GUI_Button_B_32\"", "*ICONSURFACE_B \"GUI_Button_B\"" },
            { "*ICONSURFACE_A \"GUI_Button_A_32\"", "*ICONSURFACE_A \"GUI_Button_A\"" },
            { "*BICONSURFACE \"GUI_Button_B_32\"", "*BICONSURFACE \"GUI_Button_B\"" },
            { "*AICONSURFACE \"GUI_Button_A_32\"", "*AICONSURFACE \"GUI_Button_A\"" },
        };
        static const char* const kInv[][2] = { { "*ICONSURFACE GUI_Button_A_32", "*ICONSURFACE GUI_Button_A" } };
        // With HintSize the _32 textures themselves are regenerated (fontgen.cpp: full
        // colours, smaller, centred), so the button descriptors keep their _32 names.
        if (cubeWnd && g_cfg.hintSize <= 0) for (auto& r : kWnd) icons += ReplaceAll(s, r[0], r[1]);
        else for (auto& r : kInv) icons += ReplaceAll(s, r[0], r[1]);
    }
    if (CountCrlf(s) != crlf) { Log("datagen: line endings changed - discarded"); return false; }
    Log("datagen: %s: %d accelerators, %d BUTTONDESC on, %d back->B, %d OUTSIDEBUTTON off, %d icons, %d labels sized %d, %d trophy installs skipped, %d profile entries",
        cubeWnd ? "CubeWnd" : "CubeInv0", acc, bd, bb, ob, icons, sz, g_cfg.hintSize, tr, pr);
    return bd > 0 || pr > 0 || tr > 0 || ch > 0;
}

// ---- string tables (UTF-16LE with BOM or Latin-1) -----------------------------------------
struct StringTable {
    bool utf16 = false;
    std::wstring t;
    explicit StringTable(const std::vector<uint8_t>& raw)
    {
        utf16 = raw.size() >= 2 && raw[0] == 0xFF && raw[1] == 0xFE;
        if (utf16) t.assign((const wchar_t*)(raw.data() + 2), (raw.size() - 2) / 2);
        else for (uint8_t c : raw) t.push_back((wchar_t)c);
    }
    // the value of *KEY "...": position and length inside t; the key has to occur exactly once
    bool Find(const char* key, size_t& at, size_t& len, bool quiet = false) const
    {
        std::wstring k = L"*";
        for (const char* c = key; *c; ++c) k.push_back((wchar_t)*c);
        size_t hit = std::wstring::npos; int n = 0;
        for (size_t p = 0; (p = t.find(k, p)) != std::wstring::npos; p += k.size()) {
            size_t q = p + k.size();
            if (q >= t.size() || (t[q] != L' ' && t[q] != L'\t')) continue;
            while (q < t.size() && (t[q] == L' ' || t[q] == L'\t')) ++q;
            if (q < t.size() && t[q] == L'"') { hit = q + 1; ++n; }
        }
        if (n != 1) { if (!quiet) Log("datagen: *%s found %d times", key, n); return false; }
        size_t end = t.find(L'"', hit);
        if (end == std::wstring::npos) return false;
        at = hit; len = end - hit;
        return true;
    }
    void Store(std::vector<uint8_t>& raw) const
    {
        raw.clear();
        if (utf16) {
            raw.push_back(0xFF); raw.push_back(0xFE);
            raw.insert(raw.end(), (const uint8_t*)t.data(), (const uint8_t*)(t.data() + t.size()));
        } else {
            for (wchar_t c : t) raw.push_back((uint8_t)(c < 256 ? c : '?'));
        }
    }
};

static bool SetStringValue(std::vector<uint8_t>& raw, const char* key, const std::wstring& value)
{
    StringTable st(raw);
    size_t at, len;
    if (!st.Find(key, at, len)) return false;
    st.t.replace(at, len, value);
    st.Store(raw);
    return true;
}

// Title screen: the console's own line with the A icon where it says START -
// "PRESS START" becomes "PRESS (A)", "START DRUECKEN" "(A) DRUECKEN", and so on in
// whatever language the table is. U+00F0 carries the A icon (fontgen.cpp).
static bool TitlePrompt(std::vector<uint8_t>& raw)
{
    StringTable st(raw);
    size_t at, len;
    if (!st.Find("MENU_PRESSSTART", at, len)) return false;
    std::wstring v = st.t.substr(at, len);
    size_t p = v.find(L"START");
    if (p == std::wstring::npos) { Log("datagen: MENU_PRESSSTART does not say START"); return false; }
    v.replace(p, 5, L"\x00F0");
    if (!st.Find("MENU_PRESSSTART_PC", at, len)) return false;
    st.t.replace(at, len, v);
    st.Store(raw);
    return true;
}

// Info texts name a key through a placeholder, CONTROLLER_<ACTION>_<form>, which
// stands for the binding ACTION_<ACTION> (keytext.cpp puts the pad there). Four
// of the actions the texts use have no pad binding to put there:
//   WEAPONFLASHLIGHT  keyboard only (G). The PC branch of the flashlight text
//                     uses it, the console branch names the d-pad: "#ifdef
//                     PLATFORM_WIN_PC ... #else ... DPAD_DOWN". With the PC menu
//                     that text said "pressing G".
//   EYESHINE          keyboard only (Q), in the Dark Athena tutorial of every
//                     language and in the German and French Butcher Bay one. The
//                     other languages say DPAD_UP in that same text.
//   CROUCHTOGGLE      German and French only; not a binding the game sets up at
//                     all, the English text says CROUCH.
//   SPRINT2           the pad slot by name, in the multiplayer hints - which is
//                     the keyboard's once the two slots answer for each other.
// They are pointed at the action the pad does have. Only the placeholder
// changes, its form (_A, _C3, ...) and the sentence stay.
static bool PadActions(std::vector<uint8_t>& raw)
{
    static const wchar_t* const kMap[][2] = {
        { L"\x00A7" L"LCONTROLLER_WEAPONFLASHLIGHT_", L"\x00A7" L"LCONTROLLER_DPAD_DOWN_" },
        { L"\x00A7" L"LCONTROLLER_EYESHINE_",         L"\x00A7" L"LCONTROLLER_DPAD_UP_" },
        { L"\x00A7" L"LCONTROLLER_CROUCHTOGGLE_",     L"\x00A7" L"LCONTROLLER_CROUCH_" },
        { L"\x00A7" L"LCONTROLLER_SPRINT2_",          L"\x00A7" L"LCONTROLLER_SPRINT_" },
    };
    StringTable st(raw);
    int n = 0;
    for (auto& m : kMap) {
        size_t from = wcslen(m[0]), to = wcslen(m[1]);
        for (size_t p = 0; (p = st.t.find(m[0], p)) != std::wstring::npos; p += to) { st.t.replace(p, from, m[1]); ++n; }
    }
    if (!n) return false;
    st.Store(raw);
    return true;
}

// ---- weapons: the menu's aim-assist slider is inert; the item flag 'autoaim' is the switch --
static int RemoveAutoaim(std::string& s)
{
    int n = 0;
    for (size_t p = 0; (p = s.find("*flags", p)) != std::string::npos; p += 6) {
        size_t le = s.find_first_of("\r\n", p);
        if (le == std::string::npos) le = s.size();
        for (size_t a = p; (a = s.find("autoaim", a)) != std::string::npos && a < le;) {
            bool before = a > 0 && IsAlpha(s[a - 1]);
            bool after = a + 7 < s.size() && IsAlpha(s[a + 7]);
            if (before || after) { a += 7; continue; }      // e.g. noautoaim
            size_t from = a, len = 7;
            if (a + 7 < le && s[a + 7] == '+') len = 8;      // "autoaim+"
            else if (a > p && s[a - 1] == '+') { from = a - 1; len = 8; }   // "+autoaim"
            s.erase(from, len);
            le -= len;
            ++n;
            a = from;
        }
    }
    return n;
}

// ---- generator plumbing ------------------------------------------------------------------
static void Gen(const char* rel, const std::string& variant, const std::function<bool(std::vector<uint8_t>&)>& fn)
{
    std::wstring wrel;
    for (const char* c = rel; *c; ++c) wrel.push_back((wchar_t)*c);
    std::wstring src = std::wstring(g_gameRoot) + L"\\" + wrel;
    std::wstring dst = std::wstring(g_cacheDir) + L"\\" + wrel;
    std::string ver = std::string(kVersion) + " " + variant;
    std::string key = rel;
    for (auto& c : key) c = (char)tolower((unsigned char)c);
    if (GetFileAttributesW(src.c_str()) == INVALID_FILE_ATTRIBUTES) { Log("datagen: %s missing", rel); return; }
    if (!Cache_IsFresh(dst, src, ver.c_str())) {
        std::vector<uint8_t> d;
        if (!ReadFileAll(src, d)) { Log("datagen: cannot read %s", rel); return; }
        if (!fn(d)) { Log("datagen: %s unchanged/unrecognised - original used", rel); DeleteFileW(dst.c_str()); return; }
        if (!WriteFileAll(dst, d)) { Log("datagen: cannot write %ls", dst.c_str()); return; }
        Cache_Stamp(dst, src, ver.c_str());
        Log("datagen: %s generated", rel);
    }
    Files_AddRedirect(key, dst);
}

static std::function<bool(std::vector<uint8_t>&)> AsText(const std::function<bool(std::string&)>& fn)
{
    return [fn](std::vector<uint8_t>& d) {
        std::string s(d.begin(), d.end());
        if (!fn(s)) return false;
        d.assign(s.begin(), s.end());
        return true;
    };
}

void DataGen_Run()
{
    bool consoleMenu = g_cfg.menuPlatform == 3 || g_cfg.menuPlatform == 4;
    std::string hs = std::to_string(g_cfg.xboxPrompts) + "_" + std::to_string(g_cfg.hintSize) + "_" + std::to_string(g_cfg.hintIconSize) + "_" +
                     std::to_string(g_cfg.colorIcons) + "_" + std::to_string(g_cfg.padDelete) + "_" +
                     std::to_string(g_cfg.unlockAll);   // cache key
    // CubeWnd also carries the profile fix of the console menus, prompts or not
    if (g_cfg.xboxPrompts || consoleMenu || g_cfg.unlockAll)
        Gen("Content\\GUI\\CubeWnd.xrg", "w" + hs, AsText([](std::string& s) { return MenuFile(s, true); }));
    if (g_cfg.xboxPrompts)
        Gen("Content\\GUI\\CubeInv0.xrg", "i" + hs, AsText([](std::string& s) { return MenuFile(s, false); }));
    // English lives in Content, every other language in its own folder; a language
    // that is not installed is skipped without a word
    static const char* const kLangs[][2] = { { "Content", "Eng" }, { "Content_Ger", "Ger" }, { "Content_Fre", "Fre" },
                                             { "Content_Ita", "Ita" }, { "Content_Spa", "Spa" } };
    for (auto& l : kLangs) {
        std::string dir = std::string(l[0]) + "\\Registry\\Stringtables\\";
        std::string front = dir + "Frontend_" + l[1] + ".txt", x360 = dir + "StringsX360_" + l[1] + ".txt";
        auto there = [](const std::string& rel) {
            std::wstring w(g_gameRoot); w += L'\\';
            for (char c : rel) w.push_back((wchar_t)(unsigned char)c);
            return GetFileAttributesW(w.c_str()) != INVALID_FILE_ATTRIBUTES;
        };
        // title screen: "PRESS (A)" like the console
        if (g_cfg.xboxPrompts && g_cfg.menuTexts && g_cfg.colorIcons && there(front)) Gen(front.c_str(), "t2", TitlePrompt);
        // the Xbox menus show STD_PAUSED at the bottom of the pause menu
        if (g_cfg.menuTexts && g_cfg.menuPlatform == 3 && there(x360))
            Gen(x360.c_str(), "p", [](std::vector<uint8_t>& d) { return SetStringValue(d, "STD_PAUSED", L""); });
        // texts that name an action the pad has no binding for (same condition as keytext.cpp)
        if (g_cfg.textButtons && g_cfg.xboxPrompts && g_cfg.colorIcons)
            for (const char* table : { "Ingame_", "Ingame_Athena_", "Multiplayer_" }) {
                std::string rel = dir + table + l[1] + ".txt";
                if (there(rel)) Gen(rel.c_str(), "k", PadActions);
            }
    }
    if (!g_cfg.aimAssist)
        Gen("Content\\Registry\\RpgWeapons.xrg", "a", AsText([](std::string& s) {
            size_t crlf = CountCrlf(s);
            int n = RemoveAutoaim(s);
            Log("datagen: aim assist off - %d weapons lose 'autoaim'", n);
            return n > 0 && CountCrlf(s) == crlf;
        }));
    if (g_cfg.shaderFix)
        // the three-argument texture2D/textureCube is illegal in fragment shaders;
        // current drivers reject it and the game aborts in GLSL_LoadSrc
        Gen("System\\GL\\HLInclude_GLSL.xrg", "g", AsText([](std::string& s) {
            int n = ReplaceAll(s, "{ return texture2D(_tex, _st, _bias); }", "{ return texture2D(_tex, _st); }");
            n += ReplaceAll(s, "{ return textureCube(_tex, _str, _bias); }", "{ return textureCube(_tex, _str); }");
            Log("datagen: GLSL bias calls fixed: %d", n);
            return n == 2;
        }));
}
