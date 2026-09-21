#!/usr/bin/env python3
r"""
Die Eckhinweise auf die richtigen 360-Knopfgrafiken umstellen.

Der Befund
----------
Der PC-Atlas `Content\GUI\Textures\GUI.xtc` fuehrt jede der vier Knopfgrafiken
doppelt: `GUI_Button_A/B/X/Y` und `GUI_Button_A/B/X/Y_32`. Beide sind 32x32 -
`_32` ist also keine Groessenangabe, sondern eine **andere Zeichnung**. Die
`_32`-Fassungen sind durchweg heller und flauer:

    B    RGB (126, 48, 39) dunkelrot    B_32  RGB (171, 94, 67) orange
    A        (70, 123, 53) sattes Gruen A_32      (111, 137, 55) blasses Oliv
    X        (44, 63, 125) Blau         X_32       (95, 120, 169) Hellblau
    Y       (144, 122, 23) Gold         Y_32       (188, 155, 22) Hellgelb

Im GUI-Atlas der **Xbox 360** (`riddick-beta\Content\Textures\GUI.xtc`)
existieren die `_32`-Fassungen **gar nicht**. Die Konsole nennt den Namen in
ihrer `CubeWnd.xcr` zwar, hat aber keine Grafik dazu und zeichnet die
Vollversion - deshalb ist das B dort dunkelrot und auf dem PC orange.

Dieses Skript streicht das Suffix an den sieben Stellen, an denen es die
sichtbaren Eckhinweise betrifft. Die Dateien werden **binaer** gelesen und
geschrieben und die CRLF-Zahl geprueft - ein Textmodus wuerde die Beschleuniger
der Menues zerstoeren.

    python pc_button_icons.py            Vorschau
    python pc_button_icons.py --apply
    python pc_button_icons.py --restore
"""

import argparse
import os
import shutil

GUI = (r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
       r"\Content\GUI")
BAK = ".vor_knopfgrafik"
CRLF = b"\r\n"

# Datei -> Liste von (alt, neu). Die Zeilen sind so eindeutig, dass keine
# Verwechslung moeglich ist; die Trefferzahl wird trotzdem geprueft.
STELLEN = {
    "CubeWnd.xrg": [
        (b'*ICONSURFACE_Y "GUI_Button_Y_32"', b'*ICONSURFACE_Y "GUI_Button_Y"'),
        (b'*ICONSURFACE_X "GUI_Button_X_32"', b'*ICONSURFACE_X "GUI_Button_X"'),
        (b'*ICONSURFACE_B "GUI_Button_B_32"', b'*ICONSURFACE_B "GUI_Button_B"'),
        (b'*ICONSURFACE_A "GUI_Button_A_32"', b'*ICONSURFACE_A "GUI_Button_A"'),
        (b'*BICONSURFACE "GUI_Button_B_32"',  b'*BICONSURFACE "GUI_Button_B"'),
        (b'*AICONSURFACE "GUI_Button_A_32"',  b'*AICONSURFACE "GUI_Button_A"'),
    ],
    "CubeInv0.xrg": [
        (b'*ICONSURFACE GUI_Button_A_32', b'*ICONSURFACE GUI_Button_A'),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ordner", default=GUI)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()

    if a.restore:
        for f in STELLEN:
            p = os.path.join(a.ordner, f)
            if os.path.exists(p + BAK):
                shutil.copyfile(p + BAK, p)
                os.remove(p + BAK)
                print("   zurueckgespielt:", f)
            else:
                print("   kein Backup:", f + BAK)
        return

    ergebnis = {}
    for f, paare in STELLEN.items():
        p = os.path.join(a.ordner, f)
        d = open(p, "rb").read()
        zeilen = d.count(CRLF)
        out = d
        print("### %s" % f)
        for alt, neu in paare:
            n = out.count(alt)
            if n == 0 and out.count(neu) >= 1:
                print("   %-38s schon umgestellt" % neu.decode())
                continue
            if n != 1:
                raise SystemExit("%s: %r kommt %d x vor (erwartet 1)"
                                 % (f, alt.decode(), n))
            out = out.replace(alt, neu)
            print("   %-38s -> %s" % (alt.decode(), neu.decode()))
        if out.count(CRLF) != zeilen:
            raise SystemExit("%s: Zeilenenden veraendert - abbrechen" % f)
        print("   CRLF unveraendert: %d" % zeilen)
        ergebnis[p] = out

    if not a.apply:
        print("\n(nur Vorschau - mit --apply anwenden; Spiel muss geschlossen sein)")
        return
    for p, inhalt in ergebnis.items():
        if not os.path.exists(p + BAK):
            shutil.copyfile(p, p + BAK)
        open(p, "wb").write(inhalt)
    print("\ngeschrieben. Sicherungen: *%s" % BAK)


if __name__ == "__main__":
    main()
