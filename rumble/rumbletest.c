/* rumbletest.exe - RiddickRumble.dll ohne das Spiel ausprobieren.
 *
 * Muss in System\Win32_x86\ neben DarkAthena.exe liegen, weil die DLL ihre
 * Pfade aus dem Ort der laufenden .exe ableitet (zwei Ebenen hoch ist die
 * Spielwurzel mit Content\Feedback\feedback.xrg).
 *
 *   rumbletest                    -> Explo_01_2sek
 *   rumbletest ShotGun_Shot01     -> benannter Effekt
 *   rumbletest 14                 -> ueber die Kennung, wie das Spiel es tut
 */

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

typedef void (__stdcall *PfnId)(int);
typedef void (__stdcall *PfnName)(const char *);

int main(int argc, char **argv)
{
    HMODULE h;
    PfnId   nach_id;
    PfnName nach_name;
    const char *arg = (argc > 1) ? argv[1] : "Explo_01_2sek";

    h = LoadLibraryA("RiddickRumble.dll");
    if (!h) {
        printf("RiddickRumble.dll laesst sich nicht laden (Fehler %lu)\n",
               GetLastError());
        return 1;
    }
    nach_id   = (PfnId)GetProcAddress(h, "RiddickRumble");
    nach_name = (PfnName)GetProcAddress(h, "RiddickRumbleByName");
    printf("RiddickRumble       = %p\n", (void *)nach_id);
    printf("RiddickRumbleByName = %p\n", (void *)nach_name);
    if (!nach_id || !nach_name) return 2;

    /* Die DLL richtet sich in einem eigenen Faden ein (nicht in DllMain,
     * das waere unter der Ladesperre gefaehrlich). Kurz warten. */
    Sleep(500);

    if (arg[0] >= '0' && arg[0] <= '9') {
        int id = atoi(arg);
        printf("stosse Kennung %d an ...\n", id);
        nach_id(id);
    } else {
        printf("stosse '%s' an ...\n", arg);
        nach_name(arg);
    }
    Sleep(4000);
    printf("fertig - das Protokoll steht in RiddickRumble.log\n");
    FreeLibrary(h);
    return 0;
}
