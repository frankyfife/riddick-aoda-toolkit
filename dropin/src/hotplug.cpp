// A controller that is switched on after the game has started.
//
// MSystem builds its input devices once: CInputContext_DInput::DI_CreateDevices
// lets DirectInput enumerate what is attached and creates a pad object for every
// device that is an XInput one. A pad that is off at that moment gets no object,
// and nothing looks again - it stays dead until the game is restarted.
//
// The engine can rebuild the list, though. Its per-frame update begins with
//     hwnd = <main window>
//     if (m_hWnd != hwnd) DI_CreateDevices(hwnd);      m_hWnd = this+0xAE0
// (that is how it follows a re-created window), and DI_DestroyDevices resets the
// device and port counters. So Update is detoured: about once a second it counts
// the XInput pads, and when one has appeared that the game has no object for
// (this+0xAF4 = XInput pads set up), m_hWnd is cleared - the update that follows
// rebuilds the devices itself, on its own thread, with its own code.
#include "common.h"
#include <string.h>

namespace {

typedef void (__fastcall* PfnUpdate)(uint8_t* ctx, void* edx);
typedef DWORD (WINAPI* PfnGetState)(DWORD, void*);

PfnUpdate g_origUpdate;
PfnGetState g_getState;

const char kUpdate[] = "?Update@CInputContext_DInput@@UAEXXZ";
const DWORD kPollMs = 1500;

int ConnectedPads()
{
    static bool tried;
    if (!tried) {
        tried = true;
        // the game's own choice first, so both count the same pads
        for (const char* dll : { "xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll" }) {
            HMODULE h = LoadLibraryA(dll);
            if (!h) continue;
            g_getState = (PfnGetState)GetProcAddress(h, "XInputGetState");
            if (g_getState) break;
            FreeLibrary(h);
        }
        if (!g_getState) Log("hotplug: no XInputGetState - a controller switched on later stays unseen");
    }
    if (!g_getState) return -1;
    int n = 0;
    for (DWORD i = 0; i < 4; ++i) {
        uint8_t st[32] = {};
        if (g_getState(i, st) == ERROR_SUCCESS) ++n;
    }
    return n;
}

void Watch(uint8_t* ctx)
{
    static DWORD next;
    static int last = -1;
    static bool pending;
    DWORD now = GetTickCount();
    if (next && (LONG)(now - next) < 0) return;
    next = now + kPollMs;
    if (!next) next = 1;
    int n = ConnectedPads();
    if (n < 0) return;
    int have = *(const int*)(ctx + 0xAF4);
    if (pending) {
        // one poll later, so DirectInput has the new device as well
        pending = false;
        if (n > have) {
            Log("hotplug: %d XInput controller(s), the game has %d - input devices are set up again", n, have);
            *(void**)(ctx + 0xAE0) = nullptr;
        }
    } else if (last < 0) {
        Log("hotplug: %d XInput controller(s) at start, the game set up %d", n, have);
        pending = n > have;
    } else if (n > last) {
        pending = true;
    }
    last = n;
}

void __fastcall Hook_Update(uint8_t* ctx, void* edx)
{
    g_origUpdate(ctx, edx);
    Watch(ctx);          // after it: the first update is the one that sets the devices up
}

} // namespace

void Hotplug_Hook(HMODULE ms)
{
    if (!g_cfg.hotplug || g_origUpdate) return;
    auto fn = (uint8_t*)GetProcAddress(ms, kUpdate);
    static const uint8_t kHead[5] = { 0x55, 0x8B, 0xEC, 0x6A, 0xFF };              // push ebp; mov ebp,esp; push -1
    static const uint8_t kTest[6] = { 0x39, 0xB3, 0xE0, 0x0A, 0x00, 0x00 };        // cmp [ebx+0xae0],esi
    bool known = fn && InModule(ms, fn, 0x100) && memcmp(fn, kHead, 5) == 0;
    if (known) {
        known = false;
        for (int i = 5; i < 0x100 - 6 && !known; ++i) known = memcmp(fn + i, kTest, 6) == 0;
    }
    if (!known) { Log("hotplug: CInputContext_DInput::Update not recognised - controllers are found at start only"); return; }
    auto t = (uint8_t*)VirtualAlloc(nullptr, 32, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!t) return;
    memcpy(t, kHead, 5);
    t[5] = 0xE9;
    int32_t back = (int32_t)((uintptr_t)(fn + 5) - (uintptr_t)(t + 10));
    memcpy(t + 6, &back, 4);
    FlushInstructionCache(GetCurrentProcess(), t, 10);
    g_origUpdate = (PfnUpdate)t;
    uint8_t j[5] = { 0xE9 };
    int32_t r = (int32_t)((uintptr_t)&Hook_Update - ((uintptr_t)fn + 5));
    memcpy(j + 1, &r, 4);
    if (!WriteMem(fn, j, 5)) { g_origUpdate = nullptr; Log("hotplug: Update could not be patched"); return; }
    Log("hotplug: watching for controllers that are switched on later");
}
