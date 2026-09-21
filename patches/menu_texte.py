#!/usr/bin/env python3
"""
Zwei Texte im Menue geradeziehen.

1. Startbildschirm: "EINGABETASTE DRUECKEN" -> A-Symbol + " DRUECKEN".
   Das A-Symbol liegt im Schriftatlas auf dem Spenderzeichen 0xF0 (siehe
   font_color.py); geschrieben wird also schlicht das Zeichen U+00F0.
   Die Engine waehlt den Schluessel selbst; `MENU_PRESSSTART` (Konsole),
   `MENU_PRESSSTARTBUTTON` und `MENU_PRESSSTART_PC` stehen alle in
   Frontend_*.txt, aber keiner der Namen kommt als Zeichenkette in den DLLs
   vor - die Auswahl passiert also nicht ueber einen Namen, den man umbiegen
   koennte. Darum wird schlicht der Text von `MENU_PRESSSTART_PC` auf den
   Wortlaut der Konsolenfassung gesetzt.

2. Das eingeblendete "PAUSE" unten im Pausemenue ist `STD_PAUSED` aus
   StringsX360_*.txt. Es erscheint, weil der Plattformschalter auf XENON
   steht (auf der echten 360 steht es auch dort). Der Wert wird geleert.

Die Tabellen sind teils **UTF-16LE mit Stuecklistenzeichen**, teils Latin-1.
Beides wird erkannt und unveraendert wieder geschrieben - eine Umkodierung
wuerde alle Umlaute zerstoeren.

    python menu_texte.py            Vorschau
    python menu_texte.py --apply
    python menu_texte.py --restore
"""

import argparse
import os
import re
import shutil

GAME = r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
BAK = ".vor_menutext"

# Datei -> [(Schluessel, neuer Wert)]
ARBEIT = {
    os.path.join(GAME, "Content_Ger", "Registry", "Stringtables", "Frontend_Ger.txt"):
        [("MENU_PRESSSTART_PC", "\u00f0 DR\u00dcCKEN")],
    os.path.join(GAME, "Content", "Registry", "Stringtables", "Frontend_Eng.txt"):
        [("MENU_PRESSSTART_PC", "PRESS ð")],
    os.path.join(GAME, "Content_Ger", "Registry", "Stringtables", "StringsX360_Ger.txt"):
        [("STD_PAUSED", "")],
    os.path.join(GAME, "Content", "Registry", "Stringtables", "StringsX360_Eng.txt"):
        [("STD_PAUSED", "")],
}


def lies(pfad):
    d = open(pfad, "rb").read()
    if d[:2] == b"\xff\xfe":
        return d[2:].decode("utf-16-le"), "utf-16-le", True
    return d.decode("latin1"), "latin1", False


def schreib(pfad, text, enc, bom):
    roh = (b"\xff\xfe" if bom else b"") + text.encode(enc)
    open(pfad, "wb").write(roh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=None,
                    help="Spielordner - die Wurzel, in der Content und System liegen. Ohne Angabe gilt der Wert oben im Skript.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    global GAME, ARBEIT
    if a.game:
        alt = GAME
        GAME = a.game
        ARBEIT = {p.replace(alt, GAME): v for p, v in ARBEIT.items()}

    if a.restore:
        for p in ARBEIT:
            if os.path.exists(p + BAK):
                shutil.copyfile(p + BAK, p)
                os.remove(p + BAK)
                print("   zurueckgespielt:", os.path.basename(p))
            else:
                print("   kein Backup:", os.path.basename(p) + BAK)
        return

    ergebnis = {}
    for pfad, paare in ARBEIT.items():
        if not os.path.exists(pfad):
            print("   fehlt:", pfad)
            continue
        t, enc, bom = lies(pfad)
        zeilen = t.count("\n")
        for schluessel, neu in paare:
            mu = re.compile(r'(\*' + schluessel + r'[ \t]+")([^"]*)(")')
            treffer = mu.findall(t)
            if len(treffer) != 1:
                raise SystemExit("%s: *%s kommt %d x vor (erwartet 1)"
                                 % (os.path.basename(pfad), schluessel, len(treffer)))
            alt = treffer[0][1]
            if alt == neu:
                print("   %-22s *%-20s steht schon auf %r"
                      % (os.path.basename(pfad), schluessel, neu))
                continue
            t = mu.sub(lambda m: m.group(1) + neu + m.group(3), t, count=1)
            print("   %-22s *%-20s %r -> %r"
                  % (os.path.basename(pfad), schluessel, alt, neu))
        if t.count("\n") != zeilen:
            raise SystemExit("%s: Zeilenzahl veraendert" % pfad)
        ergebnis[pfad] = (t, enc, bom)

    if not a.apply:
        print()
        print("(nur Vorschau - mit --apply anwenden; Spiel muss geschlossen sein)")
        return
    for pfad, (t, enc, bom) in ergebnis.items():
        if not os.path.exists(pfad + BAK):
            shutil.copyfile(pfad, pfad + BAK)
        schreib(pfad, t, enc, bom)
    print("\ngeschrieben. Sicherungen: *%s" % BAK)


if __name__ == "__main__":
    main()
