// Info and help texts name the controller button, on any profile.
//
// The options registry holds two bindings per action - ACTION_<NAME> (keyboard
// and mouse) and ACTION_<NAME>2 (pad). When a profile is loaded the exe walks the
// list of binding names, reads each code (CRegistry::GetValuei) and its key name
// (CScanKey::GetLocalizedKeyName) and sets the keys up; "press <key>" in the info
// texts then shows what came first, the keyboard slot. None of the hooks in
// glyphs.cpp sees that: they sit in GameClasses / GameWorld, this is the exe.
// (The profile this fix was developed on had its two slots exchanged by hand
// long ago, which is why it went unnoticed until a new profile was made.)
//
// So at that one call site the two slots answer for each other whenever the
// second holds a pad code and the first does not. Both keys are set up as before,
// only their order is the pad's; the profile file and the options pages keep
// reading the registry as it is.
//
// The exe's import table cannot be read (copy protection), so GetValuei itself
// is detoured in MSystem, as helpkey.cpp does with CConsole::ProcessKey.
//
// [Debug] KeyTextLog=1 additionally logs which code asks for which binding and
// where a key code is turned into its name: each distinct (call site, name or
// code, result) once. Only binding names (ACTION_...) and key codes are noted,
// nothing that is typed.
#include "common.h"
#include <intrin.h>
#include <set>
#include <string.h>

namespace {

typedef void* (__cdecl* PfnKeyName)(void* ret, int code);
typedef long (__fastcall* PfnGet2)(void* reg, void* edx, const char* name, long def);
typedef long (__fastcall* PfnGet3)(void* reg, void* edx, const char* name, long def, int flag);

PfnKeyName g_locName;
PfnGet2 g_get2;
PfnGet3 g_get3;
uint8_t *g_msBase, *g_msEnd;
uint8_t* g_setupSite;                // return address of the exe's binding walk
const uint32_t kSetupRva = 0x2E074;  // DarkAthena.exe 27ADAC97C5F59612 (GOG GMC-1.161)
CRITICAL_SECTION g_lock;
std::set<uint64_t>* g_seen;
const size_t kMaxLines = 800;

uint32_t Hash(const char* s)
{
    uint32_t h = 2166136261u;
    for (; *s; ++s) h = (h ^ (uint8_t)*s) * 16777619u;
    return h;
}

// what = 'L' GetLocalizedKeyName, '2' / '3' the GetValuei overloads
void Note(char what, void* caller, const char* name, long value)
{
    if (name && strncmp(name, "ACTION_", 7) != 0) return;
    uint64_t key = ((uint64_t)(uintptr_t)caller << 32) ^ ((uint64_t)(uint8_t)what << 56) ^ (name ? Hash(name) : 0)
                 ^ ((uint64_t)(uint32_t)value * 0x9E3779B1u);
    EnterCriticalSection(&g_lock);
    bool fresh = g_seen->size() < kMaxLines && g_seen->insert(key).second;
    LeaveCriticalSection(&g_lock);
    if (!fresh) return;
    HMODULE m = nullptr;
    char mod[MAX_PATH] = "?";
    uint32_t rva = (uint32_t)(uintptr_t)caller;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)caller, &m) && m) {
        char path[MAX_PATH];
        if (GetModuleFileNameA(m, path, MAX_PATH)) { const char* b = strrchr(path, '\\'); strcpy_s(mod, b ? b + 1 : path); }
        rva = (uint32_t)((uint8_t*)caller - (uint8_t*)m);
    }
    if (name) Log("keytext: %s+0x%X GetValuei(%s) = %ld (0x%02lX)", mod, rva, name, value, value);
    else Log("keytext: %s+0x%X GetLocalizedKeyName(0x%02lX)", mod, rva, value);
}

// GetValuei(name) is a three-instruction wrapper inside MSystem around
// GetValuei(name, 0): seen from there, the interesting caller is one frame up -
// [ret into the wrapper][name][0][ret of the wrapper].
void* RealCaller(void** frame)
{
    auto ret = (uint8_t*)frame[0];
    if (ret >= g_msBase && ret < g_msEnd && ret[0] == 0xC2 && ret[1] == 0x04) return frame[3];
    return ret;
}

bool IsPad(long code) { return code >= 0x80 && code <= 0xB3; }

// the other slot's name: "ACTION_USE" <-> "ACTION_USE2"
bool OtherSlot(const char* name, char* out, size_t cap, bool& second)
{
    size_t n = strlen(name);
    if (n < 8 || n + 2 > cap || strncmp(name, "ACTION_", 7) != 0) return false;
    memcpy(out, name, n + 1);
    second = name[n - 1] == '2';
    if (second) out[n - 1] = 0;
    else { out[n] = '2'; out[n + 1] = 0; }
    return true;
}

void* __cdecl Hook_LocName(void* ret, int code)
{
    Note('L', _ReturnAddress(), nullptr, code);
    return g_locName(ret, code);
}
long __fastcall Hook_Get2(void* reg, void* edx, const char* name, long def)
{
    void* caller = RealCaller((void**)_AddressOfReturnAddress());
    long v = g_get2(reg, edx, name, def);
    if (caller == g_setupSite && g_cfg.textButtons && name) {
        char other[64];
        bool second;
        if (OtherSlot(name, other, sizeof(other), second)) {
            long o = g_get2(reg, edx, other, 0);
            long first = second ? o : v, pad = second ? v : o;
            if (IsPad(pad) && !IsPad(first)) {
                static int logged;
                if (logged < 3) { ++logged; Log("keytext: %s answers with %s (0x%02lX instead of 0x%02lX) - info texts name the pad", name, other, o, v); }
                v = o;
            }
        }
    }
    if (g_cfg.keyTextLog && name) Note('2', caller, name, v);
    return v;
}
long __fastcall Hook_Get3(void* reg, void* edx, const char* name, long def, int flag)
{
    void* caller = _ReturnAddress();
    long v = g_get3(reg, edx, name, def, flag);
    if (name) Note('3', caller, name, v);
    return v;
}

// 5-byte jmp over the first instructions (n bytes, position independent), the
// replaced bytes run from a trampoline
template <class T> bool Detour(HMODULE ms, const char* exp, const uint8_t* head, size_t n, void* hook, T& orig)
{
    auto fn = (uint8_t*)GetProcAddress(ms, exp);
    if (!fn || !InModule(ms, fn, n) || memcmp(fn, head, n) != 0) { Log("keytext: %s not recognised", exp); return false; }
    auto t = (uint8_t*)VirtualAlloc(nullptr, 32, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!t) return false;
    memcpy(t, head, n);
    t[n] = 0xE9;
    int32_t back = (int32_t)((uintptr_t)(fn + n) - (uintptr_t)(t + n + 5));
    memcpy(t + n + 1, &back, 4);
    FlushInstructionCache(GetCurrentProcess(), t, n + 5);
    uint8_t j[8];
    memset(j, 0x90, sizeof(j));
    j[0] = 0xE9;
    int32_t r = (int32_t)((uintptr_t)hook - ((uintptr_t)fn + 5));
    memcpy(j + 1, &r, 4);
    orig = (T)t;                       // set before the jmp exists: the next call may come at once
    if (!WriteMem(fn, j, n)) { orig = nullptr; return false; }
    return true;
}

} // namespace

void KeyText_Hook(HMODULE ms)
{
    bool swap = g_cfg.textButtons && g_cfg.xboxPrompts && g_cfg.colorIcons;   // the pad's key names are icons only then
    if (!swap) g_cfg.textButtons = 0;
    if ((!swap && !g_cfg.keyTextLog) || g_seen) return;
    g_setupSite = (uint8_t*)GetModuleHandleA(nullptr) + kSetupRva;
    InitializeCriticalSection(&g_lock);
    g_seen = new std::set<uint64_t>();
    g_msBase = (uint8_t*)ms; g_msEnd = g_msBase + ImageSize(ms);
    static const uint8_t kLoc[6] = { 0x81, 0xEC, 0x04, 0x02, 0x00, 0x00 };           // sub esp,0x204
    static const uint8_t kGet[6] = { 0x56, 0x57, 0x8B, 0x7C, 0x24, 0x0C };           // push esi; push edi; mov edi,[esp+0xc]
    bool ok = Detour(ms, "?GetValuei@CRegistry@@QBEJPBDJ@Z", kGet, 6, (void*)Hook_Get2, g_get2);
    if (swap) Log(ok ? "keytext: info texts name the pad buttons (binding walk at DarkAthena.exe+0x%X)"
                     : "keytext: CRegistry::GetValuei not recognised - info texts keep naming the keyboard", kSetupRva);
    if (!g_cfg.keyTextLog) return;
    Detour(ms, "?GetLocalizedKeyName@CScanKey@@SA?AVCStr@@H@Z", kLoc, 6, (void*)Hook_LocName, g_locName);
    Detour(ms, "?GetValuei@CRegistry@@QAEJPBDJH@Z", kGet, 6, (void*)Hook_Get3, g_get3);
    Log("keytext: logging GetLocalizedKeyName %s, GetValuei %s / %s", g_locName ? "yes" : "no", g_get2 ? "yes" : "no", g_get3 ? "yes" : "no");
}
