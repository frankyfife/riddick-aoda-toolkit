#!/usr/bin/env python3
"""
Pad-Tastennamen auf die Konsolenbezeichnungen umstellen.

Belegt durch die PS3-Fassung (CONTENT_GER/REGISTRY/STRINGTABLE_GER.XCR): Die
Konsole zeichnet in Info- und Tutorialtexten **kein Symbol**, sondern schreibt
den Knopfnamen aus. Der Platzhalter ist derselbe wie auf dem PC -

    *TUTORIAL_DIALOGMODE "... und <A7>LCONTROLLER_USE_B, um ..."

- wird auf der Konsole zu "... und druecken Sie Y, um ...", weil dort
`BUTTON_PREFIX_B` = "druecken Sie" und `CONTROLLER_XBOX_03` = "Y" eingesetzt
werden. Der PC nimmt stattdessen den Rohnamen `JOY_BUTTON_03` aus
`MSystem.dll`, zerlegt ihn am Unterstrich und uebersetzt `JOY_BUTTON` ueber
`Misc_Ger.txt` zu "Knopf" - daher "Knopf 3".

Dieses Skript benennt die Rohnamen in `MSystem.dll` in genau die Bezeichnungen
um, die die Konsolen-Stringtabelle fuehrt. Damit stimmen Info-Texte,
Belegungsseite und Menuehinweise in einem Zug, ohne Codeeingriff.

Die Namenstabelle (`CScanKey::ms_ScanCodeNames`, 0x103bbc90) besteht aus
12-Byte-Eintraegen { Code, Code, char* Name } - die Namen sind also **Zeiger**,
die Laenge ist frei. Die neuen Zeichenketten landen im ungenutzten Teil des
Namensvorrats (Achsen 04..0F, die kein Xbox-Pad je belegt). Deren eigene Namen
werden dabei ueberschrieben; sie sind auf einem Pad nicht erreichbar.

`CubeWnd.xrg` spricht 22 Beschleuniger ueber die alten Namen an. Die werden auf
die Zahlenform `#<dezimal>` umgestellt, die `GetScanCode` ebenfalls versteht -
sonst faellt die Pad-Steuerung der Menues aus. Die Datei wird **binaer**
gelesen und geschrieben, die CRLF-Zeilenenden werden geprueft (eine
Textmodus-Konvertierung hat hier schon einmal alle Beschleuniger zerstoert).

    python rename_pad_keys.py            # Vorschau
    python rename_pad_keys.py --apply
    python rename_pad_keys.py --restore
"""

import argparse
import os
import re
import shutil
import struct

GAME = r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
MSYS = os.path.join(GAME, "System", "Win32_x86", "MSystem.dll")
CUBE = os.path.join(GAME, "Content", "GUI", "CubeWnd.xrg")

CRLF = bytes.fromhex("0d0a")
NUL = bytes(1)

# Eigene Sicherung: `.orig` gehoert bereits enable_buttondesc.py bzw. dem
# DLL-Patcher. Dieses Skript setzt immer auf dem **aktuellen** Stand auf.
BAK = ".vor_padnamen"

# Code -> Name.
# Die Konsole benutzt lange, gebeugte Bezeichnungen ("linken Schalter"), weil
# sie dazu passende Satzbausteine hat: CONTROLLER_XBOX_TRIGGER_C lautet
# "durch Ziehen des <A7>p0". Der PC-Build kennt diese Familien nicht, er hat nur
# das generische BUTTON_PREFIX_C = "durch Druecken von <A7>p0". Mit den langen
# Namen ergibt das "durch Druecken von linken Schalter" - grammatisch kaputt.
# Kurze Xbox-Aufschriften passen in jeden Satzbaustein ("durch Druecken von LT",
# "druecken Sie Y") und sind ausserdem genau die Beschriftung des Controllers.
NAMES = {
    # Knoepfe und Steuerkreuz: **ein einzelnes Sonderzeichen**, dem
    # `font_glyphs.py` in der Spielschrift das passende Knopfsymbol zugewiesen
    # hat. Der vorhandene Textzeichner malt es damit von selbst mitten im Satz,
    # in Textgroesse und mit korrektem Zeilenumbruch. Die Zeichen sind im
    # deutschen Text unbenutzt und alle <= 0xFF, passen also als ein Byte in die
    # Namenstabelle.
    0xA0: chr(0xF0),   # A
    0xA1: chr(0xF1),   # B
    0xA2: chr(0xE6),   # X
    0xA3: chr(0xF8),   # Y
    0xA4: chr(0xE5),   # START
    0xA5: chr(0xE3),   # BACK
    0xA6: chr(0xF5),   # L3
    0xA7: chr(0xA1),   # R3
    0xA8: chr(0xBF),   # LB
    0xA9: chr(0xD0),   # RB
    0xAA: chr(0xD1),   # LT
    0xAB: chr(0xC6),   # RT
    0xB0: chr(0xEC),   # Steuerkreuz oben
    0xB1: chr(0xED),   # Steuerkreuz rechts
    0xB2: chr(0xEE),   # Steuerkreuz unten
    0xB3: chr(0xEF),   # Steuerkreuz links
    # Fuer die Achsen gibt es keine Symbole - die bleiben ausgeschrieben.
    0x80: "Linker Stick rechts",
    0x81: "Linker Stick links",
    0x82: "Linker Stick hoch",
    0x83: "Linker Stick runter",
    0x84: "Rechter Stick rechts",
    0x85: "Rechter Stick links",
    0x86: "Rechter Stick hoch",
    0x87: "Rechter Stick runter",
}

# Beschleuniger in CubeWnd.xrg, die die alten Namen benutzen
# Die 22 Menue-Beschleuniger in CubeWnd.xrg sprechen zwei Pad-Knoepfe ueber
# ihren Namen an. Nach der Umbenennung gibt es die alten Namen nicht mehr.
# Die Zahlenform '#162' war der erste Versuch - im Spiel meldet der Parser
#   (CMWnd::EvaluateKey) Invalid scancode definition #162
# diese Auswertung versteht sie also nicht. Stattdessen wird direkt der neue
# Name eingesetzt, das eine Sonderzeichen aus NAMES. Die Datei wird ohnehin
# binaer geschrieben.
ACCEL = {b"JOY_BUTTON_02": bytes([0xE6]),     # X
         b"JOY_BUTTON_03": bytes([0xF8])}     # Y

# --------------------------------------------------------- Plattformschalter
# Die Menuedateien tragen den originalen Praeprozessor des Entwicklers:
#   #ifdef PLATFORM_WIN_PC (18x)  #ifdef PLATFORM_XENON (12x)
#   #ifdef PLATFORM_PS3   (15x)   #ifdef PLATFORM_CONSOLE (9x)
# Welche Symbole gesetzt werden, entscheidet MSystem in einer einzigen
# Funktion (0x100b8280): sie liest das Plattformfeld `[system+0x68]`, zieht 1
# ab und springt ueber eine Tabelle in den passenden Block.
#   Plattform 1 XBOX | 2 PS2 | 3 DOLPHIN | 4 XENON | 5 PS3 | sonst WIN
# Wird der Index fest auf 3 gesetzt, definiert der Praeprozessor
# PLATFORM_CONSOLE + PLATFORM_XENON + PLATFORM_XBOX - die Registry wird also
# genau so ausgewertet wie im Xbox-360-Build. Sechs Bytes, sonst nichts; die
# Plattform des Spiels selbst bleibt unangetastet.
PLAT_PAT = bytes.fromhex("8b406883c0ff83f804")   # mov eax,[eax+0x68]; add eax,-1; cmp eax,4
PLAT_IDX = {"xenon": 3, "ps3": 4}                # Sprungtabellenindex = Plattform - 1

POOL_LO, POOL_HI = 0x10300000, 0x10301000     # Namensvorrat insgesamt
ARENA_LO, ARENA_HI = 0x10300280, 0x10300400   # Achsen 04..0F - nie belegt


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    oh = struct.unpack_from("<H", d, e + 20)[0]
    st = e + 24 + oh
    base = struct.unpack_from("<I", d, e + 24 + 28)[0]
    secs = [(struct.unpack_from("<I", d, st + 40 * i + 12)[0],
             struct.unpack_from("<I", d, st + 40 * i + 20)[0],
             struct.unpack_from("<I", d, st + 40 * i + 16)[0]) for i in range(n)]
    return secs, base


class PE:
    def __init__(self, path):
        self.data = bytearray(open(path, "rb").read())
        self.secs, self.base = sections(bytes(self.data))

    def v2o(self, v):
        for va, raw, rs in self.secs:
            if va <= v - self.base < va + rs:
                return raw + (v - self.base - va)
        raise SystemExit("VA 0x%08x nicht abgebildet" % v)

    def name_at(self, v):
        o = self.v2o(v)
        return bytes(self.data[o:o + 48]).split(NUL)[0].decode("latin-1")


def find_entries(pe):
    """{Code: (Offset des Namenszeigers, alter Zeiger)}"""
    d = bytes(pe.data)
    out = {}
    for code in NAMES:
        for m in re.finditer(re.escape(struct.pack("<II", code, code)), d):
            ptr = struct.unpack_from("<I", d, m.end())[0]
            if POOL_LO <= ptr < POOL_HI:
                if code in out:
                    raise SystemExit("Code 0x%02x mehrfach gefunden" % code)
                out[code] = (m.end(), ptr)
    fehlt = sorted(set(NAMES) - set(out))
    if fehlt:
        raise SystemExit("keine Tabelleneintraege fuer: %s"
                         % " ".join("0x%02x" % c for c in fehlt))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=None,
                    help="Spielordner - die Wurzel, in der Content und System liegen. Ohne Angabe gilt der Wert oben im Skript.")
    ap.add_argument("--platform", choices=("keiner", "xenon", "ps3"), default="keiner",
                    help="Registry-Praeprozessor als Konsole auswerten lassen")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    global GAME, MSYS, CUBE
    if a.game:
        GAME = a.game
        MSYS = os.path.join(GAME, "System", "Win32_x86", "MSystem.dll")
        CUBE = os.path.join(GAME, "Content", "GUI", "CubeWnd.xrg")

    if a.restore:
        for f in (MSYS, CUBE):
            if os.path.exists(f + BAK):
                shutil.copyfile(f + BAK, f)
                os.remove(f + BAK)
                print("zurueckgespielt:", os.path.basename(f))
            else:
                print("kein Backup:", os.path.basename(f))
        return

    # ---------------------------------------------------------- MSystem.dll
    pe = PE(MSYS + BAK if os.path.exists(MSYS + BAK) else MSYS)
    ent = find_entries(pe)

    blob, offs, cur = bytearray(), {}, ARENA_LO
    for code in sorted(NAMES):
        offs[code] = cur
        s = NAMES[code].encode("latin-1") + NUL
        blob += s
        cur += len(s)
    if cur > ARENA_HI:
        raise SystemExit("Namen passen nicht in den freien Bereich (%d > %d)"
                         % (cur - ARENA_LO, ARENA_HI - ARENA_LO))

    print("== MSystem.dll: %d Namen, %d von %d Bytes im freien Bereich =="
          % (len(NAMES), len(blob), ARENA_HI - ARENA_LO))
    for code in sorted(NAMES):
        po, ptr = ent[code]
        print("   0x%02x  %-16s -> %s" % (code, pe.name_at(ptr), NAMES[code]))

    pe.data[pe.v2o(ARENA_LO):pe.v2o(ARENA_LO) + len(blob)] = blob
    for code in sorted(NAMES):
        struct.pack_into("<I", pe.data, ent[code][0], offs[code])

    # ------------------------------------------------------ Plattformschalter
    if a.platform != "keiner":
        hits = list(re.finditer(re.escape(PLAT_PAT), bytes(pe.data)))
        if len(hits) != 1:
            raise SystemExit("Plattformschalter nicht eindeutig (%d Treffer)" % len(hits))
        o = hits[0].start()
        pe.data[o:o + 6] = (bytes([0xB8]) + struct.pack("<I", PLAT_IDX[a.platform])
                            + bytes([0x90]))
        print()
        print("== Plattformschalter ==")
        print("   Registry-Praeprozessor laeuft als %s" % a.platform.upper())
        print("   -> PLATFORM_CONSOLE und PLATFORM_%s gesetzt, PLATFORM_WIN_PC nicht mehr"
              % a.platform.upper())

    # ---------------------------------------------------------- CubeWnd.xrg
    csrc = CUBE + BAK if os.path.exists(CUBE + BAK) else CUBE
    cd = open(csrc, "rb").read()
    crlf0 = cd.count(CRLF)
    cn = cd
    print()
    print("== CubeWnd.xrg ==")
    for alt, neu in ACCEL.items():
        n = len(re.findall(re.escape(alt), cn))
        cn = cn.replace(alt, neu)
        print("   %-15s -> 0x%-4s  %dx" % (alt.decode(), neu.hex(), n))
    if cn.count(CRLF) != crlf0:
        raise SystemExit("Zeilenenden veraendert - abbrechen")
    print("   CRLF unveraendert: %d" % crlf0)

    if not a.apply:
        print()
        print("(nur Vorschau - mit --apply anwenden; Spiel muss geschlossen sein)")
        return

    for f, data in ((MSYS, bytes(pe.data)), (CUBE, cn)):
        if not os.path.exists(f + BAK):
            shutil.copyfile(f, f + BAK)
        open(f, "wb").write(data)
        print("geschrieben: %s (Backup vorhanden)" % os.path.basename(f))


if __name__ == "__main__":
    main()
