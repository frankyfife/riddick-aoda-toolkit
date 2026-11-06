// Diagnostics ([Debug] TextLog=1): log every distinct string that goes through
// the 2D line drawer CRC_Util2D::vtable[0xf0] (ten arguments, __thiscall,
// ret 0x28: arg0, font, UTF-16 string, x, y, flags, colour, outline, shadow,
// scale) with its scale and the caller's address. Used to find which caller
// draws the menu button hints and at which size.
#include "common.h"
#include <set>
#include <tuple>
#include <mutex>
#include <string.h>

struct ModRange { uintptr_t lo, hi; char name[32]; };
static ModRange g_mods[4];
static int g_nmods;
static std::set<std::pair<std::wstring, uint32_t>> g_seen;
static std::mutex g_mx;

static void Describe(uint32_t addr, char* out, size_t n)
{
    for (int i = 0; i < g_nmods; ++i)
        if (addr >= g_mods[i].lo && addr < g_mods[i].hi) {
            sprintf_s(out, n, "%s+0x%X (0x%08X at pref. base)", g_mods[i].name, (unsigned)(addr - g_mods[i].lo),
                      (unsigned)(addr - g_mods[i].lo + 0x10000000));
            return;
        }
    sprintf_s(out, n, "0x%08X", addr);
}

static bool CopyText(const wchar_t* s, std::wstring& out)
{
    __try {
        for (int i = 0; i < 200 && s[i]; ++i) out.push_back(s[i]);
        return true;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}

// ---- textured rectangles: CRC_Util2D::vtable[0x84](target, const float rect[4], color*, ...)
static std::set<std::tuple<uint32_t, int, int, int, int>> g_rects;
static void* g_rectOrig[8];
static void* g_rectVtbl[8];
static int g_nrect;

static bool ReadRect(uint32_t p, float* r)
{
    __try { memcpy(r, (const void*)(uintptr_t)p, 16); return true; } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}

static void __stdcall OnRect(uint32_t* sp)
{
    float r[4];
    if (!ReadRect(sp[2], r)) return;
    auto key = std::make_tuple(sp[0], (int)r[0], (int)r[1], (int)r[2], (int)r[3]);
    {
        std::lock_guard<std::mutex> l(g_mx);
        if (g_rects.size() > 400 || !g_rects.insert(key).second) return;
    }
    char caller[96]; Describe(sp[0], caller, sizeof(caller));
    Log("rect: %.1f,%.1f - %.1f,%.1f (%.1f x %.1f) from %s", r[0], r[1], r[2], r[3], r[2] - r[0], r[3] - r[1], caller);
}

static void HookRect(void* self)
{
    void** vt = *(void***)self;
    std::lock_guard<std::mutex> l(g_mx);
    for (int i = 0; i < g_nrect; ++i) if (g_rectVtbl[i] == vt) return;
    if (g_nrect >= 8) return;
    void* orig = vt[0x84 / 4];
    uint8_t* stub = (uint8_t*)VirtualAlloc(nullptr, 32, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!stub) return;
    uint8_t* p = stub;
    *p++ = 0x60; *p++ = 0x8D; *p++ = 0x44; *p++ = 0x24; *p++ = 0x20; *p++ = 0x50;   // pushad; lea eax,[esp+0x20]; push eax
    *p++ = 0xB8; void* fn = (void*)&OnRect; memcpy(p, &fn, 4); p += 4; *p++ = 0xFF; *p++ = 0xD0;
    *p++ = 0x61; *p++ = 0x68; memcpy(p, &orig, 4); p += 4; *p++ = 0xC3;              // popad; push orig; ret
    void* s = stub;
    WriteMem(&vt[0x84 / 4], &s, 4);
    g_rectVtbl[g_nrect] = vt; g_rectOrig[g_nrect] = orig; ++g_nrect;
    Log("textlog: rect drawer of vtable %p hooked", vt);
}

static void __stdcall OnLine(uint32_t* sp, void* self)
{
    if (self) HookRect(self);
    std::wstring text;
    if (!sp[3] || !CopyText((const wchar_t*)(uintptr_t)sp[3], text) || text.empty()) return;
    {
        std::lock_guard<std::mutex> l(g_mx);
        if (g_seen.size() > 600 || !g_seen.insert({ text, sp[0] }).second) return;
    }
    char utf8[700] = {};
    WideCharToMultiByte(CP_UTF8, 0, text.c_str(), -1, utf8, sizeof(utf8) - 1, nullptr, nullptr);
    char caller[96]; Describe(sp[0], caller, sizeof(caller));
    float x, y, scale;
    memcpy(&x, &sp[4], 4); memcpy(&y, &sp[5], 4); memcpy(&scale, &sp[10], 4);
    Log("text: \"%s\" x=%.1f y=%.1f scale=%.3f flags=0x%X font=%08X this=%p from %s", utf8, x, y, scale,
        (unsigned)sp[6], (unsigned)sp[2], self, caller);
}

void TextLog_Patch(HMODULE m, const char* name)
{
    if (g_nmods < 4) {
        ModRange& r = g_mods[g_nmods++];
        r.lo = (uintptr_t)m; r.hi = r.lo + ImageSize(m);
        strncpy_s(r.name, name, _TRUNCATE);
    }
    auto hits = FindAllHex(m, "8b 44 24 18 f3 0f 10 44 24 28");
    if (hits.size() != 1) { Log("textlog: %s: line drawer %u matches", name, (unsigned)hits.size()); return; }
    uint8_t* at = hits[0];
    uint8_t* stub = (uint8_t*)VirtualAlloc(nullptr, 64, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!stub) return;
    uint8_t* p = stub;
    auto put = [&](std::initializer_list<uint8_t> b) { for (uint8_t c : b) *p++ = c; };
    put({ 0x60 });                               // pushad
    put({ 0x8D, 0x44, 0x24, 0x20 });             // lea eax,[esp+0x20]  (esp at entry)
    put({ 0x51, 0x50 });                         // push ecx (this); push eax (sp)
    *p++ = 0xB8; void* fn = (void*)&OnLine; memcpy(p, &fn, 4); p += 4;
    put({ 0xFF, 0xD0 });                         // call eax
    put({ 0x61 });                               // popad
    memcpy(p, at, 10); p += 10;                  // the replaced instructions
    *p++ = 0xE9; int32_t r = (int32_t)((at + 10) - (p + 4)); memcpy(p, &r, 4); p += 4;
    uint8_t j[10] = { 0xE9 };
    r = (int32_t)(stub - (at + 5)); memcpy(j + 1, &r, 4);
    memset(j + 5, 0x90, 5);
    WriteMem(at, j, 10);
    Log("textlog: %s: line drawer hooked at %p", name, at);
}
