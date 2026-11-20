// [Gameplay] UnlockAll=1: every extra is unlocked (for testing).
//
// The extras menu lives in GameWorld. When it is created it reads the profile
// value GAME_EXTRACONTENTKEY - a list of numbers separated by ',' or '+', one
// per collected key, 1..128 - into a 128-bit set at this+0x149C; an entry of
// ExtraContent\Offline01\info.xrg is shown once its "*key" is in the set (the
// shipped list uses 1..122, key 0 is always free):
//     lea  ecx,[esi+0x149c]
//     call ParseKeys
//     mov  ecx,esi                      <- hooked: all 128 bits are set first
//     mov  dword [esi+0x1498],-1
//     call ...
// The profile is not written here. The game itself stores the set again the
// next time a key is collected, and from then on that profile keeps them.
//
// The levels are handled in datagen.cpp: the chapter list of the game shows the
// chapter saves a profile has (files EFBB_nn / AODA_nn), which cannot be made up;
// the developers' own map list is still in the menu file and only needs its
// cheat() gate removed.
#include "common.h"
#include <string.h>

void Unlock_Patch(HMODULE m, const char* name)
{
    if (!g_cfg.unlockAll) return;
    auto hits = FindAllHex(m, "8d 8e 9c 14 00 00 e8 ?? ?? ?? ?? 8b ce c7 86 98 14 00 00 ff ff ff ff e8");
    if (hits.empty()) {
        if (!_strnicmp(name, "GameWorld", 9)) Log("unlock: %s: extras key reader not found - the extras stay locked", name);
        return;
    }
    if (hits.size() != 1) { Log("unlock: %s: extras key reader %u matches", name, (unsigned)hits.size()); return; }
    uint8_t* at = hits[0] + 11;                      // mov ecx,esi ; mov dword [esi+0x1498],-1   (12 bytes)
    uint8_t* stub = (uint8_t*)VirtualAlloc(nullptr, 64, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!stub) return;
    uint8_t* p = stub;
    for (uint32_t off = 0x149C; off < 0x14AC; off += 4) {    // or dword [esi+off],-1
        *p++ = 0x83; *p++ = 0x8E; memcpy(p, &off, 4); p += 4; *p++ = 0xFF;
    }
    memcpy(p, at, 12); p += 12;                      // the replaced instructions
    *p++ = 0xE9;
    int32_t back = (int32_t)((uintptr_t)(at + 12) - ((uintptr_t)p + 4));
    memcpy(p, &back, 4); p += 4;
    FlushInstructionCache(GetCurrentProcess(), stub, p - stub);
    uint8_t j[12];
    memset(j, 0x90, sizeof(j));
    j[0] = 0xE9;
    int32_t r = (int32_t)((uintptr_t)stub - ((uintptr_t)at + 5));
    memcpy(j + 1, &r, 4);
    if (!WriteMem(at, j, sizeof(j))) { Log("unlock: %s: could not be patched", name); return; }
    Log("unlock: %s: all extras unlocked", name);
}
