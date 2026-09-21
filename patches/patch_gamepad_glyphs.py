#!/usr/bin/env python3
"""
Riddick AODA (PC): echte Xbox-Button-Glyphen in Tastenhinweisen.

Was das Spiel schon kann
------------------------
Der komplette Konsolen-Pfad steckt schon im PC-Build:
  * eine Funktion bildet Tastencodes auf Texturnamen ab
    ("GUI_Button_A", "GUI_Button_LB", ...)
  * die Texturen liegen in Content\\GUI\\Textures\\GUI.xtc
Benutzt wird auf dem PC aber nur der Tastenkappen-Pfad: CRC_Util2D loest die
Aktion zu einem Tastencode auf, holt per GetLocalizedKeyName einen Textnamen
und zeichnet ihn in eine "pc_keykit"-Kappe.

WICHTIG: CRC_Util2D ist geteilter Quellcode und liegt **doppelt** vor - einmal
in GameClasses_Win32_x86.dll und einmal in GameWorld_Win32_x86.dll. Welche
Kopie zeichnet, haengt vom Aufrufer ab: die Ingame-Hinweise (Fokusrahmen)
kommen aus GameWorld. Darum patcht dieses Skript standardmaessig **beide**.

Zwei Ketten in CRC_Util2D zeichnen Tastenhinweise:
  Kette 1  vtable[0x104] (aufloesen)  ->  vtable[0x10c] (zeichnen)
  Kette 2  vtable[0x114] (aufloesen)  ->  vtable[0x11c] (zeichnen)
Beide Aufloeser kennen bereits einen Icon-Index: fuer die Mauscodes
0xF0/0xF1/0xF2 setzen sie edi=3/4/5, ueberspringen den Text, und die
Zeichenroutine setzt stattdessen "pc_keykit_mouse_*" als Textur. Genau da
haengen sich die Hooks ein.

Hooks
-----
  h1   Kette-1-Aufloeser: Gamepad-Code (0x80..0xB3) -> edi = Code, Text weg
  h2   Kette-1-Zeichner:  Icon-Index >= 0x80 -> Texturnamen holen und setzen
  h3   Kette-2-Aufloeser: Gamepad-Code -> Textur ueber vtable[0x68] setzen,
                          edi = 3 (dort heisst das "Textur zeichnen, kein Text")
  pp1/pp2 (--prefer-pad)  fragen zuerst ACTION_<NAME>2 ab (Gamepad-Slot) und
                          nehmen den Wert, wenn er im Gamepad-Bereich liegt

Ausserdem wird die Zuordnungstabelle fuer die Codes 0xA4..0xAB geradegezogen;
dort stand eine veraltete Reihenfolge, und LT/RT fehlten ganz.

Alle Einsprungstellen werden per Bytemuster gesucht, nicht fest verdrahtet -
so passt das Skript auf beide DLLs. Der neue Code liegt in einer zusaetzlichen
PE-Sektion und ist positionsunabhaengig (nur relative jmp/call), es sind also
keine Relocation-Eintraege noetig.

    python patch_gamepad_glyphs.py                     # bauen + pruefen
    python patch_gamepad_glyphs.py --prefer-pad --apply
    python patch_gamepad_glyphs.py --restore
"""

import argparse
import os
import re
import shutil
import struct

GAME = r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena"
TARGETS = [os.path.join(GAME, 'Content', 'GameClasses_Win32_x86.dll'),
           os.path.join(GAME, 'Content', 'GameWorld_Win32_x86.dll')]
HERE = os.path.dirname(os.path.abspath(__file__))

SEC_NAME = b'.pglyph\x00'

# 1=LT 2=RT 3=A 4=B 5=X 6=Y 7=LB 8=RB 9=Back 10=Start 11=Stickklick 16=nichts
TABLE_AT   = 0x20                # Eintrag fuer Code 0xA0
TABLE_ORIG = bytes([3, 4, 5, 6,  7, 8, 9, 10, 11, 11, 16, 16])
TABLE_NEW  = bytes([3, 4, 5, 6, 10, 9, 11, 11,  7,  8,  1,  2])
#                   A  B  X  Y  ST BK L3  R3  LB  RB  LT  RT


# ---------------------------------------------------------------- PE-Huelle
class PE:
    def __init__(self, path):
        self.path = path
        self.data = bytearray(open(path, 'rb').read())
        d = self.data
        self.e_lfanew = struct.unpack_from('<I', d, 0x3c)[0]
        self.nsec = struct.unpack_from('<H', d, self.e_lfanew + 6)[0]
        opthdr = struct.unpack_from('<H', d, self.e_lfanew + 20)[0]
        self.optoff = self.e_lfanew + 24
        self.sectbl = self.optoff + opthdr
        self.base = struct.unpack_from('<I', d, self.optoff + 28)[0]
        self.sec_align = struct.unpack_from('<I', d, self.optoff + 32)[0]
        self.file_align = struct.unpack_from('<I', d, self.optoff + 36)[0]
        self.size_of_image = struct.unpack_from('<I', d, self.optoff + 56)[0]
        self.secs = []
        for i in range(self.nsec):
            b = self.sectbl + 40 * i
            self.secs.append((struct.unpack_from('<I', d, b + 12)[0],   # va
                              struct.unpack_from('<I', d, b + 8)[0],    # vsize
                              struct.unpack_from('<I', d, b + 20)[0],   # raw
                              struct.unpack_from('<I', d, b + 16)[0]))  # rsize

    def va2off(self, va):
        r = va - self.base
        for v, vs, p, rs in self.secs:
            if v <= r < v + max(vs, rs):
                return p + (r - v)
        raise SystemExit('VA 0x%08x nicht in einer Sektion' % va)

    def off2va(self, o):
        for v, vs, p, rs in self.secs:
            if p <= o < p + rs:
                return self.base + v + (o - p)
        return None

    def rel(self, at, opsize=1):
        """Ziel eines rel32-Sprungs/Aufrufs, dessen Opcode bei `at` beginnt."""
        o = self.va2off(at)
        r = struct.unpack_from('<i', self.data, o + opsize)[0]
        return at + opsize + 4 + r


# ------------------------------------------------------- Stellen aufspueren
def locate(pe):
    d = bytes(pe.data)
    s = {}

    m = list(re.finditer(re.escape(bytes.fromhex('8b44240483c08083f833')), d))
    if len(m) != 1:
        raise SystemExit('Mapper nicht eindeutig (%d Treffer)' % len(m))
    s['code2tex'] = pe.off2va(m[0].start())
    # movzx eax, byte ptr [eax + <tabelle>]   liegt 12 Bytes weiter
    s['table_va'] = struct.unpack_from('<I', d, m[0].start() + 15)[0]

    # Sprungtabelle hinter code2tex: movzx eax,[eax+<Bytetabelle>] /
    # jmp [eax*4+<Sprungtabelle>]. Beide Verweise stehen als absolute Adressen
    # im Code und **haben Relocations** (geprueft) - in die Tabellenslots darf
    # also eine Hoehlenadresse geschrieben werden, der Lader zieht sie nach.
    s['jt_va'] = struct.unpack_from('<I', d, pe.va2off(s['code2tex']) + 0x16)[0]

    res = [pe.off2va(x.start())
           for x in re.finditer(rb'\x3d\xf0\x00\x00\x00\x75\x08\x8d\x7b\x01', d)]
    if len(res) != 2:
        raise SystemExit('Aufloeser nicht eindeutig (%d Treffer)' % len(res))
    for va in res:
        noff = struct.unpack_from('<I', d, pe.va2off(va - 15) + 3)[0]
        tag = '1' if noff == 0x144 else '2'
        s['h%s_at' % tag] = va
        s['h%s_back' % tag] = va + 5
        s['h%s_notext' % tag] = pe.rel(va + 10)          # e9 rel32
        s['pp%s_at' % tag] = va - 15
        s['pp%s_noff' % tag] = noff
        s['getvaluei'] = pe.rel(va - 5)                  # e8 rel32
    if 'h1_at' not in s or 'h2_at' not in s:
        raise SystemExit('Aufloeser-Zuordnung fehlgeschlagen')
    # h2 ist in dieser Benennung Kette 2 -> zur Klarheit umbenennen
    s['h3_at'], s['h3_back'], s['h3_notext'] = s.pop('h2_at'), s.pop('h2_back'), s.pop('h2_notext')

    m = list(re.finditer(rb'\x83\xf8\x03\xdd\xd8\x0f\x84', d))
    if len(m) != 1:
        raise SystemExit('Zeichner-Weiche nicht eindeutig (%d Treffer)' % len(m))
    sw = pe.off2va(m[0].start())
    s['h2_at'] = sw
    s['h2_back'] = sw + 5
    # cmp eax,3(3) fstp(2) je(6) cmp eax,4(3) je(6) cmp eax,5(3) jne(6)
    s['h2_noicon'] = pe.rel(sw + 23, 2)                  # 0f 85 rel32
    # danach: cmp eax,eax(2) jne(2) push imm32(5) -> dahinter setzt SetTexture an
    s['h2_settex'] = sw + 29 + 2 + 2 + 5

    # dritter Aufloeser: CRC_Util2D::vtable[0xE8] liefert nur den Tastennamen
    # als Text. Darueber laufen die Menue-Hinweise.
    m = list(re.finditer(rb'\x8b\x8c\x24\x1c\x01\x00\x00\x51\x8b\xc8\xe8....'
                         rb'\x8b\xb4\x24\x18\x01\x00\x00\x50\x56\xe8', d, re.S))
    if len(m) != 1:
        raise SystemExit('Namens-Aufloeser nicht eindeutig (%d Treffer)' % len(m))
    s['g1_at'] = pe.off2va(m[0].start())
    s['g1_back'] = s['g1_at'] + 15                       # hinter dem GetValuei-Aufruf
    s['g1_noff'] = 0x11c

    # Weiche im Kette-2-Zeichner (cmp edi,1 / je +5). Kommt mehrfach vor -
    # die richtige liegt kurz hinter dem Kette-2-Aufloeser.
    cand = [pe.off2va(x.start()) for x in re.finditer(rb'\x83\xff\x01\x74\x05', d)]
    cand = sorted(v for v in cand if v and 0 < v - s['h3_at'] < 0x800)
    if not cand:
        raise SystemExit('Zeichner-2-Weiche nicht gefunden')
    s['d2_at'] = cand[0]
    s['d2_next'] = cand[0] + 5                           # cmp edi,2 ...
    s['d2_je'] = cand[0] + 10                            # Ziel des je

    # vierter Pfad: der Textbaustein-Aufloeser (Hilfe- und Tutorialtexte). Er
    # setzt den Texturnamen als Attribut - der Konsolenweg fuer Glyphen mitten
    # im Text. Nur die Slot-Wahl stimmt nicht.
    g2 = []
    for m in re.finditer(rb'\xff\xd0\x50\x8b\xce\xe8....\x85\xc0\x74', d, re.S):
        co = m.start() + 5
        va = pe.off2va(co)
        if va and va + 5 + struct.unpack_from('<i', d, co + 1)[0] == s['getvaluei']:
            g2.append(va)
    if len(g2) != 1:
        raise SystemExit('Textpfad-Abfrage nicht eindeutig (%d Treffer)' % len(g2))
    s['g2_call'] = g2[0]

    # Hilfe-Leiste ("HILFE  F1"). Sie ruft den Kette-1-Zeichner direkt auf und
    # uebergibt als Icon-Index die Konstante 0 - deshalb landet sie immer im
    # Textzweig. Die Tastenbezeichnung "F1" steht als Literal im Datensegment,
    # gleich hinter dem Kopfzeilen-Schluessel. Beides gibt es nur in GameClasses.
    m = list(re.finditer(re.escape(bytes.fromhex('6a0083ec088b168b920c010000')), d))
    if len(m) == 1:
        s['hb_at'] = pe.off2va(m[0].start())      # push 0 ; sub esp,8  (5 Bytes)
        s['hb_back'] = s['hb_at'] + 5
    elif len(m) > 1:
        raise SystemExit('Hilfe-Leiste nicht eindeutig (%d Treffer)' % len(m))
    # Konsolenknopf-Schalter: 0x10 vor code2tex liegt eine Funktion, die nur
    # aus "xor al,al / ret" besteht - sie liefert also immer falsch. Ihr
    # Ergebnis gibt im CONTROLLER-Aufloeser einen weiteren Zweig frei, der so
    # nie laeuft. Sieht nach einem Kompilierschalter der Konsolenfassung aus.
    # Der "Ueberspringen"-Hinweis der Zwischensequenzen fragt fest die
    # Nachlade-Belegung ab (auf der Konsole B). Im PC-Build loest aber
    # ACTION_USE aus - der Hinweis zeigt also den falschen Knopf. Zwei
    # Fundstellen, erkennbar an "mov eax,[edx+0x68]; push <Name>".
    skip = []
    for m in re.finditer(re.escape(bytes.fromhex('8b4268')) + bytes([0x68]), d):
        ptr = struct.unpack_from('<I', d, m.end())[0]
        po = pe.va2off(ptr) if pe.off2va(m.start()) else None
        if po and bytes(d[po:po + 14]) == b'ACTION_RELOAD' + bytes(1):
            skip.append(pe.off2va(m.end()))
    u = list(re.finditer(re.escape(b'ACTION_USE' + bytes(1)), d))
    if skip and len(u) == 1:
        s['skip_at'] = skip
        s['skip_use'] = pe.off2va(u[0].start())

    # Der Eingabesammler setzt das Nachlade-Bit ueber eine Namensabfrage:
    #   push 0 / or ebx,4 / push "ACTION_RELOAD" / ... / call <gedrueckt?>
    # Liegt die Hilfe auf demselben Knopf, meldet diese Abfrage nichts mehr -
    # Nachladen ist tot, und das Ueberspringen der Zwischensequenz gleich mit,
    # weil es an demselben Bit haengt. Die Abfrage wird deshalb auf
    # "ACTION_HELP" umgebogen; der Knopf ist derselbe, das Bit kommt zurueck.
    rl = []
    for m in re.finditer(re.escape(bytes.fromhex('6a0083cb0468')), d):
        ptr = struct.unpack_from('<I', d, m.end())[0]
        po = pe.va2off(ptr) if pe.off2va(m.start()) else None
        if po and bytes(d[po:po + 14]) == b'ACTION_RELOAD' + bytes(1):
            rl.append(pe.off2va(m.end()))
    if rl:
        s['rl_at'] = rl

    # Einstieg des Symbolzeichners (vtable[0x10c]) - fuer den Kalibrierbau.
    m = list(re.finditer(re.escape(bytes.fromhex(
        '81ecc8000000d98424e400000053')), d))
    if len(m) == 1:
        s['cal_at'] = pe.off2va(m[0].start())
        s['cal_back'] = s['cal_at'] + 6        # hinter "sub esp,0xc8"

    # Einsprung des Zeilenzeichners CRC_Util2D::vtable[0xf0]. Zehn Argumente,
    # __thiscall, ret 0x28. Die ersten beiden Befehle sind zusammen 10 Bytes -
    # genug fuer einen Sprung plus Fuellbytes.
    m = list(re.finditer(re.escape(bytes.fromhex('8b442418f30f10442428')), d))
    if len(m) == 1:
        s['il_at'] = pe.off2va(m[0].start())
        s['il_back'] = s['il_at'] + 10

    # Schreibfehler im Original: die Textur im Archiv heisst "GUI_Button_DUp",
    # die DLL fragt aber "GUI_Button_DUP" - bei DLeft/DDown/DRight stimmt es.
    # Deshalb bleibt das Symbol fuer Steuerkreuz-oben leer. Ein Byte.
    m = list(re.finditer(re.escape(b'GUI_Button_DUP' + bytes(1)), d))
    if len(m) == 1:
        s['dup_at'] = pe.off2va(m[0].start() + 13)

    cb = s['code2tex'] - 0x10
    if bytes(d[pe.va2off(cb):pe.va2off(cb) + 3]) == bytes.fromhex('32c0c3'):
        s['cbtn'] = cb

    f1 = list(re.finditer(re.escape(bytes([0xa7]) + b'LGAMEMSG_HELP' + bytes(2) + b'F1' + bytes(1)), d))
    if len(f1) == 1:
        s['hb_f1'] = pe.off2va(f1[0].start() + 16)

    # Anfang der HUD-Funktion (laeuft jedes Bild). Anker ist
    # "push ecx / mov eax,0x1924" - das kommt zweimal vor, die HUD-Fassung ist
    # die kurz vor der Hilfe-Leiste. Beide Befehle sind frei von absoluten
    # Adressen, lassen sich also gefahrlos in die Hoehle kopieren (die DLL wird
    # zur Laufzeit verschoben, Relocations gibt es in der Hoehle keine).
    if 'hb_at' in s:
        kand = [pe.off2va(x.start())
                for x in re.finditer(re.escape(bytes.fromhex('51b824190000')), d)]
        kand = [v for v in kand if v and 0 < s['hb_at'] - v < 0x2000]
        if len(kand) == 1:
            s['hz_at'] = kand[0]
            s['hz_back'] = kand[0] + 6

    # Belegungs-Zwischenspeicher: GameWorld holt einmalig ueber GetValuei die
    # Codes aller Aktionen und legt sie im Objekt ab - ACTION_RELOAD landet in
    # [this+0x13c]. Wer diese Zelle im Spiel liest, ist statisch nicht zu
    # finden (der Offset kommt hundertfach als gewoehnlicher Strukturoffset
    # vor). Fuer die Messung mit dem Debugger reicht es, den Objektzeiger
    # sichtbar zu machen: der Haken schreibt ihn in die Hoehle.
    m = list(re.finditer(re.escape(bytes.fromhex('8bce89873c010000')), d))
    if len(m) == 1:
        s['tr_at'] = pe.off2va(m[0].start() + 2)      # das mov selbst
        s['tr_back'] = s['tr_at'] + 6

    # Skriptausfuehrung. Die Engine startet ein Skript ueber die Folge
    #   push 0 / push "ConExecute" / sub esp,8 / mov ecx,esp
    #   push <Skript> / call <CStr-Konstruktor> / call <Ausfuehren>
    # Vorbild: GameWorld 0x10151dd0 ("press(button4)").
    cx = d.find(b'ConExecute' + bytes(1))
    if cx >= 0:
        cxva = pe.off2va(cx)
        for m in re.finditer(re.escape(bytes([0x68]) + struct.pack('<I', cxva)), d):
            teil = d[m.end():m.end() + 0x40]
            if not teil.startswith(bytes.fromhex('83ec088bcc')):
                continue
            rufe = [k.start() for k in re.finditer(re.escape(bytes([0xe8])), teil)]
            if len(rufe) < 2:
                continue
            ctor = pe.off2va(m.end() + rufe[0]) + 5 + struct.unpack_from(
                '<i', teil, rufe[0] + 1)[0]
            exe = pe.off2va(m.end() + rufe[1]) + 5 + struct.unpack_from(
                '<i', teil, rufe[1] + 1)[0]
            s['cstr_ctor'], s['conexec'] = ctor, exe
            break

    # Der Zweig, der zuschlaegt, wenn der gedrueckte Code der Belegung von
    # ACTION_GUI_CANCEL entspricht. Genau hier bietet die Konsole in der
    # Infobox die Hilfe an (A = weiterspielen, B = Hilfe).
    gc = d.find(b'ACTION_GUI_CANCEL' + bytes(1))
    if gc >= 0:
        gcva = pe.off2va(gc)
        for m in re.finditer(re.escape(bytes([0x68]) + struct.pack('<I', gcva)), d):
            teil = d[m.end():m.end() + 20]
            # mov ecx,ebp / call / cmp [esp+0x14],eax / jne rel8
            if teil[:2] != bytes.fromhex('8bcd') or teil[2] != 0xe8:
                continue
            if teil[7:12] != bytes.fromhex('3944241475'):
                continue
            o = m.end() + 13                       # hinter dem jne
            if bytes(d[o:o + 5]) != bytes.fromhex('33c085f67e'):
                continue
            s['gc_at'] = pe.off2va(o)
            s['gc_jle'] = pe.off2va(o + 6) + struct.unpack_from('<b', d, o + 5)[0]
            s['gc_back'] = pe.off2va(o + 6)
            break

    # ---------------------------------------------------------------- Rumble
    # Der Rumble-Verteiler steht nur in GameClasses (0x102c5120). Er prueft
    # GAME_VIBRATION, baut aus der Kennung 1..29 den Effektnamen in einen CStr
    # - und wirft ihn weg. Auf der Xbox 360 ging der Name in die
    # Vibrationsausgabe; der PC-Port hat sie herausgenommen (XInputSetState
    # kommt in keiner PC-Binaerdatei vor, die 360 importiert dagegen
    # XamInputSetState, Ordinal 0x192 aus xam.xex).
    # Eingehaengt wird unmittelbar vor der Sprungtabelle, also **hinter** der
    # GAME_VIBRATION-Pruefung - der Menuepunkt "Vibration" wirkt weiter.
    #     mov ecx,[ebp+8] / lea eax,[ecx-1] / cmp eax,0x1c      (9 Byte)
    m = list(re.finditer(re.escape(bytes.fromhex('8b4d088d41ff83f81c')), d))
    if len(m) == 1:
        s['rb_at'] = pe.off2va(m[0].start())
        s['rb_back'] = pe.off2va(m[0].start() + 9)
        iat = pe_imports(pe, d)
        if 'LoadLibraryA' in iat and 'GetProcAddress' in iat:
            s['iat_load'] = iat['LoadLibraryA']
            s['iat_proc'] = iat['GetProcAddress']
        else:
            del s['rb_at']
    return s


def pe_imports(pe, d):
    """{Funktionsname: IAT-Adresse} - fuer Aufrufe aus der Hoehle heraus."""
    imp = struct.unpack_from('<I', d, pe.optoff + 104)[0]
    aus = {}
    i = imp
    while True:
        o = pe.va2off(pe.base + i)
        oft, _a, _b, nrva, first = struct.unpack_from('<IIIII', d, o)
        if not (oft or first):
            break
        t = pe.va2off(pe.base + (oft or first))
        a = pe.base + first
        while True:
            th = struct.unpack_from('<I', d, t)[0]
            if not th:
                break
            if not (th & 0x80000000):
                no = pe.va2off(pe.base + th) + 2
                aus[d[no:d.index(b'\0', no)].decode('latin1')] = a
            t += 4
            a += 4
        i += 20
    return aus


# --------------------------------------------------------- Mini-Assembler
class Asm:
    def __init__(self, base):
        self.base, self.buf, self.labels, self.fix = base, bytearray(), {}, []
        self.diffs = []

    def label(self, n):
        self.labels[n] = self.base + len(self.buf)

    def raw(self, b):
        self.buf.extend(b)

    def _rel(self, t):
        self.fix.append((len(self.buf), t)); self.buf.extend(b'\0\0\0\0')

    def jmp(self, t):
        self.raw(b'\xe9'); self._rel(t)

    def call(self, t):
        self.raw(b'\xe8'); self._rel(t)

    def jcc(self, cc, t):
        self.raw(bytes((0x0f, cc))); self._rel(t)

    def disp(self, target, anchor):
        """4-Byte-Abstand zweier Label - fuer positionsunabhaengige Datenzugriffe."""
        self.diffs.append((len(self.buf), target, anchor)); self.raw(bytes(4))

    def resolve(self):
        for off, t in self.fix:
            dst = self.labels[t] if isinstance(t, str) else t
            struct.pack_into('<i', self.buf, off, dst - (self.base + off + 4))
        for off, t, anc in self.diffs:
            struct.pack_into('<i', self.buf, off, self.labels[t] - self.labels[anc])
        return bytes(self.buf)


JB, JAE, JZ, JA, JLE = 0x82, 0x83, 0x84, 0x87, 0x8e
JNE, JBE = 0x85, 0x86

# Wie lange nach dem Zeichnen des Hilfe-Balkens gilt die Hilfe als
# angeboten. rdtsc-Takte; bei 3 GHz sind das gut 0,35 Sekunden.
HELP_FENSTER = 0x40000000


PROBE = {'pp1': 0xA0, 'pp2': 0xA1, 'g1': 0xA2, 'g2': 0xA3}


def build_cave(base, s, prefer_pad, diagnose, probe=False, help_code=0xA1,
               calibrate=False, cal1=60.0, cal2=-60.0, inline=True,
               trace_reload=False, help_rebind=True,
               bind_help='', bind_reload='', stick_icons=True,
               rumble=True):
    a = Asm(base)

    a.label('h1')
    a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JB, 'h1_orig')      # cmp eax,0x80
    a.raw(b'\x3d\xb4\x00\x00\x00'); a.jcc(JAE, 'h1_orig')     # cmp eax,0xB4
    a.raw(b'\x8b\xf8')                                        # mov edi,eax
    a.jmp(s['h1_notext'])
    a.label('h1_orig')
    a.raw(b'\x3d\xf0\x00\x00\x00')                            # cmp eax,0xF0
    a.jmp(s['h1_back'])

    a.label('h2')
    a.raw(b'\xdd\xd8')                                        # fstp st(0)
    a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JAE, 'h2_have')      # Index ist schon ein Code
    # sonst: gemerkten Code aus dem Namens-Aufloeser nehmen
    a.raw(b'\x51\x52')                                        # push ecx; push edx
    a.raw(b'\xe8' + bytes(4)); a.label('h2p'); a.raw(b'\x59')  # call $+5; pop ecx
    a.raw(b'\x8b\x91'); a.disp('gcode', 'h2p')                # mov edx,[ecx+off]
    a.raw(b'\x85\xd2'); a.jcc(JZ, 'h2_no')
    a.raw(b'\xc7\x81'); a.disp('gcode', 'h2p'); a.raw(bytes(4))
    a.raw(b'\x8b\xc2\x5a\x59')                                # mov eax,edx; pop edx; pop ecx
    a.jmp('h2_have')
    a.label('h2_no'); a.raw(b'\x5a\x59'); a.jmp('h2_orig')    # pop edx; pop ecx
    a.label('h2_have')
    a.raw(b'\x50'); a.call(s['code2tex']); a.raw(b'\x83\xc4\x04')
    a.raw(b'\x85\xc0'); a.jcc(JZ, 'h2_none')
    a.raw(b'\x50'); a.jmp(s['h2_settex'])
    a.label('h2_none'); a.jmp(s['h2_noicon'])
    a.label('h2_orig'); a.raw(b'\x83\xf8\x03'); a.jmp(s['h2_back'])

    a.label('h3')
    a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JB, 'h3_orig')
    a.raw(b'\x3d\xb4\x00\x00\x00'); a.jcc(JAE, 'h3_orig')
    a.raw(b'\x50\x50'); a.call(s['code2tex']); a.raw(b'\x83\xc4\x04')
    a.raw(b'\x85\xc0'); a.jcc(JZ, 'h3_restore')
    a.raw(b'\x50\x8b\xcd\x8b\x55\x00\xff\x52\x68')            # SetTexture(this)
    a.raw(b'\x58\xbf\x03\x00\x00\x00')                        # pop eax; mov edi,3
    a.jmp(s['h3_notext'])
    a.label('h3_restore'); a.raw(b'\x58')
    a.label('h3_orig'); a.raw(b'\x3d\xf0\x00\x00\x00'); a.jmp(s['h3_back'])

    if prefer_pad:
        for tag in ('1', '2'):
            noff = s['pp%s_noff' % tag] + 8
            a.label('pp' + tag)
            a.raw(b'\x53\x56\x8b\xf0')                        # push ebx,esi; mov esi,eax
            a.raw(b'\x8b\x8c\x24' + struct.pack('<I', noff))
            a.raw(b'\x83\xec\x40\x8b\xdc\x33\xd2')            # sub esp,0x40; mov ebx,esp; xor edx,edx
            a.label('cp' + tag)
            a.raw(b'\x8a\x04\x11\x88\x04\x13\x42\x84\xc0'); a.jcc(JZ, 'ce' + tag)
            a.raw(b'\x83\xfa\x30'); a.jcc(JB, 'cp' + tag)
            a.raw(b'\xc6\x04\x13\x00\x42')
            a.label('ce' + tag)
            a.raw(b'\xc6\x44\x13\xff\x32\xc6\x04\x13\x00')    # "...2\0"
            a.raw(b'\x53\x8b\xce'); a.call(s['getvaluei']); a.raw(b'\x83\xc4\x40')
            a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JB, 'pl' + tag)
            a.raw(b'\x3d\xb4\x00\x00\x00'); a.jcc(JB, 'pd' + tag)
            a.label('pl' + tag)
            a.raw(b'\x8b\x8c\x24' + struct.pack('<I', noff))
            a.raw(b'\x51\x8b\xce'); a.call(s['getvaluei'])
            if diagnose:
                a.raw(b'\xb8\xa2\x00\x00\x00')                # mov eax,0xA2 (X)
            a.label('pd' + tag)
            a.raw(b'\x5e\x5b')                                # pop esi; pop ebx
            a.jmp(s['h1_at'] if tag == '1' else s['h3_at'])

    # ---- Menue-Pfad -------------------------------------------------------
    # g1: der dritte Aufloeser (vtable[0xE8]) liefert nur Text. Wir fragen hier
    # ebenfalls zuerst den Gamepad-Slot ab und merken den Code in 'gcode'.
    noff = s['g1_noff'] + 8
    a.label('g1')
    a.raw(b'\x53\x56\x8b\xf0')                                # push ebx,esi; mov esi,eax
    a.raw(b'\x8b\x8c\x24' + struct.pack('<I', noff))
    a.raw(b'\x83\xec\x40\x8b\xdc\x33\xd2')
    a.label('gcp')
    a.raw(b'\x8a\x04\x11\x88\x04\x13\x42\x84\xc0'); a.jcc(JZ, 'gce')
    a.raw(b'\x83\xfa\x30'); a.jcc(JB, 'gcp')
    a.raw(b'\xc6\x04\x13\x00\x42')
    a.label('gce')
    a.raw(b'\xc6\x44\x13\xff\x32\xc6\x04\x13\x00')
    a.raw(b'\x53\x8b\xce'); a.call(s['getvaluei']); a.raw(b'\x83\xc4\x40')
    a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JB, 'gpl')
    a.raw(b'\x3d\xb4\x00\x00\x00'); a.jcc(JB, 'grec')
    a.label('gpl')
    a.raw(b'\x8b\x8c\x24' + struct.pack('<I', noff))
    a.raw(b'\x51\x8b\xce'); a.call(s['getvaluei'])
    a.label('grec')
    if probe:
        a.raw(bytes([0xb8]) + struct.pack('<I', PROBE['g1']))
    # Code merken (0, wenn es kein Gamepad-Code ist - sonst bleibt ein alter stehen)
    a.raw(b'\x51\x52')                                        # push ecx; push edx
    a.raw(b'\x8b\xd0\x81\xfa\x80\x00\x00\x00')                # mov edx,eax; cmp edx,0x80
    a.jcc(JB, 'gz')
    a.raw(b'\x81\xfa\xb4\x00\x00\x00'); a.jcc(JB, 'gs')
    a.label('gz'); a.raw(b'\x33\xd2')                         # xor edx,edx
    a.label('gs')
    a.raw(b'\xe8' + bytes(4)); a.label('g1p'); a.raw(b'\x59')  # call $+5; pop ecx
    a.raw(b'\x89\x91'); a.disp('gcode', 'g1p')                # mov [ecx+off],edx
    a.raw(b'\x5a\x59\x5e\x5b')                                # pop edx,ecx,esi,ebx
    a.jmp(s['g1_back'])

    # d2: Weiche im Kette-2-Zeichner. Liegt ein gemerkter Code vor, wird die
    # Glyphentextur gesetzt und der Icon-Index auf 3 gezogen ("kein Text").
    a.label('d2')
    a.raw(b'\x50\x51\x52')                                    # push eax,ecx,edx
    a.raw(b'\xe8' + bytes(4)); a.label('d2p'); a.raw(b'\x59')
    a.raw(b'\x8b\x91'); a.disp('gcode', 'd2p')                # mov edx,[ecx+off]
    a.raw(b'\x85\xd2'); a.jcc(JZ, 'd2_out')
    a.raw(b'\xc7\x81'); a.disp('gcode', 'd2p'); a.raw(bytes(4))
    a.raw(b'\x52'); a.call(s['code2tex']); a.raw(b'\x83\xc4\x04')
    a.raw(b'\x85\xc0'); a.jcc(JZ, 'd2_out')
    a.raw(b'\x50\x8b\xce\x8b\x16\xff\x52\x68')                # push eax; mov ecx,esi; mov edx,[esi]; call [edx+0x68]
    a.raw(b'\x5a\x59\x58')                                    # pop edx,ecx,eax
    a.raw(b'\xbf\x03\x00\x00\x00')                            # mov edi,3
    a.jmp(s['d2_next'])
    a.label('d2_out')
    a.raw(b'\x5a\x59\x58')                                    # pop edx,ecx,eax
    a.raw(b'\x83\xff\x01'); a.jcc(0x84, s['d2_je'])           # cmp edi,1 / je
    a.jmp(s['d2_next'])

    # g2: Ersatz fuer den GetValuei-Aufruf im Textbaustein-Aufloeser.
    # Liefert die Abfrage keinen Gamepad-Code, wird derselbe Name mit
    # umgedrehtem Slot nachgefragt ("...2" anhaengen bzw. entfernen).
    # __thiscall: ecx = Registry, ein Argument auf dem Stack, Callee raeumt.
    a.label('g2')
    a.raw(b'\x53\x56\x57')                                    # push ebx,esi,edi
    a.raw(b'\x8b\xf1')                                        # mov esi,ecx
    a.raw(b'\x8b\x5c\x24\x10')                                # mov ebx,[esp+0x10] (Name)
    a.raw(b'\x53\x8b\xce'); a.call(s['getvaluei'])
    a.raw(b'\x8b\xf8')                                        # mov edi,eax
    a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JB, 'g2_try')
    a.raw(b'\x3d\xb4\x00\x00\x00'); a.jcc(JB, 'g2_done')
    a.label('g2_try')
    a.raw(b'\x83\xec\x40\x8b\xcc\x33\xd2')                    # sub esp,0x40; mov ecx,esp; xor edx,edx
    a.label('g2_cp')
    a.raw(b'\x8a\x04\x13\x88\x04\x11\x42\x84\xc0'); a.jcc(JZ, 'g2_cpe')
    a.raw(b'\x83\xfa\x30'); a.jcc(JB, 'g2_cp')
    a.raw(b'\xc6\x04\x11\x00\x42')
    a.label('g2_cpe')
    a.raw(b'\x80\x7c\x11\xfe\x32'); a.jcc(0x85, 'g2_app')     # endet auf '2'?
    a.raw(b'\xc6\x44\x11\xfe\x00'); a.jmp('g2_q')             # '2' entfernen
    a.label('g2_app')
    a.raw(b'\xc6\x44\x11\xff\x32\xc6\x04\x11\x00')            # '2' anhaengen
    a.label('g2_q')
    a.raw(b'\x51\x8b\xce'); a.call(s['getvaluei']); a.raw(b'\x83\xc4\x40')
    a.raw(b'\x3d\x80\x00\x00\x00'); a.jcc(JB, 'g2_keep')
    a.raw(b'\x3d\xb4\x00\x00\x00'); a.jcc(JB, 'g2_done')
    a.label('g2_keep'); a.raw(b'\x8b\xc7')                    # mov eax,edi
    a.label('g2_done')
    a.raw(b'\x5f\x5e\x5b\xc2\x04\x00')                        # pop edi,esi,ebx; ret 4

    # hb: Hilfe-Leiste. Statt des festen Icon-Index 0 bekommt der Zeichner den
    # Tastencode des Hilfe-Knopfes; die Weiche h2 macht daraus die Glyphen-
    # textur. Die Bezeichnung "F1" wird getrennt davon geleert.
    # ---------------------------------------------------------------------
    # Hilfe auf B, ohne das Nachladen zu verlieren.
    #
    # Die Konsole (bindlistscan) hat den Mechanismus offengelegt: jede Taste
    # traegt bis zu drei Skripte - druecken, loslassen, wiederholen. B (0xA1)
    # traegt 'press(button3)' / 'release(button3)', F1 (0x3B) traegt
    # 'cmd(helpbutton)'. Und **jede Bindung ueberschreibt die vorherige fuer
    # denselben Code** - genau deshalb war das Nachladen tot, sobald
    # ACTION_HELP auf 161 stand.
    # (Dass sich Journal und Scoreboard den Code 165 teilen koennen, liegt
    # nur daran, dass beide dasselbe Skript tragen.)
    #
    # Also wird zur Laufzeit umbelegt, ueber die Skriptmaschine:
    #   hb  laeuft genau dann, wenn der Hilfe-Balken gezeichnet wird - dort
    #       bekommt B 'cmd(helpbutton)', und der Zeitstempel wird gesetzt.
    #   hz  sitzt am Anfang derselben HUD-Funktion und laeuft jedes Bild -
    #       ist der Zeitstempel alt, bekommt B sein Nachladeskript zurueck.
    # Damit hat die Hilfe Vorrang, wo sie angeboten wird, und sonst laedt B
    # nach. Zeitstempel per rdtsc: kein Import, keine absolute Adresse - die
    # DLL wird zur Laufzeit verschoben, und die Hoehle hat keine Relocations.
    def conexec(strlabel, anker):
        a.raw(bytes.fromhex('6a00'))                                  # push 0
        a.raw(bytes.fromhex('8d83')); a.disp('s_conex', anker); a.raw(bytes([0x50]))
        a.raw(bytes.fromhex('83ec08'))                                # sub esp,8
        a.raw(bytes.fromhex('8bcc'))                                  # mov ecx,esp
        a.raw(bytes.fromhex('8d83')); a.disp(strlabel, anker); a.raw(bytes([0x50]))
        a.call(s['cstr_ctor'])
        a.call(s['conexec'])
        a.raw(bytes.fromhex('83c410'))                                # add esp,0x10

    umbelegen = (help_rebind and 'hb_at' in s and 'hz_at' in s
                 and 'conexec' in s and 'cstr_ctor' in s)

    if 'hb_at' in s:
        a.label('hb')
        if umbelegen:
            a.raw(bytes([0x60]))                            # pushad
            a.raw(bytes.fromhex('e800000000')); a.label('hbp'); a.raw(bytes([0x5b]))
            a.raw(bytes.fromhex('0f31'))                              # rdtsc
            a.raw(bytes.fromhex('8983')); a.disp('g_help', 'hbp')     # Zeitstempel
            a.raw(bytes.fromhex('83bb')); a.disp('g_state', 'hbp'); a.raw(bytes([0x00]))
            a.jcc(JNE, 'hb_fertig')                         # schon umbelegt
            for i in range(len(bind_help.split('|'))):
                conexec('s_bhelp%d' % i, 'hbp')
            a.raw(bytes.fromhex('c783')); a.disp('g_state', 'hbp')
            a.raw(struct.pack('<I', 1))
            a.label('hb_fertig')
            a.raw(bytes([0x61]))                            # popad
        a.raw(bytes([0x68]) + struct.pack('<I', help_code))  # push <code>
        a.raw(bytes.fromhex('83ec08'))                                # sub esp,8
        a.jmp(s['hb_back'])

    if umbelegen:
        a.label('hz')
        a.raw(bytes([0x60]))                                # pushad
        a.raw(bytes.fromhex('e800000000')); a.label('hzp'); a.raw(bytes([0x5b]))
        a.raw(bytes.fromhex('83bb')); a.disp('g_state', 'hzp'); a.raw(bytes([0x00]))
        a.jcc(JZ, 'hz_fertig')                              # nichts umbelegt
        a.raw(bytes.fromhex('0f31'))                                  # rdtsc
        a.raw(bytes.fromhex('2b83')); a.disp('g_help', 'hzp')
        a.raw(bytes([0x3d]) + struct.pack('<I', HELP_FENSTER))
        a.jcc(JBE, 'hz_fertig')                             # noch frisch
        conexec('s_brel', 'hzp')
        a.raw(bytes.fromhex('c783')); a.disp('g_state', 'hzp'); a.raw(bytes(4))
        a.label('hz_fertig')
        a.raw(bytes([0x61]))                                # popad
        a.raw(bytes.fromhex('51b824190000'))                          # ersetzte Befehle
        a.jmp(s['hz_back'])

        a.label('g_help');  a.raw(bytes(4))
        a.label('g_state'); a.raw(bytes(4))
        a.label('s_conex'); a.raw(b'ConExecute' + bytes(1))
        for i, zeile in enumerate(bind_help.split('|')):
            a.label('s_bhelp%d' % i); a.raw(zeile.encode('latin1') + bytes(1))
        a.label('s_brel');  a.raw(bind_reload.encode('latin1') + bytes(1))

    # cal: Kalibrierbau. Verschiebt zwei der drei Float-Argumente des
    # Symbolzeichners um verschiedene Betraege. Wohin das Symbol wandert, sagt
    # eindeutig, welches Argument x und welches y ist. Nur zum Messen gedacht.
    if calibrate and 'cal_at' in s:
        # ACHTUNG: ecx traegt hier den Objektzeiger (thiscall) und darf nicht
        # angetastet werden - genau daran ist der erste Versuch abgestuerzt.
        # Als Zwischenregister dient eax, und das wird gesichert.
        a.label('cal')
        a.raw(bytes([0x50]))                              # push eax          esp-4
        a.raw(bytes.fromhex('e800000000')); a.label('calp'); a.raw(bytes([0x58]))  # call $+5 / pop eax
        a.raw(bytes.fromhex('d944241c'))                  # fld  dword [esp+0x1c]  = Arg5
        a.raw(bytes.fromhex('d880')); a.disp('k1', 'calp')
        a.raw(bytes.fromhex('d95c241c'))                  # fstp dword [esp+0x1c]
        a.raw(bytes.fromhex('d9442420'))                  # fld  dword [esp+0x20]  = Arg6
        a.raw(bytes.fromhex('d880')); a.disp('k2', 'calp')
        a.raw(bytes.fromhex('d95c2420'))                  # fstp dword [esp+0x20]
        a.raw(bytes([0x58]))                              # pop eax           esp zurueck
        a.raw(bytes.fromhex('81ecc8000000'))              # sub esp,0xc8 (ersetzter Befehl)
        a.jmp(s['cal_back'])
        a.label('k1'); a.raw(struct.pack('<f', cal1))
        a.label('k2'); a.raw(struct.pack('<f', cal2))

    # il: Symbole im Fliesstext einfaerben - **eine Ebene fuer den Text**.
    #
    # Die Zeile wird genau einmal gezeichnet, voellig unveraendert. Danach wird
    # je Symbol nur das eine Zeichen farbig darueber gesetzt, an der Stelle
    # x + Breite(Vortext). Der Text selbst wird also kein zweites Mal gezeichnet;
    # doppelt liegt nur das Symbol auf sich selbst, und das faellt nicht auf,
    # weil es dieselbe Form an derselben Stelle ist.
    #
    # Die Breite kommt aus der Messfunktion der Engine, genau wie sie diese
    # selbst zum Zentrieren benutzt:
    #     Font->vtable[0x18](Font[0x38], Text)   -> Breite in Atlas-Pixeln
    #     geteilt durch [this+0x158]             -> Breite in x-Einheiten
    #
    # vtable[0xf0], __thiscall, ret 0x28 - Argumente ueber ebp:
    #   [ebp+08] arg0   [ebp+0C] Font   [ebp+10] Zeichenkette
    #   [ebp+14] x      [ebp+18] y      [ebp+1C] Flags
    #   [ebp+20] Hauptfarbe   [ebp+24] Umriss   [ebp+28] Schatten
    #   [ebp+2C] Skalierung
    # Lokale: [ebp-4] Zielposition, [ebp-8] Anker, [ebp-0C] Farbnummer.
    if inline and 'il_at' in s:
        H = bytes.fromhex

        def il_draw(quelle, xslot, farbe):
            a.raw(H('ff752c')); a.raw(H('ff7528')); a.raw(H('ff7524'))
            farbe()
            a.raw(H('ff751c')); a.raw(H('ff7518'))
            a.raw(xslot)
            a.raw(quelle)
            a.raw(H('ff750c')); a.raw(H('ff7508'))
            a.raw(H('8bcb')); a.call('iltr')

        def il_normal():
            a.raw(H('ff7520'))

        def il_symbolfarbe():
            a.raw(H('8b55f4'))                       # mov edx,[ebp-0xC]
            a.raw(H('8b4df8'))                       # mov ecx,[ebp-8]
            a.raw(H('ffb491')); a.disp('ilcol', 'ilp')

        def il_measure():
            """Breite der Zeichenkette in esi auf [ebp-4] addieren."""
            a.raw(H('8b450c'))                       # mov eax,[ebp+0xC]  Font
            a.raw(H('d94038'))                       # fld dword [eax+0x38]
            a.raw(H('56'))                           # push esi
            a.raw(H('83ec04'))                       # sub esp,4
            a.raw(H('d91c24'))                       # fstp dword [esp]
            a.raw(H('8bc8'))                         # mov ecx,eax
            a.raw(H('8b00')); a.raw(H('8b4018'))
            a.raw(H('ffd0'))                         # call -> st0 = Breite
            a.raw(H('d8b358010000'))                 # fdiv dword [ebx+0x158]
            a.raw(H('d845fc'))                       # fadd dword [ebp-4]
            a.raw(H('d95dfc'))                       # fstp dword [ebp-4]

        a.label('il')
        a.raw(H('55')); a.raw(H('8bec')); a.raw(H('83ec10'))
        a.raw(H('535657'))
        a.raw(H('8bd9'))                             # mov ebx,ecx
        a.raw(H('e8') + bytes(4)); a.label('ilp'); a.raw(H('58'))
        a.raw(H('8945f8'))                           # Anker sichern

        # 1) Zeile genau einmal, voellig unveraendert
        il_draw(H('ff7510'), H('ff7514'), il_normal)

        a.raw(H('8b7510'))                           # esi = Zeichenkette
        a.raw(H('85f6')); a.jcc(JZ, 'il_ende')
        a.raw(H('33ff'))                             # edi = 0

        a.label('il_scan')
        a.raw(H('0fb7047e'))                         # movzx eax,word [esi+edi*2]
        a.raw(H('6685c0')); a.jcc(JZ, 'il_ende')
        a.raw(H('3d00010000')); a.jcc(JAE, 'il_next')
        a.raw(H('8b4df8'))
        a.raw(H('0fb68401')); a.disp('iltab', 'ilp')
        a.raw(H('84c0')); a.jcc(0x85, 'il_treffer')
        a.label('il_next')
        a.raw(H('47')); a.jmp('il_scan')

        a.label('il_treffer')
        a.raw(H('8945f4'))                           # Farbnummer merken

        # Zielposition = x + Breite des Vortexts
        a.raw(H('d94514')); a.raw(H('d95dfc'))       # [ebp-4] = x
        a.raw(H('85ff')); a.jcc(JZ, 'il_ohne')       # kein Vortext -> nichts messen
        a.raw(H('668b047e')); a.raw(H('50'))         # Zeichen sichern
        a.raw(H('66c7047e0000'))                     # Vortext abschneiden
        il_measure()
        a.raw(H('58')); a.raw(H('6689047e'))         # zuruecksetzen
        a.label('il_ohne')

        # nur das eine Symbolzeichen farbig zeichnen
        a.raw(H('668b447e02')); a.raw(H('50'))
        a.raw(H('66c7447e020000'))
        il_draw(H('8d047e') + H('50'), H('ff75fc'), il_symbolfarbe)
        a.raw(H('58')); a.raw(H('6689447e02'))

        a.raw(H('47')); a.jmp('il_scan')

        a.label('il_ende')
        a.raw(H('5f5e5b')); a.raw(H('8be5')); a.raw(H('5d')); a.raw(H('c22800'))

        a.label('iltr')                              # Trampolin ins Original
        a.raw(H('8b442418')); a.raw(H('f30f10442428'))
        a.jmp(s['il_back'])

        tab, col = il_tabellen()
        a.label('iltab'); a.raw(tab)
        a.label('ilcol'); a.raw(col)

    # Name fuer die umgebogene Nachlade-Abfrage. Der Build hat "ACTION_HELP"
    # nirgends als Zeichenkette - er baut den Profilschluessel zur Laufzeit aus
    # "ACTION_%s". Also legen wir ihn hier ab.
    # tr: Messhaken. Schreibt den Zeiger auf das Objekt mit dem
    # Belegungs-Zwischenspeicher in die Hoehle, damit ein Debugger von aussen
    # einen Hardware-Haltepunkt auf [Objekt+0x13c] setzen kann.
    if trace_reload and 'tr_at' in s:
        a.label('tr')
        a.raw(bytes.fromhex('89873c010000'))             # mov [edi+0x13c],eax
        a.raw(bytes([0x53]))                             # push ebx
        a.raw(bytes.fromhex('e800000000')); a.label('trp'); a.raw(bytes([0x5b]))
        a.raw(bytes.fromhex('89bb')); a.disp('g_obj', 'trp')   # mov [ebx+o],edi
        a.raw(bytes([0x5b]))                             # pop ebx
        a.jmp(s['tr_back'])
        a.label('g_obj'); a.raw(bytes(4))

    # Eigene Texturnamen fuer die beiden Stickklicks. Die Engine wirft L3 und
    # R3 auf denselben Index 11 und zeigt fuer beide GUI_Button_360_C - das
    # Symbol laesst also offen, welcher Stick gemeint ist. Diese zwei Stummel
    # liefern stattdessen GUI_Button_LC bzw. GUI_Button_RC (beide liegen in
    # GUI.xtc und tragen die Aufschrift LS/RS).
    # Sie muessen ohne absolute Adresse auskommen, weil die Hoehle keine
    # Relocations hat: call/pop holt die eigene Adresse, der Abstand zur
    # Zeichenkette ist eine Konstante.
    if stick_icons and 'jt_va' in s:
        for lbl, txt in (('lc', b'GUI_Button_LC'), ('rc', b'GUI_Button_RC')):
            a.label('tex_' + lbl)
            a.raw(bytes.fromhex('e800000000')); a.label(lbl + 'p'); a.raw(bytes([0x58]))
            a.raw(bytes([0x05])); a.disp('s_' + lbl, lbl + 'p')   # add eax,Abstand
            a.raw(bytes([0xc3]))                                  # ret
        a.label('s_lc'); a.raw(b'GUI_Button_LC' + bytes(1))
        a.label('s_rc'); a.raw(b'GUI_Button_RC' + bytes(1))

    # ------------------------------------------------------------- Rumble
    # Der Verteiler bekommt seine Kennung 1..29 in [ebp+8] und faechert sie
    # gleich danach ueber eine Sprungtabelle auf. Hier wird davor die
    # Hilfs-DLL angestossen, die die Huellkurve aus Content\Feedback\
    # feedback.xrg abspielt und die Motorwerte an XInputSetState schickt.
    # Beim ersten Aufruf wird sie ueber LoadLibraryA/GetProcAddress geholt;
    # schlaegt das fehl, wird ein 'ret 4'-Stumpf gespeichert, damit nicht bei
    # jedem Effekt erneut geladen wird. Alles positionsunabhaengig ueber
    # call/pop, weil die DLL zur Laufzeit verschoben ist.
    if rumble and 'rb_at' in s:
        Hx = bytes.fromhex
        a.label('rb')
        a.raw(Hx('609c'))                                  # pushad / pushfd
        a.raw(Hx('e800000000')); a.label('rbp'); a.raw(Hx('5b'))   # call $+5 / pop ebx
        anker = a.labels['rbp']
        a.raw(Hx('8b83')); a.disp('rb_fn', 'rbp')          # mov eax,[ebx+d]
        a.raw(Hx('85c0'))                                  # test eax,eax
        a.jcc(JNE, 'rb_call')
        a.raw(Hx('8d83')); a.disp('rb_dll', 'rbp')         # lea eax,[ebx+d]
        a.raw(Hx('50'))                                    # push eax
        a.raw(Hx('ff93')); a.raw(struct.pack('<i', s['iat_load'] - anker))
        a.raw(Hx('85c0'))
        a.jcc(JZ, 'rb_fail')
        a.raw(Hx('8d8b')); a.disp('rb_name', 'rbp')        # lea ecx,[ebx+d]
        a.raw(Hx('51'))                                    # push ecx  (Name)
        a.raw(Hx('50'))                                    # push eax  (Modul)
        a.raw(Hx('ff93')); a.raw(struct.pack('<i', s['iat_proc'] - anker))
        a.raw(Hx('85c0'))
        a.jcc(JNE, 'rb_store')
        a.label('rb_fail')
        a.raw(Hx('8d83')); a.disp('rb_stub', 'rbp')        # lea eax,[ebx+d]
        a.label('rb_store')
        a.raw(Hx('8983')); a.disp('rb_fn', 'rbp')          # mov [ebx+d],eax
        a.label('rb_call')
        a.raw(Hx('8b4d08'))                                # mov ecx,[ebp+8]
        a.raw(Hx('51'))                                    # push ecx
        a.raw(Hx('ffd0'))                                  # call eax  (stdcall)
        a.raw(Hx('9d61'))                                  # popfd / popad
        a.raw(Hx('8b4d088d41ff83f81c'))                    # das ersetzte Original
        a.jmp(s['rb_back'])
        a.label('rb_stub'); a.raw(Hx('c20400'))            # ret 4
        a.label('rb_dll');  a.raw(b'RiddickRumble.dll' + bytes(1))
        a.label('rb_name'); a.raw(b'RiddickRumble' + bytes(1))
        a.label('rb_fn');   a.raw(bytes(4))

    a.label('rlname'); a.raw(b'ACTION_HELP' + bytes(1))

    a.label('gcode'); a.raw(bytes(4))
    return a


PAD_CODE = {'A': 0xA0, 'B': 0xA1, 'X': 0xA2, 'Y': 0xA3, 'START': 0xA4,
            'BACK': 0xA5, 'L3': 0xA6, 'R3': 0xA7, 'LB': 0xA8, 'RB': 0xA9,
            'LT': 0xAA, 'RT': 0xAB}


# --------------------------------------------------- Inline-Symbole faerben
# Spendezeichen (siehe font_glyphs.py) -> laufende Nummer 1..16.
IL_CHARS = [0xF0, 0xF1, 0xE6, 0xF8, 0xE5, 0xE3, 0xF5, 0xA1,
            0xBF, 0xD0, 0xD1, 0xC6, 0xEC, 0xED, 0xEE, 0xEF]
# Farben in derselben Reihenfolge. Nur A/B/X/Y sind auf dem Controller farbig,
# alles andere bleibt weiss, damit es sich vom Fliesstext abhebt.
WEISS = 0xFFFFFFFF
IL_COLORS = [0xFF6CBB3C,   # A  gruen
             0xFFD03B36,   # B  rot
             0xFF3A6FD0,   # X  blau
             0xFFE8C020,   # Y  gelb
             WEISS, WEISS, WEISS, WEISS,
             WEISS, WEISS, WEISS, WEISS,
             WEISS, WEISS, WEISS, WEISS]


def il_tabellen():
    """-> (256-Byte-Zuordnung Zeichen->Nummer, Farbtabelle mit 17 Eintraegen)"""
    tab = bytearray(256)
    for i, c in enumerate(IL_CHARS, 1):
        tab[c] = i
    col = struct.pack('<I', 0) + b''.join(struct.pack('<I', c) for c in IL_COLORS)
    return bytes(tab), col


def align(v, n):
    return (v + n - 1) // n * n


def patch(path, prefer_pad, diagnose, fix_table=True, probe=False, help_code=0xA1,
          console_buttons=False, skip_fix=True, help_bar=True, calibrate=False,
          cal1=60.0, cal2=-60.0, inline=True, reload_via_help=False,
          trace_reload=False, help_rebind=True,
          bind_help='', bind_reload='', stick_icons=True,
          rumble=True):
    pe = PE(path)
    s = locate(pe)
    out = pe.data

    toff = pe.va2off(s['table_va'])
    if fix_table:
        cur = bytes(out[toff + TABLE_AT: toff + TABLE_AT + len(TABLE_ORIG)])
        if cur == TABLE_ORIG:
            out[toff + TABLE_AT: toff + TABLE_AT + len(TABLE_NEW)] = TABLE_NEW
        elif cur != TABLE_NEW:
            raise SystemExit('%s: Tabelle unerwartet: %s' % (os.path.basename(path), cur.hex()))

    cave_rva = align(pe.size_of_image, pe.sec_align)
    asm = build_cave(pe.base + cave_rva, s, prefer_pad, diagnose, probe, help_code,
                     calibrate, cal1, cal2, inline, trace_reload,
                     help_rebind, bind_help, bind_reload, stick_icons, rumble)
    code = asm.resolve()

    sites = [(s['h1_at'], 'h1', 5), (s['h2_at'], 'h2', 5), (s['h3_at'], 'h3', 5),
             (s['g1_at'], 'g1', 7), (s['d2_at'], 'd2', 5)]
    if prefer_pad:
        sites += [(s['pp1_at'], 'pp1', 7), (s['pp2_at'], 'pp2', 7)]
    if help_bar and 'hb_at' in s:
        sites.append((s['hb_at'], 'hb', 5))
    if inline and 'il_at' in s:
        sites.append((s['il_at'], 'il', 10))
    if calibrate and 'cal_at' in s:
        sites.append((s['cal_at'], 'cal', 6))
    if (help_rebind and 'hb_at' in s and 'hz_at' in s
            and 'conexec' in s and 'cstr_ctor' in s):
        sites.append((s['hz_at'], 'hz', 6))
    if rumble and 'rb_at' in s:
        sites.append((s['rb_at'], 'rb', 9))
    if trace_reload and 'tr_at' in s:
        sites.append((s['tr_at'], 'tr', 6))
        # Der Debugger braucht die Zelle relativ zum Modulanfang, weil die DLL
        # verschoben sein kann.
        zeilen = ['modul %s' % os.path.basename(path).replace('.orig', ''),
                  'g_obj_rva 0x%x' % (asm.labels['g_obj'] - pe.base),
                  'feld_offset 0x13c']
        with open(os.path.join(HERE, 'trace_info.txt'), 'w') as f:
            f.write(os.linesep.join(zeilen) + os.linesep)
    if help_bar and 'hb_f1' in s:
        out[pe.va2off(s['hb_f1'])] = 0        # "F1" leeren, der Glyph tritt an die Stelle
    if skip_fix and 'skip_at' in s:
        for va in s['skip_at']:
            struct.pack_into('<I', out, pe.va2off(va), s['skip_use'])
    if fix_table and 'dup_at' in s:
        out[pe.va2off(s['dup_at'])] = ord('p')
    if stick_icons and 'jt_va' in s:
        # Slot 11 (L3+R3) bekommt LC, der Sammelslot 16 bekommt RC, und R3
        # wird in der Bytetabelle auf 16 umgehaengt. Slot 16 bediente bisher
        # nur Codes, die auf einem Pad nicht vorkommen (Achsen 5..15,
        # Knoepfe 12..15) und lieferte dort "kein Symbol".
        struct.pack_into('<I', out, pe.va2off(s['jt_va'] + 11 * 4),
                         asm.labels['tex_lc'])
        struct.pack_into('<I', out, pe.va2off(s['jt_va'] + 16 * 4),
                         asm.labels['tex_rc'])
        out[pe.va2off(s['table_va'] + 0x27)] = 16        # Code 0xA7 = R3
    if reload_via_help and 'rl_at' in s:
        for va in s['rl_at']:
            struct.pack_into('<I', out, pe.va2off(va), asm.labels['rlname'])
    if console_buttons and 'cbtn' in s:
        o = pe.va2off(s['cbtn'])
        out[o:o + 3] = bytes.fromhex('b001c3')            # mov al,1 / ret
    for va, lbl, n in sites:
        o = pe.va2off(va)
        out[o:o + n] = b'\xe9' + struct.pack('<i', asm.labels[lbl] - (va + 5)) + b'\x90' * (n - 5)

    # g2 wird als Aufruf umgebogen und bleibt ein call, damit das ret 4 passt
    o = pe.va2off(s['g2_call'])
    out[o:o + 5] = b'\xe8' + struct.pack('<i', asm.labels['g2'] - (s['g2_call'] + 5))

    raw_ptr = align(len(out), pe.file_align)
    out.extend(b'\0' * (raw_ptr - len(out)))
    raw_size = align(len(code), pe.file_align)
    out.extend(code + b'\0' * (raw_size - len(code)))
    hdr = struct.pack('<8sIIIIIIHHI', SEC_NAME, max(len(code), 0x10), cave_rva,
                      raw_size, raw_ptr, 0, 0, 0, 0, 0xC0000020)   # Code + schreibbar (gcode)
    out[pe.sectbl + 40 * pe.nsec: pe.sectbl + 40 * pe.nsec + 40] = hdr
    struct.pack_into('<H', out, pe.e_lfanew + 6, pe.nsec + 1)
    struct.pack_into('<I', out, pe.optoff + 56, cave_rva + align(raw_size, pe.sec_align))
    return bytes(out), s, pe.base + cave_rva, len(code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--targets', nargs='*', default=TARGETS)
    ap.add_argument('--prefer-pad', action='store_true')
    ap.add_argument('--diagnose', action='store_true')
    ap.add_argument('--probe', action='store_true',
                    help='jeder Aufloeser liefert ein eigenes Symbol: '
                         'Kette1=A, Kette2=B, Menue=X, Text=Y')
    ap.add_argument('--no-fix-table', action='store_true')
    ap.add_argument('--trace-reload', action='store_true',
                    help='Messbau: Zeiger auf den Belegungs-Zwischenspeicher '
                         'in die Hoehle schreiben (fuer trace_reload.py)')
    ap.add_argument('--no-stick-icons', action='store_true',
                    help='L3/R3 nicht auf eigene Symbole legen')
    ap.add_argument('--no-help-rebind', action='store_true',
                    help='B nicht auf die Hilfe umbelegen, solange der '
                         'Hilfe-Balken steht')
    ap.add_argument('--bind-help', default=None,
                    help='Skriptzeile, die B auf die Hilfe legt')
    ap.add_argument('--bind-reload', default=None,
                    help='Skriptzeile, die B wieder aufs Nachladen legt')
    ap.add_argument('--reload-via-help', action='store_true',
                    help='Nachlade-Abfrage des Eingabesammlers auf ACTION_HELP '
                         'umbiegen - noetig, wenn die Hilfe auf demselben Knopf '
                         'liegt (sonst faellt Nachladen UND Ueberspringen aus)')
    ap.add_argument('--no-inline', action='store_true',
                    help='Symbole im Fliesstext nicht einfaerben (nur eine Ebene)')
    ap.add_argument('--calibrate', action='store_true',
                    help='Messbau: verschiebt Arg5 und Arg6 der Symbolzeichnung')
    ap.add_argument('--cal1', type=float, default=60.0)
    ap.add_argument('--cal2', type=float, default=-60.0)
    ap.add_argument('--no-help-bar', action='store_true',
                    help='die Hilfe-Leiste unveraendert lassen (zeigt dann F1)')
    ap.add_argument('--no-skip-fix', action='store_true',
                    help='den Ueberspringen-Hinweis bei ACTION_RELOAD belassen')
    ap.add_argument('--console-buttons', action='store_true',
                    help='den immer-falsch-Stub vor code2tex auf wahr setzen')
    ap.add_argument('--help-button', default='B',
                    help='Knopf fuer die Hilfe-Leiste (A B X Y START BACK L3 R3 '
                         'LB RB LT RT), Vorgabe B')
    ap.add_argument('--no-rumble', action='store_true',
                    help='die Vibrationsausgabe nicht einhaengen '
                         '(RiddickRumble.dll)')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--restore', action='store_true')
    a = ap.parse_args()

    for dll in a.targets:
        name = os.path.basename(dll)
        if a.restore:
            if os.path.exists(dll + '.orig'):
                shutil.copyfile(dll + '.orig', dll)
                os.remove(dll + '.orig')
                print('zurueckgespielt:', name)
            else:
                print('kein Backup:', name)
            continue

        # Die beiden Skriptzeilen. Vorlage sind die echten Bindungen aus
        # bindlistscan: B = 'press(button3)' / 'release(button3)',
        # F1 = 'cmd(helpbutton)'. Beim Umschalten bleibt 'release(button3)'
        # stehen, damit ein gehaltener Knopf nicht haengenbleibt.
        # Kein Semikolon in den Zeichenketten - daran scheitert der Parser
        # der Konsole (im Spiel geprueft: "Unexpected ; found in expression").
        code = PAD_CODE[a.help_button.upper()]
        bh = a.bind_help or ('bindscan(%d,"cmd(helpbutton)",'
                             '"release(button3)","")' % code)
        br = a.bind_reload or ('bindscan(%d,"press(button3)",'
                               '"release(button3)","")' % code)

        src = dll + '.orig' if os.path.exists(dll + '.orig') else dll
        new, s, cave, n = patch(src, a.prefer_pad or a.probe, a.diagnose,
                                not a.no_fix_table, a.probe,
                                PAD_CODE[a.help_button.upper()], a.console_buttons,
                                not a.no_skip_fix, not a.no_help_bar, a.calibrate,
                                a.cal1, a.cal2, not a.no_inline,
                                a.reload_via_help, a.trace_reload,
                                not a.no_help_rebind, bh, br,
                                not a.no_stick_icons, not a.no_rumble)
        print('== %s ==' % name)
        for k in ('code2tex', 'getvaluei', 'table_va', 'h1_at', 'h2_at', 'h3_at',
                  'pp1_at', 'pp2_at', 'g1_at', 'd2_at', 'g2_call', 'hb_at', 'hb_f1',
                  'cbtn', 'skip_use', 'cal_at', 'il_at',
                  'cstr_ctor', 'conexec', 'gc_at', 'gc_jle', 'gc_back',
                  'tr_at', 'hz_at', 'dup_at', 'rb_at', 'rb_back',
                  'iat_load', 'iat_proc'):
            if k in s:
                print('   %-10s 0x%08x' % (k, s[k]))
        if 'rl_at' in s:
            print('   %-10s %s' % ('rl_at', [hex(v) for v in s['rl_at']]))
        if 'skip_at' in s:
            print('   %-10s %s' % ('skip_at', ['0x%08x' % v for v in s['skip_at']]))
        print('   Hoehle     0x%08x, %d Bytes' % (cave, n))

        out = os.path.join(HERE, name.replace('.dll', '.patched.dll'))
        open(out, 'wb').write(new)
        if a.apply:
            if not os.path.exists(dll + '.orig'):
                shutil.copyfile(dll, dll + '.orig')
            shutil.copyfile(out, dll)
            print('   installiert (Backup: %s.orig)' % name)


if __name__ == '__main__':
    main()
