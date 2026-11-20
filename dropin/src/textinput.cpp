// X deletes the last character on the name entry screen (CubeMenu_TextInput).
//
// The on-screen keyboard has no key for it. The window's own handler deletes on
// two scan codes only:
//     cmp eax,0xE6 / je del      GUI_BUTTON2 - what X is on the console
//     cmp eax,0x0E / je del      BACKSPACE
//     xor al,al ...              not ours
// On the PC a pad button that is no GUI key arrives under its own code
// (JOY_BUTTON_02 = 0xA2; the leaderboard window of the same module asks for
// 0xE7 or 0xA3 for Y, and the menu file doubles its GUI_BUTTON2 accelerators
// with JOY_BUTTON_02). So a typing mistake could only be corrected on the
// keyboard. Both compares are replaced by a call that also accepts 0xA2.
#include "common.h"
#include <string.h>

namespace {

bool __stdcall IsDeleteKey(int code)
{
    // pad and GUI codes only - what is typed on the keyboard stays out of the log
    if (g_cfg.padLog && ((code >= 0x80 && code <= 0xBF) || (code >= 0xE0 && code <= 0xEF)))
        Log("pad: text input received code 0x%02X", code);
    return code == 0xE6 || code == 0x0E || code == 0xA2;
}

void Rel32(uint8_t* at, const void* target)
{
    int32_t r = (int32_t)((uintptr_t)target - ((uintptr_t)at + 4));
    memcpy(at, &r, 4);
}

} // namespace

void TextInput_Patch(HMODULE m, const char* name)
{
    if (!g_cfg.padDelete) return;
    auto hits = FindAllHex(m, "3d e6 00 00 00 74 18 83 f8 0e 74 13 32 c0");
    if (hits.size() != 1) {
        Log("textinput: %s: delete key test %u matches - X does not delete there", name, (unsigned)hits.size());
        return;
    }
    uint8_t* at = hits[0];
    uint8_t* stub = (uint8_t*)VirtualAlloc(nullptr, 32, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!stub) return;
    uint8_t* p = stub;
    *p++ = 0x51;                                         // push ecx        (this)
    *p++ = 0x50;                                         // push eax        (scan code)
    *p++ = 0xE8; Rel32(p, &IsDeleteKey); p += 4;         // call IsDeleteKey
    *p++ = 0x59;                                         // pop ecx
    *p++ = 0x84; *p++ = 0xC0;                            // test al,al
    *p++ = 0x0F; *p++ = 0x85; Rel32(p, at + 0x1F); p += 4;   // jnz  delete the last character
    *p++ = 0xE9; Rel32(p, at + 0x0C); p += 4;            // jmp  "not ours" (xor al,al)
    FlushInstructionCache(GetCurrentProcess(), stub, p - stub);
    uint8_t j[12];
    memset(j, 0x90, sizeof(j));
    j[0] = 0xE9;
    int32_t r = (int32_t)((uintptr_t)stub - ((uintptr_t)at + 5));
    memcpy(j + 1, &r, 4);
    if (!WriteMem(at, j, sizeof(j))) { Log("textinput: %s: could not be patched", name); return; }
    Log("textinput: %s: X deletes the last character on the name entry screen", name);
}
