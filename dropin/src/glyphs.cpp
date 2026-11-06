// Xbox 360 button glyphs in the key hints of GameClasses / GameWorld.
//
// In-memory port of ../patches/patch_gamepad_glyphs.py with the options the
// launcher uses (--prefer-pad --help-button <cfg> --no-inline --no-skip-fix
// --no-help-rebind). CRC_Util2D is linked into both DLLs, so both get patched.
// Every entry point is found by byte pattern; if anything does not match, the
// module is left completely untouched.
//
//   h1/h3  chain resolvers: pad code 0x80..0xB3 -> icon instead of key-cap text
//   h2     chain-1 drawer: icon index >= 0x80 -> texture name via code2tex
//   pp1/2  ask ACTION_<NAME>2 (the pad slot) first
//   g1/d2  menu path: remember the pad code, draw it as texture
//   g2     text-block resolver: try the other slot when the first is no pad code
//   hb     help bar draws the help button's glyph instead of "F1"
//   rb     rumble dispatcher -> Rumble_Play(id) (the PC port discards the effect)
#include "common.h"
#include <map>
#include <math.h>
#include <string.h>

volatile uint32_t g_helpBarFlag;   // hb -> h2: the next chain-1 icon belongs to the help bar

namespace {

struct Asm {
    uint8_t* base;
    std::vector<uint8_t> buf;
    std::map<std::string, uint32_t> lab;
    struct Fix { size_t off; std::string l; uint32_t abs; bool absolute = false; };
    std::vector<Fix> fix;
    struct Diff { size_t off; std::string t, a; };
    std::vector<Diff> diffs;

    explicit Asm(uint8_t* b) : base(b) {}
    uint32_t here() const { return (uint32_t)(uintptr_t)base + (uint32_t)buf.size(); }
    void label(const std::string& n) { lab[n] = here(); }
    void hex(const char* h)
    {
        for (const char* p = h; *p;) {
            while (*p == ' ') ++p;
            if (!*p) break;
            char b[3] = { p[0], p[1], 0 }; buf.push_back((uint8_t)strtoul(b, nullptr, 16)); p += 2;
        }
    }
    void bytes(const void* p, size_t n) { buf.insert(buf.end(), (const uint8_t*)p, (const uint8_t*)p + n); }
    void u32(uint32_t v) { bytes(&v, 4); }
    void str(const char* s) { bytes(s, strlen(s) + 1); }
    // labels are strings, absolute targets are uint8_t* - kept apart on purpose,
    // a const char* would otherwise convert to a pointer target
    void relL(const std::string& l) { fix.push_back({ buf.size(), l, 0 }); u32(0); }
    void absL(const std::string& l) { fix.push_back({ buf.size(), l, 0, true }); u32(0); }   // absolute address of a label
    void relA(const uint8_t* abs) { fix.push_back({ buf.size(), "", (uint32_t)(uintptr_t)abs }); u32(0); }
    void jmp(const std::string& l) { buf.push_back(0xE9); relL(l); }
    void jmp(const char* l) { jmp(std::string(l)); }
    void jmp(const uint8_t* p) { buf.push_back(0xE9); relA(p); }
    void call(const uint8_t* p) { buf.push_back(0xE8); relA(p); }
    void jcc(uint8_t cc, const std::string& l) { buf.push_back(0x0F); buf.push_back(cc); relL(l); }
    void jcc(uint8_t cc, const char* l) { jcc(cc, std::string(l)); }
    void jcc(uint8_t cc, const uint8_t* p) { buf.push_back(0x0F); buf.push_back(cc); relA(p); }
    void disp(const std::string& target, const std::string& anchor) { diffs.push_back({ buf.size(), target, anchor }); u32(0); }
    bool resolve()
    {
        for (auto& f : fix) {
            uint32_t dst = f.l.empty() ? f.abs : lab.count(f.l) ? lab[f.l] : 0;
            if (!dst) { Log("glyphs: unresolved label %s", f.l.c_str()); return false; }
            if (f.absolute) { memcpy(&buf[f.off], &dst, 4); continue; }
            int32_t r = (int32_t)(dst - ((uint32_t)(uintptr_t)base + (uint32_t)f.off + 4));
            memcpy(&buf[f.off], &r, 4);
        }
        for (auto& d : diffs) {
            if (!lab.count(d.t) || !lab.count(d.a)) { Log("glyphs: unresolved disp %s", d.t.c_str()); return false; }
            int32_t v = (int32_t)(lab[d.t] - lab[d.a]);
            memcpy(&buf[d.off], &v, 4);
        }
        return true;
    }
};

const uint8_t JB = 0x82, JAE = 0x83, JZ = 0x84, JNE = 0x85;

// code-to-texture byte table, entries for 0xA0..0xAB
// 1=LT 2=RT 3=A 4=B 5=X 6=Y 7=LB 8=RB 9=Back 10=Start 11=stick click 16=none
const uint8_t kTableOrig[12] = { 3, 4, 5, 6, 7, 8, 9, 10, 11, 11, 16, 16 };
const uint8_t kTableNew[12]  = { 3, 4, 5, 6, 10, 9, 11, 11, 7, 8, 1, 2 };

struct Sites {
    uint8_t *code2tex = nullptr, *table = nullptr, *jt = nullptr, *getvaluei = nullptr;
    uint8_t *h1 = nullptr, *h1_back = nullptr, *h1_notext = nullptr, *pp1 = nullptr; uint32_t pp1_noff = 0;
    uint8_t *h3 = nullptr, *h3_back = nullptr, *h3_notext = nullptr, *pp2 = nullptr; uint32_t pp2_noff = 0;
    uint8_t *h2 = nullptr, *h2_back = nullptr, *h2_noicon = nullptr, *h2_settex = nullptr;
    uint8_t *g1 = nullptr, *g1_back = nullptr;
    uint8_t *d2 = nullptr, *d2_next = nullptr, *d2_je = nullptr;
    uint8_t *g2_call = nullptr;
    uint8_t *hb = nullptr, *hb_back = nullptr, *hb_f1 = nullptr;
    uint8_t *dup = nullptr;
    uint8_t *rb = nullptr, *rb_back = nullptr;
};

bool Locate(HMODULE m, Sites& s)
{
    auto one = [&](const char* what, const char* hex, uint8_t*& out) {
        auto h = FindAllHex(m, hex);
        if (h.size() != 1) { Log("glyphs: %s: %u matches", what, (unsigned)h.size()); return false; }
        out = h[0];
        return true;
    };
    if (!one("code2tex", "8b 44 24 04 83 c0 80 83 f8 33", s.code2tex)) return false;
    s.table = (uint8_t*)(uintptr_t)*(uint32_t*)(s.code2tex + 15);
    s.jt = (uint8_t*)(uintptr_t)*(uint32_t*)(s.code2tex + 0x16);
    if (!InModule(m, s.table + 0x20, 12) || !InModule(m, s.jt, 17 * 4)) { Log("glyphs: tables outside module"); return false; }

    auto res = FindAllHex(m, "3d f0 00 00 00 75 08 8d 7b 01");
    if (res.size() != 2) { Log("glyphs: resolvers: %u matches", (unsigned)res.size()); return false; }
    for (uint8_t* va : res) {
        uint32_t noff = *(uint32_t*)(va - 15 + 3);
        s.getvaluei = RelTarget(va - 5);
        if (noff == 0x144) { s.h1 = va; s.h1_back = va + 5; s.h1_notext = RelTarget(va + 10); s.pp1 = va - 15; s.pp1_noff = noff; }
        else               { s.h3 = va; s.h3_back = va + 5; s.h3_notext = RelTarget(va + 10); s.pp2 = va - 15; s.pp2_noff = noff; }
    }
    if (!s.h1 || !s.h3) { Log("glyphs: resolver assignment failed"); return false; }

    if (!one("drawer switch", "83 f8 03 dd d8 0f 84", s.h2)) return false;
    s.h2_back = s.h2 + 5;
    s.h2_noicon = RelTarget(s.h2 + 23, 2);
    s.h2_settex = s.h2 + 29 + 2 + 2 + 5;

    if (!one("name resolver", "8b 8c 24 1c 01 00 00 51 8b c8 e8 ?? ?? ?? ?? 8b b4 24 18 01 00 00 50 56 e8", s.g1)) return false;
    s.g1_back = s.g1 + 15;

    for (uint8_t* c : FindAllHex(m, "83 ff 01 74 05"))
        if (c > s.h3 && c - s.h3 < 0x800 && (!s.d2 || c < s.d2)) s.d2 = c;
    if (!s.d2) { Log("glyphs: drawer-2 switch not found"); return false; }
    s.d2_next = s.d2 + 5; s.d2_je = s.d2 + 10;

    int g2 = 0;
    for (uint8_t* c : FindAllHex(m, "ff d0 50 8b ce e8 ?? ?? ?? ?? 85 c0 74"))
        if (RelTarget(c + 5) == s.getvaluei) { s.g2_call = c + 5; ++g2; }
    if (g2 != 1) { Log("glyphs: text-path query: %d matches", g2); return false; }

    // optional sites (GameClasses only)
    auto hb = FindAllHex(m, "6a 00 83 ec 08 8b 16 8b 92 0c 01 00 00");
    if (hb.size() > 1) { Log("glyphs: help bar ambiguous"); return false; }
    if (hb.size() == 1) { s.hb = hb[0]; s.hb_back = hb[0] + 5; }
    static const uint8_t f1[] = { 0xA7, 'L', 'G', 'A', 'M', 'E', 'M', 'S', 'G', '_', 'H', 'E', 'L', 'P', 0, 0, 'F', '1', 0 };
    auto f1h = FindAll(m, f1, sizeof(f1));
    if (f1h.size() == 1) s.hb_f1 = f1h[0] + 16;
    static const char dup[] = "GUI_Button_DUP";
    auto duph = FindAll(m, (const uint8_t*)dup, sizeof(dup));
    if (duph.size() == 1) s.dup = duph[0] + 13;
    auto rb = FindAllHex(m, "8b 4d 08 8d 41 ff 83 f8 1c");
    if (rb.size() == 1) { s.rb = rb[0]; s.rb_back = rb[0] + 9; }
    return true;
}

// copies the action name (ecx) to a 0x40-byte stack buffer (ebx) and appends '2'
void CopyPadName(Asm& a, const std::string& t)
{
    a.hex("83 ec 40 8b dc 33 d2");                         // sub esp,0x40; mov ebx,esp; xor edx,edx
    a.label("cp" + t);
    a.hex("8a 04 11 88 04 13 42 84 c0"); a.jcc(JZ, "ce" + t);
    a.hex("83 fa 30"); a.jcc(JB, "cp" + t);
    a.hex("c6 04 13 00 42");
    a.label("ce" + t);
    a.hex("c6 44 13 ff 32 c6 04 13 00");                   // "...2\0"
}

bool BuildCave(Asm& a, const Sites& s, bool rumble)
{
    // h1 - chain-1 resolver
    a.label("h1");
    a.hex("3d 80 00 00 00"); a.jcc(JB, "h1_orig");
    a.hex("3d b4 00 00 00"); a.jcc(JAE, "h1_orig");
    a.hex("8b f8");                                        // mov edi,eax
    a.jmp(s.h1_notext);
    a.label("h1_orig");
    a.hex("3d f0 00 00 00"); a.jmp(s.h1_back);

    // h2 - chain-1 drawer
    a.label("h2");
    a.hex("dd d8");                                        // fstp st(0)
    a.hex("3d 80 00 00 00"); a.jcc(JAE, "h2_have");
    a.hex("51 52");
    a.hex("e8 00 00 00 00"); a.label("h2p"); a.hex("59");
    a.hex("8b 91"); a.disp("gcode", "h2p");               // mov edx,[ecx+gcode]
    a.hex("85 d2"); a.jcc(JZ, "h2_no");
    a.hex("c7 81"); a.disp("gcode", "h2p"); a.u32(0);
    a.hex("8b c2 5a 59");
    a.jmp("h2_have");
    a.label("h2_no"); a.hex("5a 59"); a.jmp("h2_orig");
    a.label("h2_have");
    if (g_cfg.hintSize > 0) {
        // Help bar only ("HILFE" + help button, icon right of the label; dialog hints
        // put the icon left of the label and stay as they are). The hb stub raises
        // g_helpBarFlag right before it calls this drawer. Icon position: x [esp+0x78],
        // y [esp+0x98], height [esp+0xa8] (rect 0x1024AC15ff). The gap to the label is
        // ~0.7 icon heights - move the icon left by 0.37 of its height.
        uint32_t flag = (uint32_t)(uintptr_t)&g_helpBarFlag;
        a.hex("83 3d"); a.u32(flag); a.hex("00");           // cmp dword [flag],0
        a.jcc(JZ, "h2_nohb");
        a.hex("c7 05"); a.u32(flag); a.u32(0);              // mov dword [flag],0
        a.hex("3d"); a.u32((uint32_t)g_cfg.helpButton);     // cmp eax,<help code>
        a.jcc(JNE, "h2_nohb");
        a.hex("d9 84 24 a8 00 00 00");                     // fld   dword [esp+0xa8]  icon height
        a.hex("d8 0d"); a.absL("hgap");                    // fmul  dword [hgap]
        a.hex("d8 6c 24 78");                              // fsubr dword [esp+0x78]  x - shift
        a.hex("d9 5c 24 78");                              // fstp  dword [esp+0x78]
        a.label("h2_nohb");
    }
    a.hex("50"); a.call(s.code2tex); a.hex("83 c4 04");
    a.hex("85 c0"); a.jcc(JZ, "h2_none");
    a.hex("50"); a.jmp(s.h2_settex);
    a.label("h2_none"); a.jmp(s.h2_noicon);
    a.label("h2_orig"); a.hex("83 f8 03"); a.jmp(s.h2_back);

    // h3 - chain-2 resolver
    a.label("h3");
    a.hex("3d 80 00 00 00"); a.jcc(JB, "h3_orig");
    a.hex("3d b4 00 00 00"); a.jcc(JAE, "h3_orig");
    a.hex("50 50"); a.call(s.code2tex); a.hex("83 c4 04");
    a.hex("85 c0"); a.jcc(JZ, "h3_restore");
    a.hex("50 8b cd 8b 55 00 ff 52 68");                   // SetTexture(this)
    a.hex("58 bf 03 00 00 00");                            // pop eax; mov edi,3
    a.jmp(s.h3_notext);
    a.label("h3_restore"); a.hex("58");
    a.label("h3_orig"); a.hex("3d f0 00 00 00"); a.jmp(s.h3_back);

    // pp1/pp2 - prefer the pad slot ACTION_<NAME>2
    for (int k = 1; k <= 2; ++k) {
        std::string t = std::to_string(k);
        uint32_t noff = (k == 1 ? s.pp1_noff : s.pp2_noff) + 8;
        a.label("pp" + t);
        a.hex("53 56 8b f0");                              // push ebx,esi; mov esi,eax
        a.hex("8b 8c 24"); a.u32(noff);
        CopyPadName(a, t);
        a.hex("53 8b ce"); a.call(s.getvaluei); a.hex("83 c4 40");
        a.hex("3d 80 00 00 00"); a.jcc(JB, "pl" + t);
        a.hex("3d b4 00 00 00"); a.jcc(JB, "pd" + t);
        a.label("pl" + t);
        a.hex("8b 8c 24"); a.u32(noff);
        a.hex("51 8b ce"); a.call(s.getvaluei);
        a.label("pd" + t);
        a.hex("5e 5b");
        a.jmp(k == 1 ? s.h1 : s.h3);
    }

    // g1 - menu name resolver: pad slot first, remember the code in gcode
    {
        uint32_t noff = 0x11c + 8;
        a.label("g1");
        a.hex("53 56 8b f0");
        a.hex("8b 8c 24"); a.u32(noff);
        CopyPadName(a, "g");
        a.hex("53 8b ce"); a.call(s.getvaluei); a.hex("83 c4 40");
        a.hex("3d 80 00 00 00"); a.jcc(JB, "gpl");
        a.hex("3d b4 00 00 00"); a.jcc(JB, "grec");
        a.label("gpl");
        a.hex("8b 8c 24"); a.u32(noff);
        a.hex("51 8b ce"); a.call(s.getvaluei);
        a.label("grec");
        a.hex("51 52");
        a.hex("8b d0 81 fa 80 00 00 00"); a.jcc(JB, "gz");
        a.hex("81 fa b4 00 00 00"); a.jcc(JB, "gs");
        a.label("gz"); a.hex("33 d2");
        a.label("gs");
        a.hex("e8 00 00 00 00"); a.label("g1p"); a.hex("59");
        a.hex("89 91"); a.disp("gcode", "g1p");           // mov [ecx+gcode],edx
        a.hex("5a 59 5e 5b");
        a.jmp(s.g1_back);
    }

    // d2 - chain-2 drawer switch: a remembered code becomes the glyph texture
    a.label("d2");
    a.hex("50 51 52");
    a.hex("e8 00 00 00 00"); a.label("d2p"); a.hex("59");
    a.hex("8b 91"); a.disp("gcode", "d2p");
    a.hex("85 d2"); a.jcc(JZ, "d2_out");
    a.hex("c7 81"); a.disp("gcode", "d2p"); a.u32(0);
    a.hex("52"); a.call(s.code2tex); a.hex("83 c4 04");
    a.hex("85 c0"); a.jcc(JZ, "d2_out");
    a.hex("50 8b ce 8b 16 ff 52 68");                      // SetTexture(esi)
    a.hex("5a 59 58");
    a.hex("bf 03 00 00 00");                               // mov edi,3
    a.jmp(s.d2_next);
    a.label("d2_out");
    a.hex("5a 59 58");
    a.hex("83 ff 01"); a.jcc(JZ, s.d2_je);
    a.jmp(s.d2_next);

    // g2 - replacement for GetValuei in the text-block resolver (__thiscall, ret 4)
    a.label("g2");
    a.hex("53 56 57");
    a.hex("8b f1");
    a.hex("8b 5c 24 10");
    a.hex("53 8b ce"); a.call(s.getvaluei);
    a.hex("8b f8");
    a.hex("3d 80 00 00 00"); a.jcc(JB, "g2_try");
    a.hex("3d b4 00 00 00"); a.jcc(JB, "g2_done");
    a.label("g2_try");
    a.hex("83 ec 40 8b cc 33 d2");
    a.label("g2_cp");
    a.hex("8a 04 13 88 04 11 42 84 c0"); a.jcc(JZ, "g2_cpe");
    a.hex("83 fa 30"); a.jcc(JB, "g2_cp");
    a.hex("c6 04 11 00 42");
    a.label("g2_cpe");
    a.hex("80 7c 11 fe 32"); a.jcc(JNE, "g2_app");          // ends in '2'?
    a.hex("c6 44 11 fe 00"); a.jmp("g2_q");                 // strip it
    a.label("g2_app");
    a.hex("c6 44 11 ff 32 c6 04 11 00");                   // append '2'
    a.label("g2_q");
    a.hex("51 8b ce"); a.call(s.getvaluei); a.hex("83 c4 40");
    a.hex("3d 80 00 00 00"); a.jcc(JB, "g2_keep");
    a.hex("3d b4 00 00 00"); a.jcc(JB, "g2_done");
    a.label("g2_keep"); a.hex("8b c7");
    a.label("g2_done");
    a.hex("5f 5e 5b c2 04 00");

    // hb - help bar: icon index = pad code of the help button
    if (s.hb) {
        a.label("hb");
        if (g_cfg.hintSize > 0) { a.hex("c7 05"); a.u32((uint32_t)(uintptr_t)&g_helpBarFlag); a.u32(1); }   // mov dword [flag],1
        a.hex("68"); a.u32((uint32_t)g_cfg.helpButton);
        a.hex("83 ec 08");
        a.jmp(s.hb_back);
    }

    // own texture names for the stick clicks (L3 and R3 share GUI_Button_360_C)
    for (const char* lc : { "lc", "rc" }) {
        std::string l = lc;
        a.label("tex_" + l);
        a.hex("e8 00 00 00 00"); a.label(l + "p"); a.hex("58");
        a.hex("05"); a.disp("s_" + l, l + "p");
        a.hex("c3");
    }
    a.label("s_lc"); a.str("GUI_Button_LC");
    a.label("s_rc"); a.str("GUI_Button_RC");

    // rb - rumble: the dispatcher gets its id 1..29 in [ebp+8]; hooked behind the
    // GAME_VIBRATION check, so the menu option keeps working
    if (rumble && s.rb) {
        a.label("rb");
        a.hex("60 9c");                                    // pushad; pushfd
        a.hex("8b 4d 08 51");                              // push id
        a.hex("b8"); a.u32((uint32_t)(uintptr_t)&Rumble_Play);
        a.hex("ff d0");                                    // call eax (stdcall)
        a.hex("9d 61");
        a.hex("8b 4d 08 8d 41 ff 83 f8 1c");                // replaced instructions
        a.jmp(s.rb_back);
    }

    a.label("rlname"); a.str("ACTION_HELP");   // unused, keeps the layout identical to the Python cave
    a.label("gcode"); a.u32(0);
    if (g_cfg.hintSize > 0) { float g = 0.37f; a.label("hgap"); a.bytes(&g, 4); }

    return a.resolve();
}

void JmpAt(uint8_t* at, uint32_t to, size_t n)
{
    uint8_t b[16]; memset(b, 0x90, sizeof(b));
    b[0] = 0xE9;
    int32_t r = (int32_t)(to - ((uint32_t)(uintptr_t)at + 5));
    memcpy(b + 1, &r, 4);
    WriteMem(at, b, n);
}

} // namespace

// The menu hint loop (*BUTTON_DESCRIPTOR, CubeWnd.xrg; linked into GameClasses
// and GameWorld) draws each icon as a fixed quad x..x+32 / y..y+32 with
// CRC_Util2D::vtable[0x84]. Texture coordinates come from the texture origin
// (+0xF4/+0xF8, vtable[0x70]) and texture scale (+0xFC/+0x100, vtable[0x74]):
//     u = (px - origin.x) * scale.x / texture width        (rect draw, 0x103F1E62)
// The loop sets the scale to 1.0 - one texel per unit. On the inventory/info-box
// overlay the canvas is stretched (CRC_Util2D +0x158/+0x15C = 0.703 x 1.0, logged
// in game), so the 32-unit icon comes out 1.42x too wide. There the quad becomes
// 32 * 0.703 units wide and the texture x scale 32 / width, so the whole texture
// lands on the narrower quad: round, not cropped.
//   mov eax,[esp+0x18] ; lea ecx,[edi+0x20] (y+32) ; add eax,0x20 (x+32)
static int __stdcall HintIconWidth(uint8_t* util)
{
    float sx = 0, sy = 0;
    __try { memcpy(&sx, util + 0x158, 4); memcpy(&sy, util + 0x15C, 4); }
    __except (EXCEPTION_EXECUTE_HANDLER) { return 32; }
    if (!(sx > 0.01f && sy > 0.01f && sx < 100 && sy < 100) || fabsf(sx - sy) < 0.01f) return 32;
    int w = std::min(32, std::max(12, (int)lroundf(32.0f * sx / sy)));
    float tex = 32.0f / (float)w;
    __try { memcpy(util + 0xFC, &tex, 4); } __except (EXCEPTION_EXECUTE_HANDLER) { return 32; }
    static int logged;
    if (logged < 4) { ++logged; Log("glyphs: hint icon on canvas %.3f x %.3f -> quad width %d, texture scale %.3f", sx, sy, w, tex); }
    return w;
}

static void HintIconAspect(HMODULE m, const char* name)
{
    auto hits = FindAllHex(m, "8b 44 24 18 8d 4f 20 83 c0 20 3b f9");
    if (hits.size() != 1) { Log("glyphs: %s: hint icon quad %u matches", name, (unsigned)hits.size()); return; }
    uint8_t* site = hits[0] + 4;
    uint8_t* stub = (uint8_t*)VirtualAlloc(nullptr, 64, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!stub) return;
    uint8_t* p = stub;
    auto put = [&](std::initializer_list<uint8_t> b) { for (uint8_t c : b) *p++ = c; };
    put({ 0x8D, 0x4F, 0x20 });                   // lea ecx,[edi+0x20]   (y1, unchanged)
    put({ 0x50, 0x51, 0x56 });                   // push eax (x); push ecx; push esi (CRC_Util2D)
    *p++ = 0xB8; void* fn = (void*)&HintIconWidth; memcpy(p, &fn, 4); p += 4;
    put({ 0xFF, 0xD0 });                         // call eax  -> eax = width
    put({ 0x89, 0xC2, 0x59, 0x58, 0x01, 0xD0 });  // mov edx,eax; pop ecx; pop eax; add eax,edx
    *p++ = 0xE9; int32_t r = (int32_t)((site + 6) - (p + 4)); memcpy(p, &r, 4); p += 4;
    uint8_t j[6] = { 0xE9, 0, 0, 0, 0, 0x90 };
    r = (int32_t)(stub - (site + 5)); memcpy(j + 1, &r, 4);
    WriteMem(site, j, 6);
    Log("glyphs: %s: hint icons keep their aspect on stretched canvases", name);
}

uint8_t* g_lastCave;        // for the self test
size_t g_lastCaveSize;

void Glyphs_Patch(HMODULE m, const char* name)
{
    if (!g_cfg.xboxPrompts && !(g_cfg.rumble && !_strnicmp(name, "GameClasses", 11))) return;
    Sites s;
    if (!Locate(m, s)) { Log("glyphs: %s not recognised - left alone", name); return; }

    bool prompts = g_cfg.xboxPrompts != 0;
    if (prompts) {
        uint8_t* t = s.table + 0x20;
        if (memcmp(t, kTableOrig, 12) != 0 && memcmp(t, kTableNew, 12) != 0) {
            Log("glyphs: %s: code table unexpected - left alone", name);
            return;
        }
    }

    uint8_t* cave = (uint8_t*)VirtualAlloc(nullptr, 0x2000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!cave) return;
    Asm a(cave);
    if (!BuildCave(a, s, g_cfg.rumble != 0) || a.buf.size() > 0x2000) { Log("glyphs: cave build failed"); return; }
    memcpy(cave, a.buf.data(), a.buf.size());
    FlushInstructionCache(GetCurrentProcess(), cave, a.buf.size());
    g_lastCave = cave; g_lastCaveSize = a.buf.size();

    if (prompts) {
        WriteMem(s.table + 0x20, kTableNew, 12);
        JmpAt(s.h1, a.lab["h1"], 5);
        JmpAt(s.h2, a.lab["h2"], 5);
        JmpAt(s.h3, a.lab["h3"], 5);
        JmpAt(s.g1, a.lab["g1"], 7);
        JmpAt(s.d2, a.lab["d2"], 5);
        JmpAt(s.pp1, a.lab["pp1"], 7);
        JmpAt(s.pp2, a.lab["pp2"], 7);
        if (s.hb) JmpAt(s.hb, a.lab["hb"], 5);
        if (s.hb_f1) { uint8_t z = 0; WriteMem(s.hb_f1, &z, 1); }           // "F1" -> the glyph replaces it
        if (s.dup) { uint8_t p = 'p'; WriteMem(s.dup, &p, 1); }             // GUI_Button_DUP -> DUp (archive name)
        // slot 11 (L3) -> LC, the catch-all slot 16 -> RC, and R3 (0xA7) to slot 16
        uint32_t lc = a.lab["tex_lc"], rc = a.lab["tex_rc"];
        WriteMem(s.jt + 11 * 4, &lc, 4);
        WriteMem(s.jt + 16 * 4, &rc, 4);
        uint8_t sixteen = 16; WriteMem(s.table + 0x27, &sixteen, 1);
        // g2 stays a call so its ret 4 fits
        uint8_t c[5] = { 0xE8 };
        int32_t r = (int32_t)(a.lab["g2"] - ((uint32_t)(uintptr_t)s.g2_call + 5));
        memcpy(c + 1, &r, 4);
        WriteMem(s.g2_call, c, 5);
    }
    if (g_cfg.rumble && s.rb) JmpAt(s.rb, a.lab["rb"], 9);
    if (prompts && g_cfg.hintSize > 0) HintIconAspect(m, name);
    Log("glyphs: %s patched (prompts=%d help bar=%d rumble=%d, cave %u bytes at %p)",
        name, prompts, s.hb != nullptr, g_cfg.rumble && s.rb, (unsigned)a.buf.size(), cave);
}
