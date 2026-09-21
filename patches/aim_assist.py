#!/usr/bin/env python3
r"""
Die Zielhilfe wirklich abschaltbar machen.

Warum der Regler im Menue nichts tut
------------------------------------
Der Punkt "Autoaim" im Konsolenmenue (CubeWnd.xrg, Fenster
`options_controller_adv`, `*OPTION "OPT\CONTROLLER_AUTOAIM"`, `*STEPS 6`)
wird durchaus **gelesen**: GameClasses `0x1030aad0` ff. holt den Wert ueber
`[vtable+0x78]` mit dem Vorgabewert 0.7, multipliziert ihn mit einem Faktor
aus `GAME_DIFFICULTY` und legt ihn im Einstellungsobjekt bei `+0xac4` ab.

Nur: **niemand liest dieses Feld je wieder.** Alle zehn Gleitkomma-Zugriffe
darauf liegen zwischen `0x10305e77` und `0x1030d2d5` und tun ausschliesslich
setzen, kopieren und serialisieren (Replikation zum Server). In der
Zielrechnung kommt `+0xac4` nicht vor - weder in GameClasses noch in
GameWorld. Der Regler speichert also einen Wert, den die Spiellogik ignoriert.

Wirksam ist stattdessen die **Waffenflagge** `autoaim` (Bit 9 = 0x200 der
Gegenstandsflaggen, Tabelle ab GameClasses `0x1082d728`). Sie steht in
`Content\Registry\RpgWeapons.xrg` an 23 Waffen. Dieses Skript nimmt sie
heraus - eine reine Datenaenderung, kein Code-Eingriff.

Die Datei wird **binaer** gelesen und geschrieben und die CRLF-Zahl geprueft.
`noautoaim` (Figurenflagge, Bit 24) bleibt unangetastet - der Ausdruck greift
nur, wenn vor `autoaim` kein Buchstabe steht.

    python aim_assist.py            Vorschau
    python aim_assist.py --apply    Zielhilfe aus
    python aim_assist.py --restore  Zielhilfe wieder an
"""

import argparse
import os
import re
import shutil

DATEI = (r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
         r"\Content\Registry\RpgWeapons.xrg")
BAK = ".vor_zielhilfe"
CRLF = b"\r\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datei", default=DATEI)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()

    bak = a.datei + BAK
    if a.restore:
        if os.path.exists(bak):
            shutil.copyfile(bak, a.datei)
            os.remove(bak)
            print("zurueckgespielt:", os.path.basename(a.datei), "- Zielhilfe wieder an")
        else:
            print("kein Backup:", bak)
        return

    d = open(a.datei, "rb").read()
    zeilen = d.count(CRLF)

    # nur in *flags-Zeilen, und nur als eigenstaendige Flagge
    ab, an = 0, 0
    aus = bytearray()
    rest = 0
    for m in re.finditer(rb"(?m)^[^\r\n]*\*flags[^\r\n]*", d):
        zeile = m.group(0)
        if not re.search(rb"(?<![a-zA-Z])autoaim", zeile):
            continue
        neu = re.sub(rb"(?<![a-zA-Z])autoaim\+", b"", zeile)
        neu = re.sub(rb"\+(?<![a-zA-Z]\+)autoaim(?![a-zA-Z])", b"", neu)
        if neu == zeile:
            continue
        aus += d[rest:m.start()] + neu
        rest = m.end()
        ab += 1
        if ab <= 3:
            print("   %s" % zeile.strip().decode("latin1")[:76])
            print("-> %s" % neu.strip().decode("latin1")[:76])
    aus += d[rest:]
    out = bytes(aus)

    print()
    print("   %d Waffen verlieren die Flagge 'autoaim'" % ab)
    uebrig = len(re.findall(rb"(?<![a-zA-Z])autoaim", out))
    print("   danach noch 'autoaim' im Text: %d (erwartet 0)" % uebrig)
    print("   'noautoaim' unveraendert: %d" % len(re.findall(rb"noautoaim", out)))
    if out.count(CRLF) != zeilen:
        raise SystemExit("Zeilenenden veraendert - abbrechen")
    print("   CRLF unveraendert: %d" % zeilen)

    if not a.apply:
        print()
        print("(nur Vorschau - mit --apply anwenden; Spiel muss geschlossen sein)")
        return
    if not ab:
        print("nichts zu tun - die Flagge ist schon draussen")
        return
    if not os.path.exists(bak):
        shutil.copyfile(a.datei, bak)
        print("\nBackup:", os.path.basename(bak))
    open(a.datei, "wb").write(out)
    print("geschrieben - Zielhilfe aus.")


if __name__ == "__main__":
    main()
