/* RiddickRumble.dll - der fehlende Ausgang fuer die Vibration.
 *
 * Warum es diese DLL gibt
 * -----------------------
 * Die PC-Fassung hat alles fuer Rumble ausser der Ausgabe:
 *   - Content\Feedback\feedback.xrg enthaelt 59 Huellkurven mit je zwei
 *     Kanaelen (die beiden Motoren), Zeit in Sekunden, Kraft 0..1.
 *     Die Datei ist bytegleich mit der der Xbox 360.
 *   - GameClasses hat einen Verteiler (0x102c5120), der eine Rumble-Kennung
 *     1..29 auf einen Effektnamen abbildet. Er prueft GAME_VIBRATION, baut
 *     den Namen in einen CStr - und wirft ihn weg. Ein ausgeweideter Rumpf.
 *   - MSystem loest aus xinput1_3.dll nur XInputGetState auf.
 *     XInputSetState kommt in keiner PC-Binaerdatei vor.
 * Die Xbox-360-Fassung importiert dagegen XamInputSetState (Ordinal 0x192
 * aus xam.xex) - dort laeuft es also ueber die Standardschnittstelle.
 *
 * Diese DLL liest dieselbe feedback.xrg, spielt die Huellkurve ab und
 * schickt die beiden Motorwerte an XInputSetState. Eingehaengt wird sie von
 * patch_gamepad_glyphs.py im Verteiler, direkt hinter der
 * GAME_VIBRATION-Pruefung - der Menuepunkt "Vibration" wirkt also weiter.
 *
 * Bauen: build.cmd   (MSVC, 32 Bit - das Spiel ist 32-bittig)
 */

#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <stdlib.h>

#define MAX_ENV     96      /* Huellkurven in feedback.xrg (dort sind es 59) */
#define MAX_PT      32      /* Punkte je Kanal (dort hoechstens 12)          */
#define MAX_VOICE    8      /* gleichzeitig klingende Effekte                */
#define TICK_MS     16      /* rund 60 Hz                                    */

typedef struct { float t, f; } Point;

typedef struct {
    char  name[64];
    int   n[2];
    Point p[2][MAX_PT];
    float dauer;
} Envelope;

typedef struct { WORD left, right; } XVib;
typedef DWORD (WINAPI *PfnSet)(DWORD, XVib *);
typedef DWORD (WINAPI *PfnGet)(DWORD, void *);

static Envelope g_env[MAX_ENV];
static int      g_nenv = 0;

static struct { int idx; DWORD start; } g_voice[MAX_VOICE];
static CRITICAL_SECTION g_cs;

static PfnSet   g_set = NULL;
static PfnGet   g_get = NULL;
static DWORD    g_pad = 0;
static volatile LONG g_stop = 0;
/* Wird erst gesetzt, wenn der Arbeitsfaden feedback.xrg gelesen und XInput
 * aufgeloest hat. Vorher darf niemand g_env anfassen. */
static volatile LONG g_bereit = 0;

static float    g_gain = 1.0f;        /* Gesamtstaerke                        */
static int      g_swap = 0;           /* Kanaele auf die Motoren tauschen     */
static int      g_log  = 1;
static char     g_logpfad[MAX_PATH];
static char     g_wurzel[MAX_PATH];   /* Spielwurzel (zwei Ebenen ueber exe)  */

/* Die 29 Kennungen des Verteilers, in genau der Reihenfolge der
 * Sprungtabelle bei GameClasses 0x102c554c. Kennung 1 ist Index 0. */
static const char *g_ids[29] = {
    "DamageBreath1", "DamageBreath2", "DamageBreath3", "DamageFrom_ShotGun01",
    "DamageFrom_ASR01", "CS1", "CS2", "CS3", "DamageFrom_Fist01",
    "DamageFrom_Fist02", "Grab_Response01", "Fist_Right01", "Fist_Right02",
    "Explo_01_2sek", "ShotGun_Shot01", "ShotGun_Shot02", "ASR_Shot01",
    "ASR_Shot02", "SMG_Shot01", "SMG_Shot02", "Fist_Left01", "Fist_Left02",
    "UpperCut01", "Damage_Light01", "Damage_Light02", "Damage_Medium01",
    "Damage_Medium02", "Damage_High01", "Damage_High02"
};

/* ------------------------------------------------------------- Protokoll */
static void plog(const char *fmt, ...)
{
    FILE *f;
    va_list ap;
    SYSTEMTIME st;

    if (!g_log || !g_logpfad[0]) return;
    f = fopen(g_logpfad, "a");
    if (!f) return;
    GetLocalTime(&st);
    fprintf(f, "%02d:%02d:%02d.%03d  ", st.wHour, st.wMinute, st.wSecond,
            st.wMilliseconds);
    va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fputc('\n', f);
    fclose(f);
}

/* ----------------------------------------------------------------- Pfade */
static void pfade(void)
{
    char exe[MAX_PATH];
    char *p;
    int i;

    GetModuleFileNameA(NULL, exe, MAX_PATH);
    /* Die exe liegt in System\Win32_x86\ - drei Trenner hoch ist die Wurzel */
    strcpy(g_wurzel, exe);
    for (i = 0; i < 3; i++) {
        p = strrchr(g_wurzel, 92);          /* Rueckstrich */
        if (p) *p = 0;
    }
    strcpy(g_logpfad, exe);
    p = strrchr(g_logpfad, 92);
    if (p) strcpy(p + 1, "RiddickRumble.log");
}

/* ------------------------------------------------- feedback.xrg einlesen */
static void parse_feedback(void)
{
    char pfad[MAX_PATH];
    HANDLE h;
    DWORD gr, gelesen = 0;
    char *buf, *s, *ende, *p;

    sprintf(pfad, "%s%cContent%cFeedback%cfeedback.xrg", g_wurzel, 92, 92, 92);
    h = CreateFileA(pfad, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        plog("feedback.xrg nicht gefunden: %s", pfad);
        return;
    }
    gr = GetFileSize(h, NULL);
    buf = (char *)malloc(gr + 1);
    if (!buf) { CloseHandle(h); return; }
    ReadFile(h, buf, gr, &gelesen, NULL);
    CloseHandle(h);
    buf[gelesen] = 0;

    s = buf;
    ende = buf + gelesen;

    /* Der Kopfkommentar zaehlt alle Namen auf - er darf nicht mitgelesen
     * werden, sonst haelt der Parser die Liste fuer Nutzdaten. */
    p = strstr(buf, "*/");
    if (p && (p - buf) < 8192) s = p + 2;

    while (s < ende && g_nenv < MAX_ENV) {
        Envelope *e;
        char *q, *grenze, *cur;
        int len, kanal = -1;

        p = strstr(s, "*ENVELOPE");
        if (!p) break;
        s = p + 9;
        while (s < ende && (*s == ' ' || *s == 9 || *s == 13 || *s == 10)) s++;
        if (*s != 34) continue;             /* Anfuehrungszeichen */
        s++;
        q = strchr(s, 34);
        if (!q) break;

        e = &g_env[g_nenv];
        memset(e, 0, sizeof(*e));
        len = (int)(q - s);
        if (len > 63) len = 63;
        memcpy(e->name, s, len);
        e->name[len] = 0;
        s = q + 1;

        grenze = strstr(s, "*ENVELOPE");
        if (!grenze) grenze = ende;
        cur = s;
        while (cur < grenze) {
            char *c  = strstr(cur, "*CHANNEL");
            char *pt = strstr(cur, "*POINT");
            if (c && c < grenze && (!pt || c < pt)) {
                kanal = atoi(c + 8);
                if (kanal < 0 || kanal > 1) kanal = -1;
                cur = c + 8;
                continue;
            }
            if (pt && pt < grenze) {
                char *tt = strstr(pt, "*TIME");
                char *ff = strstr(pt, "*FORCE");
                if (tt && ff && tt < grenze && ff < grenze && kanal >= 0
                        && e->n[kanal] < MAX_PT) {
                    Point *P = &e->p[kanal][e->n[kanal]++];
                    P->t = (float)atof(tt + 5);
                    P->f = (float)atof(ff + 6);
                    if (P->t > e->dauer) e->dauer = P->t;
                }
                cur = pt + 6;
                continue;
            }
            break;
        }
        g_nenv++;
        s = grenze;
    }
    free(buf);
    plog("feedback.xrg gelesen: %d Huellkurven", g_nenv);
}

static int finde(const char *name)
{
    int i;
    for (i = 0; i < g_nenv; i++)
        if (_stricmp(g_env[i].name, name) == 0) return i;
    return -1;
}

/* Kraft eines Kanals zum Zeitpunkt t, linear zwischen den Stuetzpunkten */
static float kraft(const Envelope *e, int kanal, float t)
{
    int i, n = e->n[kanal];
    const Point *p = e->p[kanal];

    if (n <= 0) return 0.0f;
    if (t <= p[0].t) return p[0].f;
    for (i = 1; i < n; i++) {
        if (t <= p[i].t) {
            float d = p[i].t - p[i - 1].t;
            if (d <= 0.0f) return p[i].f;
            return p[i - 1].f + (p[i].f - p[i - 1].f) * (t - p[i - 1].t) / d;
        }
    }
    return 0.0f;
}

/* --------------------------------------------------------------- Mischer */
static void suche_pad(void);
static void hole_xinput(void);
static void pfade(void);
static void lies_ini(void);

/* Der Arbeitsfaden richtet zuerst alles ein und mischt danach.
 *
 * Warum die Einrichtung nicht in DllMain steht: dort laeuft alles unter der
 * Ladesperre von Windows. Ein LoadLibraryA fuer xinput1_3.dll waere genau
 * die Verklemmung, vor der Microsoft warnt. Der Faden wird in DllMain nur
 * erzeugt; laufen tut er erst, wenn die Sperre wieder frei ist. */
static DWORD WINAPI arbeiter(LPVOID unbenutzt)
{
    XVib letzte;
    int seit_suche = 0;
    letzte.left = 0xFFFF;
    letzte.right = 0xFFFF;
    (void)unbenutzt;

    pfade();
    lies_ini();
    plog("---- RiddickRumble geladen ----");
    parse_feedback();
    hole_xinput();
    suche_pad();
    InterlockedExchange(&g_bereit, 1);

    for (;;) {
        DWORD jetzt;
        float l = 0.0f, r = 0.0f;
        int i;
        XVib v;

        if (g_stop) break;
        jetzt = GetTickCount();

        /* Der Controller ist beim Laden der DLL oft noch nicht da (oder wird
         * zwischendurch abgezogen). Einmal pro Sekunde neu suchen - oefter
         * waere schaedlich, XInputGetState auf einem leeren Steckplatz
         * kostet spuerbar Zeit. */
        if (++seit_suche >= 1000 / TICK_MS) {
            seit_suche = 0;
            suche_pad();
        }

        EnterCriticalSection(&g_cs);
        for (i = 0; i < MAX_VOICE; i++) {
            const Envelope *e;
            float t, a, b;
            if (g_voice[i].idx < 0) continue;
            e = &g_env[g_voice[i].idx];
            t = (float)((long)(jetzt - g_voice[i].start)) / 1000.0f;
            if (t > e->dauer) { g_voice[i].idx = -1; continue; }
            a = kraft(e, 0, t);
            b = kraft(e, 1, t);
            if (a > l) l = a;
            if (b > r) r = b;
        }
        LeaveCriticalSection(&g_cs);

        if (g_swap) { float x = l; l = r; r = x; }
        l *= g_gain;
        r *= g_gain;
        if (l < 0.0f) l = 0.0f;
        if (l > 1.0f) l = 1.0f;
        if (r < 0.0f) r = 0.0f;
        if (r > 1.0f) r = 1.0f;
        v.left  = (WORD)(l * 65535.0f);
        v.right = (WORD)(r * 65535.0f);

        if (g_set && (v.left != letzte.left || v.right != letzte.right)) {
            g_set(g_pad, &v);
            letzte = v;
        }
        Sleep(TICK_MS);
    }
    if (g_set) {
        XVib aus;
        aus.left = 0;
        aus.right = 0;
        g_set(g_pad, &aus);
    }
    return 0;
}

/* --------------------------------------------------------- Einstellungen */
static void lies_ini(void)
{
    char pfad[MAX_PATH], wert[64];
    char *p;

    GetModuleFileNameA(NULL, pfad, MAX_PATH);
    p = strrchr(pfad, 92);
    if (p) strcpy(p + 1, "RiddickRumble.ini");
    if (GetFileAttributesA(pfad) == INVALID_FILE_ATTRIBUTES) return;

    GetPrivateProfileStringA("Rumble", "Gain", "1.0", wert, sizeof(wert), pfad);
    g_gain = (float)atof(wert);
    g_swap = GetPrivateProfileIntA("Rumble", "SwapMotors", 0, pfad);
    g_log  = GetPrivateProfileIntA("Rumble", "Log", 1, pfad);
    if (g_gain < 0.0f) g_gain = 0.0f;
    if (g_gain > 4.0f) g_gain = 4.0f;
}

/* ---------------------------------------------------------------- XInput */
static void hole_xinput(void)
{
    static const char *kandidaten[3] = {
        "xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll"
    };
    int i;

    for (i = 0; i < 3; i++) {
        HMODULE h = LoadLibraryA(kandidaten[i]);
        if (!h) continue;
        g_set = (PfnSet)GetProcAddress(h, "XInputSetState");
        g_get = (PfnGet)GetProcAddress(h, "XInputGetState");
        if (g_set) {
            plog("XInputSetState aus %s", kandidaten[i]);
            return;
        }
        FreeLibrary(h);
    }
    plog("KEIN XInputSetState gefunden - Rumble bleibt stumm");
}

/* Sucht den ersten belegten Steckplatz. Wird einmal pro Sekunde aufgerufen,
 * meldet aber nur, wenn sich etwas aendert - sonst laeuft das Protokoll voll. */
static void suche_pad(void)
{
    static int gemeldet = -2;
    unsigned char zustand[32];
    DWORD i;
    int gefunden = -1;

    if (!g_get) return;
    for (i = 0; i < 4; i++) {
        memset(zustand, 0, sizeof(zustand));
        if (g_get(i, zustand) == ERROR_SUCCESS) { gefunden = (int)i; break; }
    }
    if (gefunden >= 0) g_pad = (DWORD)gefunden;
    if (gefunden == gemeldet) return;
    gemeldet = gefunden;
    if (gefunden >= 0)
        plog("Controller auf Steckplatz %d", gefunden);
    else
        plog("kein Controller angeschlossen - Steckplatz 0 wird trotzdem bedient");
}

static void anstossen(int idx)
{
    int i, frei = -1;

    EnterCriticalSection(&g_cs);
    for (i = 0; i < MAX_VOICE; i++) {
        if (g_voice[i].idx == idx) { frei = i; break; }   /* neu anstossen */
        if (g_voice[i].idx < 0 && frei < 0) frei = i;
    }
    if (frei < 0) frei = 0;
    g_voice[frei].idx = idx;
    g_voice[frei].start = GetTickCount();
    LeaveCriticalSection(&g_cs);
}

/* ---------------------------------------------------------- Schnittstelle */
__declspec(dllexport) void __stdcall RiddickRumble(int id)
{
    int idx;
    const char *name;

    if (id < 1 || id > 29) {
        plog("Kennung %d ausserhalb 1..29", id);
        return;
    }
    if (!g_bereit) return;              /* Einrichtung laeuft noch */
    name = g_ids[id - 1];
    idx = finde(name);
    if (idx < 0) {
        plog("id %2d  %-22s  KEINE Huellkurve", id, name);
        return;
    }
    anstossen(idx);
    plog("id %2d  %-22s  %.2f s, %d/%d Punkte", id, name,
         g_env[idx].dauer, g_env[idx].n[0], g_env[idx].n[1]);
}

/* Zum Ausprobieren von aussen: Effekt ueber seinen Namen anstossen. */
__declspec(dllexport) void __stdcall RiddickRumbleByName(const char *name)
{
    int idx;
    if (!g_bereit) { Sleep(300); }      /* beim Ausprobieren kurz warten */
    idx = finde(name ? name : "");
    if (idx < 0) {
        plog("Name '%s' unbekannt", name ? name : "(null)");
        return;
    }
    anstossen(idx);
    plog("Name '%s' angestossen (%.2f s)", name, g_env[idx].dauer);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD grund, LPVOID reserviert)
{
    int i;
    (void)reserviert;

    if (grund == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        InitializeCriticalSection(&g_cs);
        for (i = 0; i < MAX_VOICE; i++) g_voice[i].idx = -1;
        /* Hier nur den Faden erzeugen - alles andere macht er selbst,
         * ausserhalb der Ladesperre. */
        CreateThread(NULL, 0, arbeiter, NULL, 0, NULL);
    } else if (grund == DLL_PROCESS_DETACH) {
        g_stop = 1;
        if (g_set) {
            XVib aus;
            aus.left = 0;
            aus.right = 0;
            g_set(g_pad, &aus);
        }
    }
    return TRUE;
}
