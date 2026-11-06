// File redirection: generated copies in AodaFix_cache are served in place of the
// game's data files. Size queries (GetFileAttributesExA) are redirected as well,
// because the engine may size its read buffer before it opens the file.
#include "common.h"
#include <map>
#include <mutex>

static std::map<std::string, std::wstring> g_redirect;   // lower-case relative path -> generated file
static std::mutex g_mx;
static int g_logged;

void Files_AddRedirect(const std::string& relLower, const std::wstring& target)
{
    std::lock_guard<std::mutex> l(g_mx);
    g_redirect[relLower] = target;
    Log("redirect %s", relLower.c_str());
}

static const std::wstring* Lookup(const char* name)
{
    if (!name) return nullptr;
    std::string n = name;
    for (auto& c : n) { c = (char)tolower((unsigned char)c); if (c == '/') c = (char)0x5C; }
    std::lock_guard<std::mutex> l(g_mx);
    for (auto& r : g_redirect) {
        const std::string& k = r.first;
        if (n.size() < k.size() || n.compare(n.size() - k.size(), k.size(), k) != 0) continue;
        if (n.size() == k.size() || n[n.size() - k.size() - 1] == (char)0x5C) return &r.second;
    }
    return nullptr;
}

static HANDLE WINAPI Hook_CreateFileA(LPCSTR name, DWORD acc, DWORD share, LPSECURITY_ATTRIBUTES sa, DWORD disp, DWORD flags, HANDLE tmpl)
{
    const std::wstring* t = Lookup(name);
    // read-only opens (also GENERIC_READ|GENERIC_WRITE on an existing file without
    // truncation) are served from the cache; anything that would write goes through
    bool writes = disp == CREATE_ALWAYS || disp == TRUNCATE_EXISTING || disp == CREATE_NEW;
    if (g_cfg.fileLog && name && g_logged < 3000) {
        ++g_logged;
        Log("file: %s acc=0x%08lX share=%lu disp=%lu flags=0x%lX%s", name, acc, share, disp, flags, t ? (writes ? " (NOT redirected: write)" : " -> cache") : "");
    }
    if (t && !writes) {
        HANDLE h = CreateFileW(t->c_str(), acc & ~(DWORD)(GENERIC_WRITE | FILE_WRITE_DATA | FILE_APPEND_DATA),
                               share | FILE_SHARE_READ, sa, OPEN_EXISTING, flags, tmpl);
        if (h != INVALID_HANDLE_VALUE) return h;
        if (g_cfg.fileLog) Log("file: redirect open failed (%lu) for %s", GetLastError(), name);
    }
    return CreateFileA(name, acc, share, sa, disp, flags, tmpl);
}

static DWORD WINAPI Hook_GetFileAttributesA(LPCSTR name)
{
    if (const std::wstring* t = Lookup(name)) {
        DWORD a = GetFileAttributesW(t->c_str());
        if (a != INVALID_FILE_ATTRIBUTES) return a;
    }
    return GetFileAttributesA(name);
}

static BOOL WINAPI Hook_GetFileAttributesExA(LPCSTR name, GET_FILEEX_INFO_LEVELS lvl, LPVOID info)
{
    if (const std::wstring* t = Lookup(name))
        if (GetFileAttributesExW(t->c_str(), lvl, info)) return TRUE;
    return GetFileAttributesExA(name, lvl, info);
}

void Files_PatchModule(HMODULE mod)
{
    PatchIAT(mod, "kernel32.dll", "CreateFileA", (void*)Hook_CreateFileA);
    PatchIAT(mod, "kernel32.dll", "GetFileAttributesA", (void*)Hook_GetFileAttributesA);
    PatchIAT(mod, "kernel32.dll", "GetFileAttributesExA", (void*)Hook_GetFileAttributesExA);
}
