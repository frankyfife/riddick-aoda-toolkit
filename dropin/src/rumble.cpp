// Controller vibration (port of ../rumble/RiddickRumble.c).
//
// The PC port ships the complete envelope data (Content\Feedback\feedback.xrg,
// byte-identical to the Xbox 360 file) but no output stage: GameClasses' rumble
// dispatcher maps id 1..29 to an effect name and discards it, and XInputSetState
// appears in no PC binary. glyphs.cpp hooks the dispatcher behind its
// GAME_VIBRATION check and calls Rumble_Play(id); a 60 Hz worker mixes up to
// eight running envelopes into the two motors.
#include "common.h"
#include <string.h>

namespace {

const int kMaxEnv = 96, kMaxPt = 32, kMaxVoice = 8, kTickMs = 16;

struct Point { float t, f; };
struct Envelope { char name[64]; int n[2]; Point p[2][kMaxPt]; float length; };
struct XVib { WORD left, right; };
typedef DWORD(WINAPI* PfnSet)(DWORD, XVib*);
typedef DWORD(WINAPI* PfnGet)(DWORD, void*);

Envelope g_env[kMaxEnv];
int g_nenv;
struct { int idx; DWORD start; } g_voice[kMaxVoice];
CRITICAL_SECTION g_cs;
PfnSet g_set;
PfnGet g_get;
DWORD g_pad;
volatile LONG g_stop, g_ready;
HANDLE g_thread;

// the 29 ids of the dispatcher, in the order of its jump table (id 1 = index 0)
const char* const kIds[29] = {
    "DamageBreath1", "DamageBreath2", "DamageBreath3", "DamageFrom_ShotGun01",
    "DamageFrom_ASR01", "CS1", "CS2", "CS3", "DamageFrom_Fist01",
    "DamageFrom_Fist02", "Grab_Response01", "Fist_Right01", "Fist_Right02",
    "Explo_01_2sek", "ShotGun_Shot01", "ShotGun_Shot02", "ASR_Shot01",
    "ASR_Shot02", "SMG_Shot01", "SMG_Shot02", "Fist_Left01", "Fist_Left02",
    "UpperCut01", "Damage_Light01", "Damage_Light02", "Damage_Medium01",
    "Damage_Medium02", "Damage_High01", "Damage_High02"
};

void ParseFeedback()
{
    std::vector<uint8_t> raw;
    if (!ReadFileAll(std::wstring(g_gameRoot) + L"\\Content\\Feedback\\feedback.xrg", raw)) { Log("rumble: feedback.xrg not found"); return; }
    std::string text(raw.begin(), raw.end());
    const char* buf = text.c_str();
    const char* end = buf + text.size();
    const char* s = buf;
    // the head comment lists all names - skip it
    if (const char* c = strstr(buf, "*/")) if (c - buf < 8192) s = c + 2;
    while (s < end && g_nenv < kMaxEnv) {
        const char* p = strstr(s, "*ENVELOPE");
        if (!p) break;
        s = p + 9;
        while (s < end && (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')) ++s;
        if (*s != '"') continue;
        ++s;
        const char* q = strchr(s, '"');
        if (!q) break;
        Envelope* e = &g_env[g_nenv];
        memset(e, 0, sizeof(*e));
        size_t len = std::min<size_t>(63, q - s);
        memcpy(e->name, s, len);
        s = q + 1;
        const char* limit = strstr(s, "*ENVELOPE");
        if (!limit) limit = end;
        const char* cur = s;
        int ch = -1;
        while (cur < limit) {
            const char* c = strstr(cur, "*CHANNEL");
            const char* pt = strstr(cur, "*POINT");
            if (c && c < limit && (!pt || c < pt)) {
                ch = atoi(c + 8);
                if (ch < 0 || ch > 1) ch = -1;
                cur = c + 8;
                continue;
            }
            if (pt && pt < limit) {
                const char* tt = strstr(pt, "*TIME");
                const char* ff = strstr(pt, "*FORCE");
                if (tt && ff && tt < limit && ff < limit && ch >= 0 && e->n[ch] < kMaxPt) {
                    Point* P = &e->p[ch][e->n[ch]++];
                    P->t = (float)atof(tt + 5);
                    P->f = (float)atof(ff + 6);
                    e->length = std::max(e->length, P->t);
                }
                cur = pt + 6;
                continue;
            }
            break;
        }
        ++g_nenv;
        s = limit;
    }
    Log("rumble: %d envelopes loaded from feedback.xrg", g_nenv);
}

int Find(const char* name)
{
    for (int i = 0; i < g_nenv; ++i) if (!_stricmp(g_env[i].name, name)) return i;
    return -1;
}

float Force(const Envelope* e, int ch, float t)
{
    int n = e->n[ch];
    const Point* p = e->p[ch];
    if (n <= 0) return 0;
    if (t <= p[0].t) return p[0].f;
    for (int i = 1; i < n; ++i)
        if (t <= p[i].t) {
            float d = p[i].t - p[i - 1].t;
            if (d <= 0) return p[i].f;
            return p[i - 1].f + (p[i].f - p[i - 1].f) * (t - p[i - 1].t) / d;
        }
    return 0;
}

void FindPad()
{
    static int reported = -2;
    if (!g_get) return;
    int found = -1;
    for (DWORD i = 0; i < 4; ++i) {
        uint8_t st[32] = {};
        if (g_get(i, st) == ERROR_SUCCESS) { found = (int)i; break; }
    }
    if (found >= 0) g_pad = (DWORD)found;
    if (found == reported) return;
    reported = found;
    if (found >= 0) Log("rumble: controller in slot %d", found);
    else Log("rumble: no controller connected (slot 0 is driven anyway)");
}

DWORD WINAPI Worker(LPVOID)
{
    // set-up runs here, outside the loader lock (LoadLibrary of xinput)
    ParseFeedback();
    for (const char* dll : { "xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll" }) {
        HMODULE h = LoadLibraryA(dll);
        if (!h) continue;
        g_set = (PfnSet)GetProcAddress(h, "XInputSetState");
        g_get = (PfnGet)GetProcAddress(h, "XInputGetState");
        if (g_set) { Log("rumble: XInputSetState from %s", dll); break; }
        FreeLibrary(h);
    }
    if (!g_set) Log("rumble: no XInputSetState - vibration stays silent");
    FindPad();
    InterlockedExchange(&g_ready, 1);

    XVib last = { 0xFFFF, 0xFFFF };
    int sinceSearch = 0;
    while (!g_stop) {
        DWORD now = GetTickCount();
        if (++sinceSearch >= 1000 / kTickMs) { sinceSearch = 0; FindPad(); }
        float l = 0, r = 0;
        EnterCriticalSection(&g_cs);
        for (auto& v : g_voice) {
            if (v.idx < 0) continue;
            const Envelope* e = &g_env[v.idx];
            float t = (float)(long)(now - v.start) / 1000.0f;
            if (t > e->length) { v.idx = -1; continue; }
            l = std::max(l, Force(e, 0, t));
            r = std::max(r, Force(e, 1, t));
        }
        LeaveCriticalSection(&g_cs);
        if (g_cfg.rumbleSwap) std::swap(l, r);
        l = std::min(1.0f, std::max(0.0f, l * g_cfg.rumbleGain));
        r = std::min(1.0f, std::max(0.0f, r * g_cfg.rumbleGain));
        XVib v = { (WORD)(l * 65535.0f), (WORD)(r * 65535.0f) };
        if (g_set && (v.left != last.left || v.right != last.right)) { g_set(g_pad, &v); last = v; }
        Sleep(kTickMs);
    }
    return 0;
}

} // namespace

void Rumble_Init()
{
    if (!g_cfg.rumble) return;
    InitializeCriticalSection(&g_cs);
    for (auto& v : g_voice) v.idx = -1;
    g_thread = CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
}

void __stdcall Rumble_Play(int id)
{
    if (id < 1 || id > 29 || !g_ready) return;
    const char* name = kIds[id - 1];
    int idx = Find(name);
    static int logged;
    if (g_cfg.rumbleLog || logged < 10) { ++logged; Log("rumble: id %2d %-22s%s", id, name, idx < 0 ? " (no envelope)" : ""); }
    if (idx < 0) return;
    EnterCriticalSection(&g_cs);
    int slot = -1;
    for (int i = 0; i < kMaxVoice; ++i) {
        if (g_voice[i].idx == idx) { slot = i; break; }   // restart a running effect
        if (g_voice[i].idx < 0 && slot < 0) slot = i;
    }
    if (slot < 0) slot = 0;
    g_voice[slot].idx = idx;
    g_voice[slot].start = GetTickCount();
    LeaveCriticalSection(&g_cs);
}

void Rumble_Shutdown(bool callXInput)
{
    g_stop = 1;
    if (callXInput && g_set) { XVib off = { 0, 0 }; g_set(g_pad, &off); }
}
