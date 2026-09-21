#!/usr/bin/env python3
"""
Knopfsymbole farbig und mit den Originalgrafiken des Spiels in die Schriften
einbauen.

Warum das geht
--------------
Der Mipmap-Kopf hat neun Felder; Feld 5 ist die Formatkennung. Die Schriften
fuehren dort 0x00040000 (A8, ein Byte je Pixel), die Knopftexturen in GUI.xtc
fuehren 0x00000800 - DXT5, nachgewiesen durch Dekodieren von GUI_Button_Y.
DXT5 braucht bei denselben Abmessungen exakt gleich viel Speicher wie A8:
512x512 sind in beiden Faellen 262144 Byte, und das gilt fuer jede Stufe bis
hinunter zu 4x4. Der Atlas laesst sich also in Farbe umschreiben, ohne dass
sich ein einziger Offset in der Datei verschiebt.

Die Symbole kommen nicht mehr aus der Zeichenfeder, sondern direkt aus
GUI.xtc - dieselben Grafiken, die die Konsolenfassung benutzt.

Die beiden kleinsten Stufen passen nicht: ein DXT5-Block ist immer 16 Byte
gross, bei 2x2 stehen aber nur 4 Byte bereit. Sie werden aus der Kette gehaengt
(Feld 'next' des letzten brauchbaren Eintrags auf 0); benutzt werden sie
ohnehin nur bei mikroskopisch kleinem Text.

    python font_color.py                Vorschau
    python font_color.py --apply
    python font_color.py --restore
"""

import argparse
import os
import shutil
import struct

GAME = r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
FONTDIR = os.path.join(GAME, "Content", "Fonts")
GUIXTC = os.path.join(GAME, "Content", "GUI", "Textures", "GUI.xtc")
FONTS = ("Text.xfc", "Subtitle.xfc", "Headings.xfc")
BAK = ".vor_symbolen"
NUL = bytes(1)
MIP = b"MIPMAP" + NUL

FMT_DXT5 = 0x00000800
FMT_A8 = 0x00040000

# Padcode, Spenderzeichen, Textur in GUI.xtc, Zuschnitt (None = Alpha-Rahmen)
GLYPHS = [
    (0xA0, 0xF0, "GUI_Button_A",      None),
    (0xA1, 0xF1, "GUI_Button_B",      None),
    (0xA2, 0xE6, "GUI_Button_X",      None),
    (0xA3, 0xF8, "GUI_Button_Y",      None),
    (0xA4, 0xE5, "GUI_Button_Start",  (29, 20, 82, 63)),   # ohne den Schriftzug
    (0xA5, 0xE3, "GUI_Button_Back",   (17, 20, 64, 58)),   # ohne den Schriftzug
    (0xA6, 0xF5, "GUI_Button_LC",     None),
    (0xA7, 0xA1, "GUI_Button_RC",     None),
    (0xA8, 0xBF, "GUI_Button_LB",     None),
    (0xA9, 0xD0, "GUI_Button_RB",     None),
    (0xAA, 0xD1, "GUI_Button_LT",     None),
    (0xAB, 0xC6, "GUI_Button_RT",     None),
    (0xB0, 0xEC, "GUI_Button_DUp",    None),
    (0xB1, 0xED, "GUI_Button_DRight", None),
    (0xB2, 0xEE, "GUI_Button_DDown",  None),
    (0xB3, 0xEF, "GUI_Button_DLeft",  None),
]

ZELLE_H = 35        # Zeilenhoehe der Schrift
SYM_H = 31          # Hoehe des Symbols in der Zelle (--groesse)
# Grossbuchstaben belegen in der Zelle die Zeilen 6..27. Das Symbol wird um
# diesen Streifen herum mittig gesetzt, sitzt also etwas tiefer als die
# Versalhoehe - so machen es die Konsolenfassungen auch.
RAND = 4            # Abstand, auf 4 gerundet - sonst mischt ein DXT-Block Farben


# --------------------------------------------------------------- DXT5-Codec
def bc3_encode_block(px):
    a = [p[3] for p in px]
    a0, a1 = max(a), min(a)
    out = bytearray([a0, a1])
    if a0 > a1:
        pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    bits = 0
    for i, v in enumerate(a):
        bits |= min(range(8), key=lambda k: abs(pal[k] - v)) << (3 * i)
    out += bits.to_bytes(6, "little")

    cols = [(p[0], p[1], p[2]) for p in px]
    lum = lambda c: c[0] * 299 + c[1] * 587 + c[2] * 114
    hell, dunkel = max(cols, key=lum), min(cols, key=lum)
    to565 = lambda c: ((c[0] >> 3) << 11) | ((c[1] >> 2) << 5) | (c[2] >> 3)
    c0, c1 = to565(hell), to565(dunkel)
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return bytes(out + c0.to_bytes(2, "little") + c1.to_bytes(2, "little") + bytes(4))
    auf = lambda v: (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63,
                     (v & 31) * 255 // 31)
    p0, p1 = auf(c0), auf(c1)
    pal4 = [p0, p1,
            tuple((2 * p0[i] + p1[i]) // 3 for i in range(3)),
            tuple((p0[i] + 2 * p1[i]) // 3 for i in range(3))]
    bits = 0
    for i, c in enumerate(cols):
        bits |= min(range(4),
                    key=lambda k: sum((pal4[k][j] - c[j]) ** 2 for j in range(3))) << (2 * i)
    return bytes(out + c0.to_bytes(2, "little") + c1.to_bytes(2, "little")
                 + bits.to_bytes(4, "little"))


def bc3_encode(bild):
    b, h = bild.size
    px = bild.load()
    aus = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, b, 4):
            blk = [px[min(bx + x, b - 1), min(by + y, h - 1)]
                   for y in range(4) for x in range(4)]
            aus += bc3_encode_block(blk)
    return bytes(aus)


def bc3_decode(data, w, h):
    from PIL import Image
    img = Image.new("RGBA", (w, h))
    px = img.load()
    i = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            a0, a1 = data[i], data[i + 1]
            ab = int.from_bytes(data[i + 2:i + 8], "little")
            pal = ([a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]) \
                if a0 > a1 else \
                ([a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255])
            c0, c1 = struct.unpack_from("<HH", data, i + 8)
            cb = struct.unpack_from("<I", data, i + 12)[0]
            auf = lambda v: (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63,
                             (v & 31) * 255 // 31)
            p0, p1 = auf(c0), auf(c1)
            cp = [p0, p1, tuple((2 * p0[k] + p1[k]) // 3 for k in range(3)),
                  tuple((p0[k] + 2 * p1[k]) // 3 for k in range(3))]
            for y in range(4):
                for x in range(4):
                    if bx + x >= w or by + y >= h:
                        continue
                    n = y * 4 + x
                    px[bx + x, by + y] = cp[(cb >> (2 * n)) & 3] + (pal[(ab >> (3 * n)) & 7],)
            i += 16
    return img


# ---------------------------------------------------------------- Container
def eintraege(d, dirOff):
    """Verzeichnis ab dirOff: [Name, Slot, next, kind, data, len, wh, fmt]."""
    aus = []
    p = dirOff
    while p + 48 <= len(d):
        name = d[p:p + 24].split(NUL)[0]
        if not name or not all(32 <= c < 127 for c in name):
            break
        nxt, kind, dat, ln, e1, e2 = struct.unpack_from("<6I", d, p + 24)
        aus.append([name.decode("latin1"), p, nxt, kind, dat, ln, e1, e2])
        p += 48
    return aus


def knopfgrafiken():
    """Die benoetigten Texturen aus GUI.xtc holen und dekodieren."""
    d = open(GUIXTC, "rb").read()
    dirOff = struct.unpack_from("<I", d, 24)[0]
    gesucht = set(g[2] for g in GLYPHS)
    aus = {}
    p = dirOff
    while p + 48 <= len(d):
        name = d[p:p + 24].split(NUL)[0].decode("latin1", "replace")
        if name in gesucht and name not in aus:
            q = p + 48
            while q < p + 48 * 6 and d[q:q + 7] != MIP:
                q += 48
            if d[q:q + 7] == MIP:
                dat = struct.unpack_from("<I", d, q + 32)[0]
                h9 = struct.unpack_from("<9I", d, dat)
                w, hh, fmt, nutz = h9[3], h9[4], h9[5], h9[7]
                vor = h9[2] - nutz
                if fmt == FMT_DXT5 and nutz == ((w + 3) // 4) * ((hh + 3) // 4) * 16:
                    aus[name] = bc3_decode(d[dat + 36 + vor:dat + 36 + vor + nutz], w, hh)
        p += 48
    fehlt = gesucht - set(aus)
    if fehlt:
        raise SystemExit("in GUI.xtc nicht gefunden: " + ", ".join(sorted(fehlt)))
    return aus


def neubau(d, dirOff, neue_daten, neue_fmt):
    """Container mit geaenderten Datenbloecken neu aufbauen.

    Die Bloecke liegen luecken- und ueberlappungsfrei hintereinander, das
    Verzeichnis haengt hinten dran und alle Zeiger sind absolute Dateioffsets.
    Aendert sich eine Blockgroesse, verschiebt sich alles dahinter - also wird
    die Datei komplett neu geschrieben und jeder Zeiger nachgezogen.

    neue_daten: {alterDatenoffset: neuer Inhalt}
    neue_fmt:   {Verzeichnisslot: neue Formatkennung}
    """
    eint = eintraege(bytes(d), dirOff)
    laenge = {}
    for e in eint:
        laenge[e[4]] = max(laenge.get(e[4], 0), e[5])
    # Der Dateikopf ist 48 Byte gross, die Daten beginnen dahinter.
    # DIRECTORYHEADER traegt Datenoffset 0 - das heisst 'keine Daten' und
    # darf nicht als Blockanfang missverstanden werden.
    kopf_ende = 48
    offsets = sorted(o for o in laenge if o >= kopf_ende)

    neu = bytearray(d[:kopf_ende])
    karte = {0: 0}
    for off in offsets:
        karte[off] = len(neu)
        neu += neue_daten.get(off, bytes(d[off:off + laenge[off]]))
    neuDir = len(neu)
    karte[dirOff] = neuDir
    delta = neuDir - dirOff

    for e in eint:
        name, slot, nxt, kind, dat, ln, e1, e2 = e
        if e[4] in neue_daten and ln:
            ln = len(neue_daten[e[4]])
        neu += name.encode("latin1").ljust(24, NUL)
        neu += struct.pack("<6I",
                           nxt + delta if nxt else 0,
                           kind + delta if kind else 0,
                           karte.get(dat, dat + delta),
                           ln, e1, neue_fmt.get(slot, e2))
    struct.pack_into("<I", neu, 24, neuDir)
    return neu


def symbolbilder():
    """Zugeschnitten und auf SYM_H skaliert; liefert {Spenderzeichen: Bild}."""
    from PIL import Image
    roh = knopfgrafiken()
    aus = {}
    for padcode, spender, texname, schnitt in GLYPHS:
        im = roh[texname]
        kasten = schnitt or im.split()[3].getbbox()
        im = im.crop(kasten)
        breite = max(4, round(im.width * SYM_H / im.height))
        aus[spender] = im.resize((breite, SYM_H), Image.LANCZOS)
    return aus


def main():
    global SYM_H
    from PIL import Image
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=None,
                    help="Spielordner - die Wurzel, in der Content und System liegen. Ohne Angabe gilt der Wert oben im Skript.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--prop", action="store_true",
                    help="PROPERTIES-Byte 13 auf 1 setzen (wie bei den Texturen)")
    ap.add_argument("--format", choices=("dxt5", "a8"), default="dxt5",
                    help="a8 baut die Datei nur neu auf, ohne Formatwechsel - "
                         "damit laesst sich der Neubau allein pruefen")
    ap.add_argument("--groesse", type=int, default=31,
                    help="Hoehe der Symbole in Pixeln (Zeile ist 35 hoch)")
    ap.add_argument("--png", default=None)
    a = ap.parse_args()
    global GAME, FONTDIR, GUIXTC
    if a.game:
        GAME = a.game
        FONTDIR = os.path.join(GAME, "Content", "Fonts")
        GUIXTC = os.path.join(GAME, "Content", "GUI", "Textures", "GUI.xtc")
    SYM_H = a.groesse

    if a.restore:
        for name in FONTS:
            f = os.path.join(FONTDIR, name)
            if os.path.exists(f + BAK):
                shutil.copyfile(f + BAK, f)
                os.remove(f + BAK)
                print("zurueckgespielt:", name)
            else:
                print("kein Backup:", name)
        return

    sym = symbolbilder()
    print("Symbole aus GUI.xtc:")
    for padcode, spender, texname, _ in GLYPHS:
        b = sym[spender]
        print("   %02X  %-18s %2dx%-2d" % (padcode, texname[11:], b.width, b.height))
    print()

    for name in FONTS:
        f = os.path.join(FONTDIR, name)
        quelle = f + BAK if os.path.exists(f + BAK) else f
        d = bytearray(open(quelle, "rb").read())
        dirOff = struct.unpack_from("<I", d, 24)[0]
        eint = eintraege(bytes(d), dirOff)
        cd = [e for e in eint if e[0] == "CHARDESC"]
        mm = [e for e in eint if e[0] == "MIPMAP"]
        pr = [e for e in eint if e[0] == "PROPERTIES"]
        if not cd or not mm:
            print("== %-14s kein CHARDESC/MIPMAP" % name)
            continue
        cd = cd[0]
        mm.sort(key=lambda e: -e[5])
        gross = mm[0]
        # Masse aus dem Mipmap-Kopf: dort stehen Breite und Hoehe eindeutig.
        # Das Verzeichnisfeld packt beide in ein Wort, aber in umgekehrter
        # Reihenfolge - bei Headings.xfc (512x256) faellt das sofort auf.
        breite, hoehe = struct.unpack_from("<II", d, gross[4] + 12)
        roh = breite * hoehe
        print("== %-14s Atlas %dx%d, %d Stufen" % (name, breite, hoehe, len(mm)))

        px = bytes(d[gross[4] + 36: gross[4] + 36 + roh])
        alpha = Image.frombytes("L", (breite, hoehe), px)
        rgba = Image.new("RGBA", (breite, hoehe), (255, 255, 255, 0))
        rgba.putalpha(alpha)

        n = cd[5] // 34
        wo = {}
        for i in range(n):
            code = struct.unpack_from("<H", d, cd[4] + i * 34 + 32)[0]
            wo[code] = i

        # groesstes leeres Zeilenband suchen
        leer = [y for y in range(hoehe) if max(px[y * breite:(y + 1) * breite]) == 0]
        band = None
        if leer:
            baender, s0, p = [], leer[0], leer[0]
            for y in leer[1:]:
                if y != p + 1:
                    baender.append((s0, p))
                    s0 = y
                p = y
            baender.append((s0, p))
            band = max(baender, key=lambda b: b[1] - b[0])
        if band is None or band[1] - band[0] + 1 < ZELLE_H + 2 * RAND:
            print("   zu wenig freier Platz")
            continue
        print("   freies Band Zeile %d..%d (%d Zeilen)"
              % (band[0], band[1], band[1] - band[0] + 1))

        y = (band[0] + RAND + 3) & ~3
        x, gesetzt = 0, 0
        for padcode, spender, texname, _ in GLYPHS:
            if spender not in wo:
                print("   Spenderzeichen 0x%02X fehlt - %s uebersprungen" % (spender, texname))
                continue
            bild = sym[spender]
            gb = (bild.width + 3) & ~3
            if x + gb > breite:
                x = 0
                y = (y + ZELLE_H + RAND + 3) & ~3
            if y + ZELLE_H > band[1]:
                print("   Platz reicht nicht mehr fuer %s" % texname)
                break
            rgba.paste(bild, (x, y + (6 + 27) // 2 - SYM_H // 2 + 1))
            e = cd[4] + wo[spender] * 34
            struct.pack_into("<h", d, e + 2, -5)
            struct.pack_into("<6f", d, e + 4,
                             x / breite, y / hoehe,
                             (x + bild.width) / breite, (y + ZELLE_H) / hoehe,
                             float(bild.width), float(ZELLE_H))
            struct.pack_into("<h", d, e + 30, bild.width + 2)
            x += gb + RAND
            gesetzt += 1
        print("   %d Symbole gesetzt" % gesetzt)

        if a.png:
            p2 = a.png.replace(".png", "_%s.png" % name.split(".")[0])
            hg = Image.new("RGB", rgba.size, (30, 30, 30))
            hg.paste(rgba, mask=rgba.split()[3])
            hg.save(p2)
            print("   Atlas:", p2)

        # ---- alle Stufen neu erzeugen --------------------------------------
        # Aufbau exakt wie bei den Spieltexturen: 36-Byte-Kopf, dann ein
        # 16-Byte-Vorspann (4, Groesse, 0, 16) und danach die DXT5-Bloecke.
        # Der Vorspann hat der Schrift bisher gefehlt - deshalb der Absturz.
        # Die kleinsten Stufen belegen immer mindestens einen Block, also
        # 16 Byte; auch das machen die Texturen so.
        neue_daten, neue_fmt = {}, {}
        for e in mm:
            b2, h2 = struct.unpack_from("<II", d, e[4] + 12)
            stufe = rgba if (b2, h2) == (breite, hoehe) else                 rgba.resize((max(1, b2), max(1, h2)), Image.LANCZOS)
            if a.format == "dxt5":
                if b2 < 4 or h2 < 4:
                    stufe = stufe.resize((4, 4), Image.LANCZOS)
                daten = bc3_encode(stufe)
                fmt, f1, vorspann = FMT_DXT5, 0x5000, struct.pack("<4I", 4, len(daten), 0, 16)
            else:
                daten = stufe.split()[3].tobytes()
                fmt, f1, vorspann = FMT_A8, 0, b""
            kopf = struct.pack("<9I", 0x400, f1, len(vorspann) + len(daten),
                               b2, h2, fmt, 0, len(daten), 1)
            neue_daten[e[4]] = kopf + vorspann + daten
            neue_fmt[e[1]] = fmt
        print("   %d Stufen als %s neu erzeugt" % (len(mm), a.format.upper()))

        if a.prop and pr:
            d[pr[0][4] + 13] = 1 if a.format == "dxt5" else 0
            print("   PROPERTIES[13] = %d" % d[pr[0][4] + 13])

        d = neubau(d, dirOff, neue_daten, neue_fmt)
        print("   Datei neu aufgebaut: %d Byte" % len(d))

        if a.apply:
            if not os.path.exists(f + BAK):
                shutil.copyfile(f, f + BAK)
            open(f, "wb").write(bytes(d))
            print("   geschrieben")

    if not a.apply:
        print()
        print("(nur Vorschau - mit --apply anwenden; Spiel muss geschlossen sein)")


if __name__ == "__main__":
    main()
