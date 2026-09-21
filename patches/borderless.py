#!/usr/bin/env python3
"""
Randloses Fenster statt Rahmenfenster - ohne DxWnd.

Hintergrund
-----------
`VID_MODE=desktop` ist eine Hintertuer der Engine: MSystem vergleicht den Wert
gegen die Zeichenkette "desktop" (0x100b90ca) und ueberspringt dann die
Modussuche. Das Spiel laeuft damit in voller Desktopaufloesung - aber als
Fenster **mit Rahmen**. Genau dafuer setzt die Gemeinde sonst DxWnd ein.

Das Fenster baut RndrGL. Die zustaendige Funktion bekommt Stil und erweiterten
Stil als Parameter und liest den Stil an zwei Stellen aus dem Stapel:

    0x1003aa07  mov ecx,[esp+0x950]   -> Stil fuer AdjustWindowRectEx
    0x1003ab07  mov ecx,[esp+0x94c]   -> Stil fuer CreateWindowExA

Beide sind 7 Byte lang, dort passt genau `mov ecx, imm32` (5) plus zwei NOPs.
Wichtig ist, **beide** zu setzen: `AdjustWindowRectEx` rechnet aus der
Client-Groesse die Fenstergroesse aus. Bliebe dort der Rahmenstil stehen, waere
das Fenster um die Rahmenbreite zu gross und saesse verschoben - genau das
bekannte "klemmt unten links".

Standardstil: WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN.

    python borderless.py            Vorschau
    python borderless.py --apply
    python borderless.py --restore
"""

import argparse
import os
import re
import shutil
import struct
import struct

RNDR = (r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
        r"\System\Win32_x86\RndrGL.dll")
BAK = ".vor_randlos"

WS_POPUP        = 0x80000000
WS_VISIBLE      = 0x10000000
WS_CLIPSIBLINGS = 0x04000000
WS_CLIPCHILDREN = 0x02000000
STIL = WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN

# (Bezeichnung, Muster, Laenge des zu ersetzenden mov)
STELLEN = (
    ("AdjustWindowRectEx", bytes.fromhex("8b8c2450090000" "6a00" "89542428" "51"), 7),
    ("CreateWindowExA",    bytes.fromhex("8b8c244c090000" "6a00" "52"), 7),
)

# ---------------------------------------------------------------- Balken weg
# Der Zeichenbereich kommt aus `CRC_Viewport::GetViewArea` (MSystem 0x1004dbb0)
# und ist bereits das gebalkte Rechteck - das Viewport-Objekt kennt gar nichts
# anderes. Die Flaechenmasse dagegen hat RndrGL selbst: [ebx+0x3f6c] Breite,
# [ebx+0x3f70] Hoehe (beide aus 0x3f5c/0x3f60 kopiert, siehe 0x10031356 ff.).
#
# In der Funktion ab 0x10031400 holt `call 0x10031470` das Rechteck nach
# [esp+0x20..0x2c] (x1,y1,x2,y2). Danach rechnet sie daraus die vier
# glViewport-Argumente - und **liest das Rechteck hinter dem Aufruf noch
# einmal**, um daraus Projektionswerte zu bilden ([ebx+0x3f3c], 0x3f40,
# 0x3f54, 0x3f58). Deshalb wird nicht nur der Viewport gesetzt, sondern das
# Rechteck auf dem Stapel selbst auf (0,0,Breite,Hoehe) ueberschrieben - dann
# passt auch die Projektion dazu und das Bild wird nicht verzerrt.
#
# Ersetzt werden die 44 Byte von 0x10031475 bis 0x100314a0 (alles zwischen dem
# GetViewArea-Aufruf und dem glViewport-Aufruf).
VP_ALT = bytes.fromhex(
    "8b83703f0000" "8b8b783f0000" "3bc8" "7e02" "8bc1"
    "8b4c242c" "8b742428" "8bd1" "2b542424" "2bc1"
    "52" "8b542424" "2bf2" "56" "50" "52")
# ------------------------------------------- voller Monitor statt Arbeitsflaeche
# RndrGL holt sich bei 0x1001c88d ein MONITORINFO (Puffer ab [esp+0x28]):
#   +0x2c..0x38 rcMonitor   +0x3c..0x48 rcWork
# und rechnet die Fenstergroesse aus **rcWork** - also ohne Taskleiste. Genau
# deshalb blieb oben ein Streifen Desktop und unten die Leiste stehen.
# Vier Lesezugriffe, jeweils 0x10 tiefer auf rcMonitor gezogen. (Das `push 0`
# in der Mitte verschiebt esp um 4, deshalb sind die letzten beiden
# Verschiebungen um 4 groesser.)
MON_ALT = bytes.fromhex(
    "8b442444" "2b44243c"      # rcWork.right  - rcWork.left   = Breite
    "6a00" "8944245c"
    "8b44244c" "2b442444"      # rcWork.bottom - rcWork.top    = Hoehe
    "89442458")
MON_NEU = bytes.fromhex(
    "8b442434" "2b44242c"      # rcMonitor.right  - rcMonitor.left
    "6a00" "8944245c"
    "8b44243c" "2b442434"      # rcMonitor.bottom - rcMonitor.top
    "89442458")

# --------------------------------------------- Klemmung an den Arbeitsbereich
# Die Fensterfunktion holt sich SPI_GETWORKAREA (0x1003a8e4) und **kuerzt** die
# gewuenschte Groesse darauf:
#     edx = rcWork.right - rcWork.left      ; Arbeitsbreite
#     cmp ebx,edx / jle weiter              ; groesser? -> schrumpfen
# und ebenso fuer die Hoehe. Bei einer 159 Pixel hohen Taskleiste werden aus
# 2160 genau 2001 - exakt der gemessene Fehlbetrag. Beide Spruenge werden
# unbedingt gemacht, damit nie geklemmt wird.
KLEMM = (
    ("Breite", bytes.fromhex("3bda" "7e18" "8b96180700 00".replace(" ", "")),
               bytes.fromhex("3bda" "eb18" "8b96180700 00".replace(" ", ""))),
    ("Hoehe",  bytes.fromhex("3bfa" "7e18" "8b961c0700 00".replace(" ", "")),
               bytes.fromhex("3bfa" "eb18" "8b961c0700 00".replace(" ", ""))),
)

VP_NEU = bytes.fromhex(
    "c744242000000000"      # mov [esp+0x20],0        x1
    "c744242400000000"      # mov [esp+0x24],0        y1
    "8b836c3f0000"          # mov eax,[ebx+0x3f6c]    Breite
    "89442428"              # mov [esp+0x28],eax      x2
    "8b8b703f0000"          # mov ecx,[ebx+0x3f70]    Hoehe
    "894c242c"              # mov [esp+0x2c],ecx      y2
    "51" "50" "6a00" "6a00" # glViewport(0,0,Breite,Hoehe)
    "9090")                 # Fuellbytes


# ------------------------------------------------ Fenster festnageln
# Wie DxWnd es macht: nicht rechnen, sondern setzen. DxWnds Profil fuer dieses
# Spiel sagt schlicht posx=0, posy=0, sizx=3820, sizy=2160.
#
# Hinter `CreateWindowExA` (0x1003ab34) liegt der Fehlerzweig 0x1003ab40..
# 0x1003ab94 - 84 Byte, die nur laufen, wenn die Fenstererzeugung scheitert
# (dann ist das Spiel ohnehin verloren). Dort hinein kommt:
#
#     SetWindowPos(hwnd, NULL, 0, 0,
#                  GetSystemMetrics(SM_CXSCREEN),
#                  GetSystemMetrics(SM_CYSCREEN),
#                  SWP_NOZORDER|SWP_NOACTIVATE)
#
# Das Spiel ist per-monitor-DPI-bewusst (im laufenden Spiel gemessen), die
# Metriken liefern also echte 3840x2160.
#
# Die beiden Aufrufe muessen **ohne absolute Adresse** auskommen, weil in der
# Hoehle keine Relocations liegen und die DLL verschoben werden kann: call/pop
# holt die eigene Adresse, die IAT-Slots werden relativ dazu angesprochen.
NAGEL_AT   = 0x1003ab3e     # jne 0x1003ab94  -> wird zu zwei NOPs
NAGEL_ALT  = bytes.fromhex("7554")
HOEHLE_VA  = 0x1003ab40
HOEHLE_END = 0x1003ab94
IAT_GETSYSTEMMETRICS = 0x100b291c
IAT_SETWINDOWPOS     = 0x100b28e0


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3c)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    opthdr = struct.unpack_from("<H", d, e + 20)[0]
    sectbl = e + 24 + opthdr
    r = va - 0x10000000
    for i in range(nsec):
        b = sectbl + 40 * i
        v = struct.unpack_from("<I", d, b + 12)[0]
        vs = struct.unpack_from("<I", d, b + 8)[0]
        pr = struct.unpack_from("<I", d, b + 20)[0]
        rs = struct.unpack_from("<I", d, b + 16)[0]
        if v <= r < v + max(vs, rs):
            return pr + (r - v)
    raise SystemExit("VA 0x%08x nicht in einer Sektion" % va)


def nagel_code(cave_va):
    """Baut den Stummel; anker ist das `pop ebx` bei cave+10."""
    anker = cave_va + 10
    dg = IAT_GETSYSTEMMETRICS - anker
    dw = IAT_SETWINDOWPOS - anker
    c = bytearray()
    c += bytes.fromhex("85f6")                       # test esi,esi
    c += bytes.fromhex("7429")                       # je ende (+0x29)
    c += bytes.fromhex("53")                         # push ebx
    c += bytes.fromhex("e800000000")                 # call $+5
    c += bytes.fromhex("5b")                         # pop ebx   <- anker
    c += bytes.fromhex("6a14")                       # push 0x14  SWP_NOZORDER|NOACTIVATE
    c += bytes.fromhex("6a01")                       # push 1     SM_CYSCREEN
    c += bytes.fromhex("ff93") + struct.pack("<i", dg)
    c += bytes.fromhex("50")                         # push eax   cy
    c += bytes.fromhex("6a00")                       # push 0     SM_CXSCREEN
    c += bytes.fromhex("ff93") + struct.pack("<i", dg)
    c += bytes.fromhex("50")                         # push eax   cx
    c += bytes.fromhex("6a00")                       # push 0     Y
    c += bytes.fromhex("6a00")                       # push 0     X
    c += bytes.fromhex("6a00")                       # push 0     hWndInsertAfter
    c += bytes.fromhex("56")                         # push esi   hWnd
    c += bytes.fromhex("ff93") + struct.pack("<i", dw)
    c += bytes.fromhex("5b")                         # pop ebx
    assert len(c) == 45, len(c)                      # ende liegt bei +45
    c += bytes.fromhex("e9") + struct.pack("<i", HOEHLE_END - (cave_va + 50))
    return bytes(c)


# --- Die eigentliche 4K-Sperre -------------------------------------------
# `ModeList_Init` (MDispGL.cpp, ab 0x10040380) ruft EnumDisplaySettingsA in
# einer Schleife und bricht **nach 512 Modi** ab:
#     100405b1  cmp eax, 0x200
#     100405ba  jl  0x100403c0
# Windows meldet auf diesem Rechner 650 Modi; 3840x2160 liegt auf Platz
# 637-649, faellt also hinten heraus. Der groesste Modus unterhalb von 512 ist
# 1920x1440 (4:3) - genau das, was die "best match"-Suche dann waehlt und was
# das Spiel als VID_MODE in die cfg zurueckschreibt.
# Die Schleife endet ohnehin sauber, sobald EnumDisplaySettings 0 liefert
# (0x100403d4), die 512 sind also nur eine Sicherheitsgrenze. Auf 4096 hoch.
MODI_AT  = 0x100405b1
MODI_ALT = bytes.fromhex("3d00020000")      # cmp eax, 0x200
MODI_NEU = bytes.fromhex("3d00100000")      # cmp eax, 0x1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datei", default=RNDR)
    ap.add_argument("--stil", default=None,
                    help="Fensterstil als Hexzahl, z.B. 0x96000000")
    ap.add_argument("--alte-modiliste", action="store_true",
                    help="die Aufzaehlgrenze von 512 Anzeigemodi so lassen "
                         "(dann findet das Spiel 3840x2160 nicht)")
    ap.add_argument("--kein-nagel", action="store_true",
                    help="das Fenster NICHT per SetWindowPos festnageln "
                         "(der Aufruf kommt vor der Renderer-Initialisierung "
                         "und hat im Spiel einen Absturz ausgeloest)")
    ap.add_argument("--nur-rahmen", action="store_true",
                    help="nur den Fensterrahmen entfernen, Viewport unangetastet")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()

    bak = a.datei + BAK
    if a.restore:
        if os.path.exists(bak):
            shutil.copyfile(bak, a.datei)
            os.remove(bak)
            print("zurueckgespielt:", os.path.basename(a.datei))
        else:
            print("kein Backup:", bak)
        return

    stil = int(a.stil, 16) if a.stil else STIL
    d = bytearray(open(a.datei, "rb").read())
    neu = bytes([0xb9]) + struct.pack("<I", stil) + bytes([0x90, 0x90])
    assert len(neu) == 7

    for bez, pat, n in STELLEN:
        tr = [m.start() for m in re.finditer(re.escape(pat), bytes(d))]
        if len(tr) != 1:
            # schon gepatcht?
            schon = [m.start() for m in
                     re.finditer(re.escape(neu + pat[n:]), bytes(d))]
            if schon:
                print("   %-20s schon gesetzt" % bez)
                continue
            raise SystemExit("%s: %d Treffer statt 1" % (bez, len(tr)))
        o = tr[0]
        print("   %-20s @Datei 0x%06x: %s -> %s"
              % (bez, o, bytes(d[o:o+n]).hex(' '), neu.hex(' ')))
        d[o:o+n] = neu

    if not a.alte_modiliste:
        o = va2off(bytes(d), MODI_AT)
        ist = bytes(d[o:o+len(MODI_ALT)])
        if ist == MODI_NEU:
            print("   %-20s schon gesetzt" % "Modusliste")
        elif ist == MODI_ALT:
            print("   %-20s @Datei 0x%06x: cmp eax,0x200 -> cmp eax,0x1000 "
                  "(512 -> 4096 Modi)" % ("Modusliste", o))
            d[o:o+len(MODI_NEU)] = MODI_NEU
        else:
            raise SystemExit("Modusgrenze unerwartet: %s" % ist.hex(' '))

    if not a.nur_rahmen:
        for bez, kalt, kneu in KLEMM:
            tr = [m.start() for m in re.finditer(re.escape(kalt), bytes(d))]
            if len(tr) == 1:
                print("   %-20s @Datei 0x%06x: jle -> jmp (keine Klemmung)"
                      % ("Arbeitsbereich " + bez, tr[0]))
                d[tr[0]:tr[0]+len(kneu)] = kneu
            elif re.search(re.escape(kneu), bytes(d)):
                print("   %-20s schon gesetzt" % ("Arbeitsbereich " + bez))
            else:
                raise SystemExit("Klemmung %s: %d Treffer" % (bez, len(tr)))

        tr = [m.start() for m in re.finditer(re.escape(MON_ALT), bytes(d))]
        if len(tr) == 1:
            print("   %-20s @Datei 0x%06x: rcWork -> rcMonitor" % ("Monitorflaeche", tr[0]))
            d[tr[0]:tr[0]+len(MON_NEU)] = MON_NEU
        elif re.search(re.escape(MON_NEU), bytes(d)):
            print("   %-20s schon gesetzt" % "Monitorflaeche")
        else:
            raise SystemExit("MONITORINFO-Stelle nicht gefunden (%d Treffer)" % len(tr))

        tr = [m.start() for m in re.finditer(re.escape(VP_ALT), bytes(d))]
        if len(tr) == 1:
            o = tr[0]
            print("   %-20s @Datei 0x%06x: %d Byte Viewport-Rechnung ersetzt"
                  % ("Viewport", o, len(VP_ALT)))
            d[o:o+len(VP_ALT)] = VP_NEU
        elif re.search(re.escape(VP_NEU), bytes(d)):
            print("   %-20s schon gesetzt" % "Viewport")
        else:
            raise SystemExit("Viewport-Rechnung nicht gefunden (%d Treffer)" % len(tr))

    if not a.nur_rahmen and not a.kein_nagel:
        o = va2off(bytes(d), NAGEL_AT)
        if bytes(d[o:o+2]) == NAGEL_ALT:
            d[o:o+2] = bytes.fromhex("9090")
            oc = va2off(bytes(d), HOEHLE_VA)
            code = nagel_code(HOEHLE_VA)
            d[oc:oc+len(code)] = code
            print("   %-20s Fenster auf 0,0 und volle Bildschirmgroesse genagelt"
                  % "SetWindowPos")
        elif bytes(d[o:o+2]) == bytes.fromhex("9090"):
            print("   %-20s schon gesetzt" % "SetWindowPos")
        else:
            raise SystemExit("Nagelstelle unerwartet: %s" % bytes(d[o:o+2]).hex())

    print()
    print("   Stil 0x%08x = WS_POPUP|WS_VISIBLE|WS_CLIPSIBLINGS|WS_CLIPCHILDREN"
          % stil)
    print("   Voraussetzung: VID_MODE=3840 2160 32 120 in der Environment.cfg unter")
    print("   %LOCALAPPDATA%\\Atari\\The Chronicles of Riddick - Assault on Dark Athena")

    if not a.apply:
        print()
        print("(nur Vorschau - mit --apply anwenden; Spiel muss geschlossen sein)")
        return
    if not os.path.exists(bak):
        shutil.copyfile(a.datei, bak)
        print("\nBackup:", os.path.basename(bak))
    open(a.datei, "wb").write(bytes(d))
    print("geschrieben.")


if __name__ == "__main__":
    main()
