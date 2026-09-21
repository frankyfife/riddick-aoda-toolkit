#!/usr/bin/env python3
"""
Konsolen-Tastenhinweise in der Menuedefinition wieder einschalten.

Die Konsolenfassung deklariert die Menue-Hinweise als
    *BUTTONDESC1 b,<A7>LMENU_BACK
also "B-Knopf, Beschriftung Zurueck" - daraus macht die Engine einen Glyphen.
Im PC-Build sind genau diese Zeilen **auskommentiert** und durch
    *OUTSIDEBUTTON pos='bottomleft' action='...' caption='<A7>LMENU_BACK'
ersetzt, was die Tastenkappe mit "Esc" zeichnet. Die Parser-Schluesselwoerter
BUTTONDESC0..3 sind in GameClasses und GameWorld aber weiterhin vorhanden.

Dieses Skript entfernt das "//" vor den BUTTONDESC-Zeilen. Es ersetzt die zwei
Schraegstriche durch zwei Leerzeichen, die Datei bleibt also byteweise gleich
lang - und wird **binaer** gelesen und geschrieben, damit die CRLF-Zeilenenden
erhalten bleiben (eine Textmodus-Konvertierung hat hier schon mal die komplette
Pad-Steuerung der Menues lahmgelegt).

    python enable_buttondesc.py            # Vorschau
    python enable_buttondesc.py --apply    # anwenden (legt .orig an)
    python enable_buttondesc.py --restore  # zuruecksetzen
"""

import argparse
import os
import re
import shutil

CUBE = (r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
        r"\Content\GUI\CubeWnd.xrg")

PAT = re.compile(rb'//(\s*)(\*BUTTONDESC([0-3])\s+([^,]+),)')
# Die PC-spezifischen Tastenkappen-Hinweise. Die Konsolenfassung hat davon nur
# zwei, der PC-Port 158 - sie ueberlagern jetzt die wieder aktiven BUTTONDESC.
OUT = re.compile(rb'(?<!/)\*OUTSIDEBUTTON')
# Einzelne Hinweise heissen MENU_BACK, fuehren aber die Taste a. "Zurueck"
# liegt in der Konsolenbelegung auf B; ohne die Korrektur zeigt der Hinweis das
# falsche Symbol. Nur BUTTONDESC0, nur diese Beschriftung.
#
# MENU_CONTINUE bleibt ausdruecklich auf a: die Konsolenfassung zeigt
# "Weiterspielen" mit dem gruenen A (in den Aufnahmen der Xbox-360-Fassung
# nachgesehen), nicht mit B.
B_FIX = re.compile(rb'(\*BUTTONDESC0\s+)a,(\xa7LMENU_BACK)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default=CUBE)
    ap.add_argument('--nur', default='',
                    help='nur Hinweise mit diesen Tasten einschalten, z.B. "a,b". '
                         'Leer heisst alle. Gebraucht fuer CubeInv0: dort '
                         'ueberlagern die Pfeil-Hinweise die ohnehin '
                         'vorhandenen Seitenbeschriftungen.')
    ap.add_argument('--kein-b-fix', action='store_true',
                    help='MENU_BACK/MENU_CONTINUE nicht von a auf b setzen')
    ap.add_argument('--no-outside', action='store_true',
                    help='die PC-Tastenkappen-Hinweise abschalten')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--restore', action='store_true')
    a = ap.parse_args()
    nur = set(x.strip().encode() for x in a.nur.split(',') if x.strip())

    bak = a.file + '.orig'
    if a.restore:
        if os.path.exists(bak):
            shutil.copyfile(bak, a.file)
            os.remove(bak)
            print('zurueckgespielt:', a.file)
        else:
            print('kein Backup:', bak)
        return

    src = bak if os.path.exists(bak) else a.file
    d = open(src, 'rb').read()

    hits = list(PAT.finditer(d))
    print('%d auskommentierte BUTTONDESC-Zeilen gefunden' % len(hits))
    seen = {}
    for m in hits:
        line = d[m.start():d.find(b'\r', m.start())]
        key = line.decode('latin-1')
        seen[key] = seen.get(key, 0) + 1
    for k, n in sorted(seen.items(), key=lambda x: -x[1]):
        print('  %3dx  %s' % (n, k.replace('\xa7', '@')))

    out = PAT.sub(lambda m: (b'  ' + m.group(1) + m.group(2)
                             if (not nur or m.group(4).strip().lower() in nur)
                             else m.group(0)), d)
    assert len(out) == len(d), 'Laenge veraendert - abbrechen'
    if nur:
        print('\nnur Tasten %s eingeschaltet' % a.nur)

    if not a.kein_b_fix:
        n = len(B_FIX.findall(out))
        out = B_FIX.sub(lambda m: m.group(1) + b'b,' + m.group(2), out)
        assert len(out) == len(d), 'Laenge veraendert - abbrechen'
        if n:
            print('%d Hinweis(e) MENU_BACK/MENU_CONTINUE von a auf b gesetzt' % n)

    if a.no_outside:
        n = len(OUT.findall(out))
        out = OUT.sub(b'//*OUTSIDEBUTTON', out)
        print('\n%d OUTSIDEBUTTON-Zeilen auskommentiert (die PC-Tastenkappen)' % n)
    assert out.count(b'\r\n') == d.count(b'\r\n'), 'Zeilenenden veraendert'

    if not a.apply:
        print('\n(nur Vorschau - mit --apply anwenden)')
        return

    if not os.path.exists(bak):
        shutil.copyfile(a.file, bak)
        print('Backup:', bak)
    open(a.file, 'wb').write(out)
    print('eingeschaltet. CRLF unveraendert: %d' % out.count(b'\r\n'))


if __name__ == '__main__':
    main()
