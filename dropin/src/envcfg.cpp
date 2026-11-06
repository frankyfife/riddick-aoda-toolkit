// Environment.cfg (%LOCALAPPDATA%\Atari\<game>\Environment.cfg) sanity before the
// engine reads it: a valid shader level, and the desktop mode as VID_MODE.
#include "common.h"
#include <shlobj.h>
#include <string.h>

static std::string GetKey(const std::string& s, const char* key)
{
    std::string k = std::string(key) + "=";
    for (size_t p = 0; (p = s.find(k, p)) != std::string::npos; p += k.size()) {
        if (p > 0 && s[p - 1] != '\n') continue;
        size_t e = s.find_first_of("\r\n", p);
        return s.substr(p + k.size(), (e == std::string::npos ? s.size() : e) - p - k.size());
    }
    return "\x01";   // missing
}

static bool SetKey(std::string& s, const char* key, const std::string& v)
{
    std::string k = std::string(key) + "=";
    for (size_t p = 0; (p = s.find(k, p)) != std::string::npos; p += k.size()) {
        if (p > 0 && s[p - 1] != '\n') continue;
        size_t e = s.find_first_of("\r\n", p);
        if (e == std::string::npos) e = s.size();
        if (s.compare(p + k.size(), e - p - k.size(), v) == 0) return false;
        s.replace(p + k.size(), e - p - k.size(), v);
        return true;
    }
    if (!s.empty() && s.back() != '\n') s += "\r\n";
    s += k + v + "\r\n";
    return true;
}

void EnvCfg_Prepare()
{
    wchar_t la[MAX_PATH];
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA, nullptr, 0, la))) return;
    std::wstring dir = std::wstring(la) + L"\\Atari";
    CreateDirectoryW(dir.c_str(), nullptr);
    dir += L"\\The Chronicles of Riddick - Assault on Dark Athena";
    CreateDirectoryW(dir.c_str(), nullptr);
    std::wstring cfg = dir + L"\\Environment.cfg";

    std::vector<uint8_t> raw;
    if (!ReadFileAll(cfg, raw)) {
        // first start: the game seeds its cfg from the shipped one (XR_SHADERMODE=11 there)
        if (!ReadFileAll(std::wstring(g_gameRoot) + L"\\Environment.cfg", raw)) { Log("envcfg: no Environment.cfg yet"); return; }
        Log("envcfg: seeded from the game folder");
    }
    std::string s(raw.begin(), raw.end());
    bool changed = false;

    std::string sm = GetKey(s, "XR_SHADERMODE");
    if (g_cfg.shaderMode >= 0) changed |= SetKey(s, "XR_SHADERMODE", std::to_string(g_cfg.shaderMode));
    else if (sm != "\x01" && (atoi(sm.c_str()) < 0 || atoi(sm.c_str()) > 6)) {
        Log("envcfg: XR_SHADERMODE=%s is outside 0..6 (crash in GLSL_LoadSrc) -> 0 (auto)", sm.c_str());
        changed |= SetKey(s, "XR_SHADERMODE", "0");
    }

    if (g_cfg.desktopMode) {
        DEVMODEW dm = {}; dm.dmSize = sizeof(dm);
        if (EnumDisplaySettingsW(nullptr, ENUM_CURRENT_SETTINGS, &dm)) {
            char v[64];
            sprintf_s(v, "%lu %lu 32 %lu", dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency);
            std::string old = GetKey(s, "VID_MODE");
            if (SetKey(s, "VID_MODE", v)) { changed = true; Log("envcfg: VID_MODE %s -> %s", old == "\x01" ? "(none)" : old.c_str(), v); }
        }
    }
    if (!changed) { Log("envcfg: ok (VID_MODE=%s, XR_SHADERMODE=%s)", GetKey(s, "VID_MODE").c_str(), GetKey(s, "XR_SHADERMODE").c_str()); return; }
    HANDLE h = CreateFileW(cfg.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) { Log("envcfg: cannot write %ls", cfg.c_str()); return; }
    DWORD wr; WriteFile(h, s.data(), (DWORD)s.size(), &wr, nullptr); CloseHandle(h);
}
