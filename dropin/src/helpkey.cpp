// The help button really opens the help (issue #2).
//
// HelpButton used to pick the glyph only; the help itself stayed on F1. The
// obvious cure - rebinding the button to cmd(helpbutton) while the help bar is
// up and back afterwards - is what ../patches/patch_gamepad_glyphs.py prepared
// and never switched on. It cannot be made reliable, for reasons that sit in
// MSystem's CConsole:
//   * a scan code holds one CKeyBind per device with three scripts (press,
//     release, repeat); binding the code again stops the old entry and
//     overwrites all three (Parser_BindDeviceScanCode), so "help and reload on
//     B" can only be a swap with a restore
//   * bindscan() always writes the any-device entry (-1), while FindBinding
//     prefers a device-specific one - the swap may never be looked at
//   * the restore has to guess what the button did before
// So no binding is touched here. CConsole::ProcessKey is where every key event
// is matched against the bindings; it is exported by name. While the help bar
// is being drawn, a press of the help button is taken there and answered with
// cmd(helpbutton) - the script F1 carries - instead of the button's own
// binding. With no help bar on screen the button does what it always did.
//
//   CScanKey +4   bits 0..8 scan code, 9..13 shift state, 14 repeat, 15 released
//   CConsole +0x5C  mode, 2 = keys go to the bindings (else: the console line)
#include "common.h"
#include <string.h>

namespace {

const DWORD kBarWindowMs = 300;      // the bar counts as visible this long after its last frame

typedef bool (__fastcall* PfnProcessKey)(uint8_t* con, void* edx, const uint8_t* key, int mode);
typedef void (__cdecl* PfnExec)();

volatile LONG g_barTick;             // GetTickCount() of the last frame that drew the help bar
volatile LONG g_barSeen;
PfnProcessKey g_origProcessKey;      // trampoline: the six replaced bytes + jmp back
PfnExec g_execHelp;                  // ConExecute("cmd(helpbutton)"), built once GameClasses is known
bool g_held;                         // the current press went to the help - its release follows it

const char kConName[] = "ConExecute";
const char kHelpScript[] = "cmd(helpbutton)";
const char kConExecuteImp[] = "?ConExecuteImp@@YA_NVCStr@@PBDH@Z";            // bool (CStr, const char*, int)
const char kProcessKey[] = "?ProcessKey@CConsole@@QAE_NABVCScanKey@@H@Z";    // bool (const CScanKey&, int)

bool BarVisible()
{
    return g_barSeen && GetTickCount() - (DWORD)g_barTick < kBarWindowMs;
}

void RunHelp()
{
    __try { g_execHelp(); }
    __except (EXCEPTION_EXECUTE_HANDLER) { Log("help: WARNING exception 0x%08lX in cmd(helpbutton)", GetExceptionCode()); }
}

// true = the event is ours, the bindings never see it
bool TakeKey(const uint8_t* con, const uint8_t* key, int mode)
{
    uint32_t k = *(const uint32_t*)(key + 4);
    int code = (int)(k & 0x1FF);
    bool up = (k >> 15) & 1, repeat = (k >> 14) & 1;
    if (!mode) mode = *(const int*)(con + 0x5C);
    // pad codes only (sticks 0x80.., buttons 0xA0.., d-pad 0xB0..): never the keyboard,
    // a log that ends up in a bug report must not carry what somebody typed
    if (g_cfg.padLog && code >= 0x80 && code <= 0xBF && !repeat)
        Log("pad: code 0x%02X device %u %s, mode %d", code, (unsigned)*(const uint16_t*)(key + 0x12), up ? "up" : "down", mode);
    if (code != g_cfg.helpButton || !g_execHelp) return false;
    if (up) { bool taken = g_held; g_held = false; return taken; }
    if (repeat) return g_held;
    g_held = mode == 2 && BarVisible();
    static int taken, passed;
    if (!g_held) {
        // the first few are logged without PadLog, so a plain log already says why nothing happened
        if (passed < 10) {
            ++passed;
            if (!g_barSeen) Log("help: button 0x%02X pressed, no help bar drawn so far (mode %d) - left to its binding", code, mode);
            else Log("help: button 0x%02X pressed, help bar last drawn %lu ms ago (mode %d) - left to its binding",
                     code, GetTickCount() - (DWORD)g_barTick, mode);
        }
        return false;
    }
    if (taken < 20) { ++taken; Log("help: button 0x%02X pressed while the help bar is on screen -> cmd(helpbutton)", code); }
    RunHelp();
    return true;
}

bool __fastcall Hook_ProcessKey(uint8_t* con, void* edx, const uint8_t* key, int mode)
{
    if (TakeKey(con, key, mode)) return false;      // what the binding path returns as well
    return g_origProcessKey(con, edx, key, mode);
}

void Rel32(uint8_t* at, const void* target)
{
    int32_t r = (int32_t)((uintptr_t)target - ((uintptr_t)at + 4));
    memcpy(at, &r, 4);
}

// The engine starts a script with
//     push 0 / push "ConExecute" / sub esp,8 / mov ecx,esp
//     push <script> / call CStr::CStr(const char*) / call ConExecuteImp / add esp,0x10
// The constructor is not exported, every module carries its own copy. It is taken
// from the call sites of that shape whose second call ends in MSystem's
// ConExecuteImp; all of them have to agree.
uint8_t* FindCStrCtor(HMODULE gc, const uint8_t* conExecuteImp)
{
    auto names = FindAll(gc, (const uint8_t*)kConName, sizeof(kConName));
    uint8_t* ctor = nullptr;
    int sites = 0;
    for (uint8_t* name : names) {
        if (name[-1] != 0) continue;                                   // tail of a longer string
        uint8_t pat[10] = { 0x68, 0, 0, 0, 0, 0x83, 0xEC, 0x08, 0x8B, 0xCC };
        uint32_t va = (uint32_t)(uintptr_t)name;
        memcpy(pat + 1, &va, 4);
        for (uint8_t* p : FindAll(gc, pat, sizeof(pat))) {
            for (uint8_t* q = p + 10; q <= p + 18; ++q) {              // an EH state store may sit in between
                if (!InModule(gc, q, 18)) break;
                if (q[0] != 0x68 || q[5] != 0xE8 || q[10] != 0xE8 || q[15] != 0x83 || q[16] != 0xC4 || q[17] != 0x10) continue;
                uint8_t* thunk = RelTarget(q + 10);
                if (!InModule(gc, thunk, 6) || thunk[0] != 0xFF || thunk[1] != 0x25) continue;
                auto slot = (uint8_t**)(uintptr_t)*(uint32_t*)(thunk + 2);
                if (!InModule(gc, slot, 4) || *slot != conExecuteImp) continue;
                uint8_t* c = RelTarget(q + 5);
                if (!InModule(gc, c)) continue;
                if (ctor && ctor != c) { Log("help: script call sites disagree about the CStr constructor"); return nullptr; }
                ctor = c;
                ++sites;
                break;
            }
        }
    }
    if (ctor) Log("help: CStr constructor at %p (%d script call sites)", ctor, sites);
    return ctor;
}

} // namespace

// called from the glyph cave each time the help bar is drawn
void __stdcall HelpKey_BarDrawn()
{
    g_barTick = (LONG)GetTickCount();
    if (!g_barSeen) { g_barSeen = 1; Log("help: help bar on screen for the first time"); }
}

// MSystem: detour CConsole::ProcessKey. Its callers reach it through the export
// (the exe's import table is not readable, the copy protection wraps it), so the
// function itself is patched. Its first three instructions - push ebp /
// mov ebp,esp / and esp,-0x40 - are six position-independent bytes.
void HelpKey_HookConsole(HMODULE ms)
{
    if (!g_cfg.helpActive || !g_cfg.xboxPrompts || g_origProcessKey) return;
    auto fn = (uint8_t*)GetProcAddress(ms, kProcessKey);
    static const uint8_t kHead[6] = { 0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xC0 };
    if (!fn || !InModule(ms, fn, 6) || memcmp(fn, kHead, 6) != 0) {
        Log("help: CConsole::ProcessKey not recognised - the help stays on F1");
        return;
    }
    auto t = (uint8_t*)VirtualAlloc(nullptr, 32, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!t) return;
    memcpy(t, kHead, 6);
    t[6] = 0xE9; Rel32(t + 7, fn + 6);
    FlushInstructionCache(GetCurrentProcess(), t, 11);
    g_origProcessKey = (PfnProcessKey)t;
    uint8_t j[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    int32_t r = (int32_t)((uintptr_t)&Hook_ProcessKey - ((uintptr_t)fn + 5));
    memcpy(j + 1, &r, 4);
    if (!WriteMem(fn, j, 6)) { g_origProcessKey = nullptr; Log("help: CConsole::ProcessKey could not be patched"); return; }
    Log("help: CConsole::ProcessKey hooked at %p", fn);
}

// GameClasses: build the script call. Until this has run the hook passes every key on.
void HelpKey_Attach(HMODULE gc)
{
    if (g_execHelp) return;
    HMODULE ms = GetModuleHandleA("MSystem.dll");
    if (ms && !g_origProcessKey) HelpKey_HookConsole(ms);      // MSystem was mapped before we could see it
    if (!g_origProcessKey) return;
    auto exec = ms ? (uint8_t*)GetProcAddress(ms, kConExecuteImp) : nullptr;
    uint8_t* ctor = exec ? FindCStrCtor(gc, exec) : nullptr;
    if (!ctor) { Log("help: script engine not found - the help stays on F1"); return; }
    auto s = (uint8_t*)VirtualAlloc(nullptr, 64, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!s) return;
    uint8_t* p = s;
    auto put = [&](std::initializer_list<uint8_t> b) { for (uint8_t c : b) *p++ = c; };
    auto imm = [&](const void* v) { memcpy(p, &v, 4); p += 4; };
    put({ 0x6A, 0x00 });                         // push 0
    put({ 0x68 }); imm(kConName);                // push "ConExecute"
    put({ 0x83, 0xEC, 0x08, 0x8B, 0xCC });       // sub esp,8 ; mov ecx,esp
    put({ 0x68 }); imm(kHelpScript);             // push "cmd(helpbutton)"
    put({ 0xE8 }); Rel32(p, ctor); p += 4;       // call CStr::CStr(const char*)   (ret 4)
    put({ 0xE8 }); Rel32(p, exec); p += 4;       // call ConExecuteImp             (it destroys the CStr)
    put({ 0x83, 0xC4, 0x10, 0xC3 });             // add esp,0x10 ; ret
    FlushInstructionCache(GetCurrentProcess(), s, p - s);
    g_execHelp = (PfnExec)s;
    Log("help: button 0x%02X opens the help while the help bar is on screen (ConExecuteImp at %p)", g_cfg.helpButton, exec);
}
