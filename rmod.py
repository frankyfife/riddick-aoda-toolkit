#!/usr/bin/env python3
r"""
rmod - die Logik hinter dem Riddick-Launcher.

Alles, was am Spiel geaendert wird, laeuft ueber dieses Modul. Es kennt drei
Arten von Eingriffen:

  1. **Umschaltbar zur Laufzeit** - Plattform (PC-Cube / Xbox-Cube), Zielhilfe,
     Grafikeinstellungen. Das sind kleine, gezielte Aenderungen an Bytes oder
     Textzeilen, die der Launcher jederzeit hin und her schalten kann.
  2. **Einbau** - die fertigen Dateien aus `data\` werden ins Spiel kopiert
     (Knopfsymbole, Schriften, Menuetexte, Vibration, Fenster/4K).
  3. **Sicherung** - jede Datei, die zum ersten Mal angefasst wird, bekommt
     vorher eine Kopie unter `<Spiel>\_LauncherBackup\` mit gleicher
     Verzeichnisstruktur. Ein Verzeichnis `sicherungen.json` merkt sich, was
     angefasst wurde; damit laesst sich alles in einem Zug zuruecknehmen.

Die Pfade werden **relativ** zur gewaehlten `DarkAthena.exe` bestimmt:
    <exe> = <Spiel>\System\Win32_x86\DarkAthena.exe
"""

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
NUL = bytes(1)
SICHERUNG = "_LauncherBackup"
VERZEICHNIS = "sicherungen.json"

# --------------------------------------------------------------- Plattform
# MSystem entscheidet in einer einzigen Funktion, welche PLATFORM_-Symbole der
# Registry-Praeprozessor setzt. Sie liest das Plattformfeld und springt ueber
# eine Tabelle:  1 XBOX | 2 PS2 | 3 DOLPHIN | 4 XENON | 5 PS3 | sonst WIN.
# Sechs Bytes entscheiden, ob das echte Feld gelesen oder ein fester Index
# eingesetzt wird - mehr ist an der Umschaltung nicht dran.
PLAT_PC = bytes.fromhex("8b406883c0ff")            # mov eax,[eax+0x68]; add eax,-1
PLAT_FOLGE = bytes.fromhex("83f804")               # cmp eax,4  - steht dahinter
PLAT_IDX = {"xenon": 3, "ps3": 4}


def plat_bytes(name):
    return bytes([0xB8]) + struct.pack("<I", PLAT_IDX[name]) + bytes([0x90])


def plat_normalisiert(daten):
    """MSystem-Inhalt mit dem Plattformschalter auf der PC-Form.

    Wird zum Vergleichen gebraucht: die Plattform ist eine Einstellung, keine
    Bearbeitung. Ohne diese Normalisierung wuerde ein Umschalten des
    Hauptmenues die Datei als 'fremd' erscheinen lassen.
    """
    for name in PLAT_IDX:
        muster = plat_bytes(name) + PLAT_FOLGE
        if daten.count(muster) == 1:
            return daten.replace(muster, PLAT_PC + PLAT_FOLGE, 1)
    return daten


def sha256_bytes(daten):
    return hashlib.sha256(daten).hexdigest()


# ------------------------------------------------------------ Grafikoptionen
# (Schluessel, {Sprache: Beschriftung}, Art, Zusatz, wer liest, Vorgabewert)
#
# Woher die Angaben stammen
# -------------------------
# Die Vorgabewerte sind aus den Aufrufstellen abgelesen: das Spiel holt jeden
# Schluessel mit `push <Vorgabe>; push "<Name>"; call [vtable+0x74]` (Ganzzahl)
# bzw. `+0x78` (Kommazahl). Steht in der cfg nichts, gilt genau dieser Wert.
#
# Geprueft im Code:
#   R_ANTIALIAS    RndrGL 0x1005c6d0 zerlegt den Wert in zwei 16-Bit-Haelften
#                  (`sar edx,16` / `and eax,0xffff`) und reicht beide an
#                  0x1005c1e0. Dort gilt: 1 bedeutet aus, es gewinnt die
#                  kleinere der beiden Haelften, und sie wird auf das
#                  Hardwaremaximum geklemmt. Sinnvoll ist also (n<<16)|n -
#                  der Wert 1048592 aus der Original-cfg ist genau 16.
#   XR_SHADERMODE  0..6. Die Namen stehen im Spiel selbst:
#                  StringsPC_*.txt, SYS_SHADERMODE0..6 = Auto, 0.5, 1.1, 1.1,
#                  1.4, 2.0, 2.0++ (mit Hardware-Empfehlung je Stufe).
#   R_ANISOTROPY   Kommazahl, wird an den Treiber weitergereicht und dort
#                  geklemmt; ueblich sind 1, 2, 4, 8, 16.
GRAFIK = [
    ("VID_VSYNC",   {"de": "Bildsynchronisierung (VSync)",
                     "en": "Vertical sync"},              "schalter", None, "RndrGL", "1"),
    ("R_ANTIALIAS", {"de": "Kantenglaettung",
                     "en": "Anti-aliasing"},              "auswahl",
     [("1", "aus / off"), ("131074", "2x"), ("262148", "4x"),
      ("524296", "8x"), ("1048592", "16x")],                          "RndrGL", "1"),
    ("R_ANISOTROPY", {"de": "Anisotrope Filterung",
                      "en": "Anisotropic filtering"},     "auswahl",
     [("1.000000", "1x"), ("2.000000", "2x"), ("4.000000", "4x"),
      ("8.000000", "8x"), ("16.000000", "16x")],                      "RndrGL", "1.0"),
    ("XR_SHADERMODE", {"de": "Shader-Stufe",
                       "en": "Shader level"},             "auswahl",
     [("0", "Auto"), ("1", "0.5"), ("2", "1.1"), ("3", "1.1"),
      ("4", "1.4"), ("5", "2.0"), ("6", "2.0++")],                    "MXR", "0"),
    ("XR_CHARSHADOWS", {"de": "Figurenschatten",
                        "en": "Character shadows"},       "schalter", None, "MXR", "1"),
    ("XR_SSAO",     {"de": "Umgebungsverdeckung (SSAO)",
                     "en": "Ambient occlusion (SSAO)"},   "schalter", None, "MXR", "0"),
    ("VIDEO_SSAO",  {"de": "SSAO im Menue gemerkt",
                     "en": "SSAO as remembered by the menu"},
                                                          "schalter", None, "GameClasses", "0"),
    ("XR_MOTIONBLUR_DOF", {"de": "Bewegungsunschaerfe / Tiefe",
                           "en": "Motion blur / depth of field"},
                                                          "schalter", None, "MXR", "1"),
    ("XR_FLARES",   {"de": "Blendenflecke",
                     "en": "Lens flares"},                "schalter", None, "MXR", "0"),
    ("XR_WALLMARKS", {"de": "Einschussloecher",
                      "en": "Bullet marks"},              "schalter", None, "MXR", "1"),
    ("XR_SOFTSTENCIL", {"de": "Weiche Schattenkanten",
                        "en": "Soft shadow edges"},       "schalter", None, "MXR", "0"),
    ("R_DYNAMICLOADMIPS", {"de": "Texturstufen nachladen",
                           "en": "Stream mip levels"},    "schalter", None, "GameClasses", "1"),
    ("VID_GAMMADISABLE", {"de": "Gammakorrektur abschalten",
                          "en": "Disable gamma correction"}, "schalter", None, "RndrGL", "0"),
    ("GL_SHADERCOMPILETHREADS", {"de": "Shader-Uebersetzer (Faeden)",
                                 "en": "Shader compiler threads"},
                                                          "zahl", None, "RndrGL", "1"),
    ("XR_MAXTEXTURES", {"de": "Texturen hoechstens",
                        "en": "Texture limit"},           "zahl", None, "MSystem", "32768"),
    ("XR_MAXVBCOUNT", {"de": "Vertexpuffer hoechstens",
                       "en": "Vertex buffer limit"},      "zahl", None, "MXR", "16384"),
    ("R_BACKBUFFERFORMAT", {"de": "Bildpufferformat (Rohwert)",
                            "en": "Back buffer format (raw)"},
                                                          "zahl", None, "RndrGL", "4194304"),
    ("XR_SURFOPTIONS", {"de": "Flaechenoptionen (Bitfeld)",
                        "en": "Surface options (bit field)"}, "zahl", None, "MXR", "16"),
]

# Vorhanden, aber Wirkung und Bereich nicht im Einzelnen geprueft.
# Leeres Feld = der Schluessel bleibt unveraendert.
GRAFIK_ERWEITERT = [
    ("GL_ADVPIXELFORMAT",  {"de": "Erweitertes Pixelformat",
                            "en": "Extended pixel format"},        "RndrGL", ""),
    ("GL_SINGLEFBO",       {"de": "Ein einzelner Bildpuffer",
                            "en": "Single framebuffer object"},    "RndrGL", "0"),
    ("GL_TEXTUREDEPTH",    {"de": "Texturtiefe",
                            "en": "Texture depth"},                "RndrGL", ""),
    ("GL_DETACHMSAABUFFERS", {"de": "MSAA-Puffer loesen",
                              "en": "Detach MSAA buffers"},        "RndrGL", ""),
    ("GL_DOASYNCSHADERCOMPILE", {"de": "Shader nebenlaeufig bauen",
                                 "en": "Compile shaders asynchronously"}, "RndrGL", ""),
    ("GL_CLEARRENDERTEX",  {"de": "Zieltexturen leeren",
                            "en": "Clear render textures"},        "RndrGL", ""),
    ("GL_BROKENCLIPPLANES", {"de": "Kappebenen umgehen",
                             "en": "Work around clip planes"},     "RndrGL", ""),
    ("GL_ALLOWD3DHACK",    {"de": "D3D-Behelf zulassen",
                            "en": "Allow the D3D workaround"},     "RndrGL", ""),
    ("GL_EXTDISABLE",      {"de": "Erweiterungen abschalten",
                            "en": "Disable GL extensions"},        "RndrGL", ""),
    ("XR_FORCE_POT_TEXTURES", {"de": "Zweierpotenz-Texturen",
                               "en": "Force power-of-two textures"}, "MXR", ""),
    ("XR_SPLINETESSLEVEL", {"de": "Kurvenunterteilung",
                            "en": "Spline tessellation"},          "MXR", ""),
    ("XR_LODSCALE",        {"de": "Detailabstand (LOD-Skala)",
                            "en": "Detail distance (LOD scale)"},  "MXR", ""),
    ("XR_LODOFFSET",       {"de": "Detailversatz (LOD-Offset)",
                            "en": "Detail bias (LOD offset)"},     "MXR", ""),
    ("R_PICMIP0",          {"de": "Texturstufe Gruppe 0",
                            "en": "Texture mip level, group 0"},   "RndrGL/MXR", ""),
]


class Spiel:
    """Alle Pfade und Zustaende einer Installation."""

    def __init__(self, exe):
        exe = os.path.abspath(exe)
        if os.path.basename(exe).lower() != "darkathena.exe":
            raise ValueError("Bitte DarkAthena.exe waehlen (System\\Win32_x86).")
        self.exe = exe
        self.sys = os.path.dirname(exe)
        self.wurzel = os.path.dirname(os.path.dirname(self.sys))
        if not os.path.isdir(os.path.join(self.wurzel, "Content")):
            raise ValueError("Kein Content-Verzeichnis neben der exe gefunden - "
                             "erwartet wird <Spiel>\\System\\Win32_x86\\DarkAthena.exe")
        self.bak = os.path.join(self.wurzel, SICHERUNG)
        self.verz_datei = os.path.join(self.bak, VERZEICHNIS)
        self.verz = self._verz_lesen()

    # ------------------------------------------------------------ Sicherung
    def _verz_lesen(self):
        if os.path.exists(self.verz_datei):
            try:
                with open(self.verz_datei, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"dateien": [], "neu": []}

    def _verz_schreiben(self):
        os.makedirs(self.bak, exist_ok=True)
        with open(self.verz_datei, "w", encoding="utf-8") as f:
            json.dump(self.verz, f, indent=2, ensure_ascii=False)

    def sichern(self, rel):
        """Legt eine Kopie an, falls noch keine da ist. rel ist spielrelativ.

        Wichtig: auch wenn die Kopie schon existiert, wird der Eintrag im
        Verzeichnis erneuert. Sonst verliert ein spaeteres Zuruecknehmen
        Dateien, deren Kopie zwar noch daliegt, deren Eintrag aber bei einem
        frueheren Zuruecknehmen geloescht wurde.
        """
        ziel = os.path.join(self.wurzel, rel)
        kopie = os.path.join(self.bak, rel)
        if not os.path.exists(ziel):
            if rel not in self.verz["neu"]:
                self.verz["neu"].append(rel)          # gab es vorher nicht
                self._verz_schreiben()
            return
        if not os.path.exists(kopie):
            os.makedirs(os.path.dirname(kopie), exist_ok=True)
            shutil.copy2(ziel, kopie)
        if rel not in self.verz["dateien"]:
            self.verz["dateien"].append(rel)
            self._verz_schreiben()

    def gesicherte(self):
        """Alle vorhandenen Sicherungen, spielrelativ - auch solche, die im
        Verzeichnis fehlen. Damit greift das Zuruecknehmen selbst dann, wenn
        das Verzeichnis nicht mehr vollstaendig ist."""
        aus = []
        for wurzel, _dirs, dateien in os.walk(self.bak):
            for f in dateien:
                voll = os.path.join(wurzel, f)
                rel = os.path.relpath(voll, self.bak)
                if rel.lower() == VERZEICHNIS.lower():
                    continue
                aus.append(rel)
        return aus

    def alles_zurueck(self):
        """Jede gesicherte Datei zurueckspielen, jede neue entfernen.

        Die Kopien bleiben liegen - sie kosten nichts und sind das zweite
        Netz, falls spaeter von Hand etwas verstellt wird.
        """
        n = 0
        for rel in self.gesicherte():
            kopie = os.path.join(self.bak, rel)
            ziel = os.path.join(self.wurzel, rel)
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            shutil.copy2(kopie, ziel)
            n += 1
        for rel in list(self.verz["neu"]):
            ziel = os.path.join(self.wurzel, rel)
            if os.path.exists(ziel):
                os.remove(ziel)
                n += 1
        self.verz = {"dateien": [], "neu": []}
        self._verz_schreiben()
        return n

    # --------------------------------------------------------------- Einbau
    #
    # Es werden **keine** Spieldateien mitgeliefert. Jeder Bestandteil wird aus
    # den Dateien der vorhandenen Installation erzeugt, indem die Skripte unter
    # `patches\` darauf angewandt werden. Was im Projekt liegt, ist
    # ausschliesslich eigener Code.
    #
    # Je Bestandteil:
    #   dateien  - was angefasst wird (wird vorher gesichert)
    #   schritte - (Skript, Argumente) in genau dieser Reihenfolge
    #   marke    - am Ergebnis ablesbar, ob der Eingriff drin ist
    PATCHES = os.path.join(HIER, "patches")

    def _gl(self, *teile):
        return os.path.join(self.wurzel, *teile)

    def bestandteile(self):
        gc = self._gl("Content", "GameClasses_Win32_x86.dll")
        gw = self._gl("Content", "GameWorld_Win32_x86.dll")
        gui = self._gl("Content", "GUI")
        return {
            "kern": {
                "dateien": [r"Content\GameClasses_Win32_x86.dll",
                            r"Content\GameWorld_Win32_x86.dll",
                            r"System\Win32_x86\MSystem.dll",
                            r"Content\GUI\CubeWnd.xrg",
                            r"Content\GUI\CubeInv0.xrg"],
                "schritte": [
                    ("patch_gamepad_glyphs.py",
                     ["--targets", gc, gw, "--prefer-pad", "--help-button", "L3",
                      "--no-inline", "--no-skip-fix", "--no-help-rebind", "--apply"]),
                    ("rename_pad_keys.py", ["--game", self.wurzel, "--apply"]),
                    ("enable_buttondesc.py",
                     ["--file", os.path.join(gui, "CubeWnd.xrg"),
                      "--no-outside", "--apply"]),
                    # In CubeInv0 nur die a/b-Hinweise: die Pfeil-Hinweise
                    # lagen ueber den ohnehin vorhandenen Seitenbeschriftungen.
                    ("enable_buttondesc.py",
                     ["--file", os.path.join(gui, "CubeInv0.xrg"),
                      "--nur", "a,b", "--no-outside", "--apply"]),
                    ("pc_button_icons.py", ["--ordner", gui, "--apply"]),
                ],
            },
            "grafik": {
                "dateien": [r"System\Win32_x86\RndrGL.dll"],
                "schritte": [("borderless.py",
                              ["--datei", self._gl("System", "Win32_x86", "RndrGL.dll"),
                               "--kein-nagel", "--apply"])],
            },
            "schrift": {
                "dateien": [r"Content\Fonts\Text.xfc",
                            r"Content\Fonts\Subtitle.xfc",
                            r"Content\Fonts\Headings.xfc"],
                "schritte": [("font_color.py", ["--game", self.wurzel, "--apply"])],
                "braucht": "Pillow",
            },
            "texte": {
                "dateien": [r"Content_Ger\Registry\Stringtables\Frontend_Ger.txt",
                            r"Content_Ger\Registry\Stringtables\StringsX360_Ger.txt",
                            r"Content\Registry\Stringtables\Frontend_Eng.txt",
                            r"Content\Registry\Stringtables\StringsX360_Eng.txt"],
                "schritte": [("menu_texte.py", ["--game", self.wurzel, "--apply"])],
            },
            "rumble": {
                "dateien": [r"System\Win32_x86\RiddickRumble.dll",
                            r"System\Win32_x86\RiddickRumble.ini"],
                "schritte": [],          # wird kopiert, ist eigener Code
            },
        }

    # ----------------------------------------------------- Erkennungsmarken
    # Kein Vergleich mit mitgelieferten Pruefsummen - es wird am Ergebnis
    # selbst abgelesen, ob der Eingriff drin ist. Ob eine Datei ueberhaupt
    # bearbeitbar ist, prueft das jeweilige Skript: es bricht ab, wenn es
    # seine Bytemuster nicht findet.
    def _marke_kern(self):
        d = open(self._gl("Content", "GameClasses_Win32_x86.dll"), "rb").read()
        return b".pglyph" in d

    def _marke_grafik(self):
        d = open(self._gl("System", "Win32_x86", "RndrGL.dll"), "rb").read()
        # ModeList_Init (MDispGL.cpp): cmp eax,0x200 -> cmp eax,0x1000.
        # Die Konstante allein kommt auch als Datenwort vor, deshalb wird
        # die ganze Befehlsfolge geprueft - mit dem folgenden
        # mov [esp+0x18],eax / jl ist sie eindeutig.
        return bytes.fromhex("3d001000008944241 80f8c".replace(" ", "")) in d

    def _marke_schrift(self):
        # Der Mipmap-Kopf fuehrt im Original A8 (0x00040000), danach DXT5 (0x800).
        d = open(self._gl("Content", "Fonts", "Text.xfc"), "rb").read()
        q = struct.unpack_from("<I", d, 24)[0]
        while q + 48 <= len(d):
            name = d[q:q + 24].split(NUL)[0]
            if name == b"MIPMAP":
                return struct.unpack_from("<I", d, q + 44)[0] == 0x800
            if not name:
                break
            q += 48
        return False

    def _marke_texte(self):
        p = self._gl("Content_Ger", "Registry", "Stringtables", "Frontend_Ger.txt")
        d = open(p, "rb").read()
        t = (d[2:].decode("utf-16-le", "replace") if d[:2] == b"\xff\xfe"
             else d.decode("latin1"))
        return "ð" in t.split("MENU_PRESSSTART_PC")[-1][:40]

    def _marke_rumble(self):
        return os.path.exists(self._gl("System", "Win32_x86", "RiddickRumble.dll"))

    def teil_zustand(self, teil):
        """-> eingebaut | original | fehlt"""
        for rel in self.bestandteile()[teil]["dateien"]:
            if teil != "rumble" and not os.path.exists(os.path.join(self.wurzel, rel)):
                return "fehlt"
        try:
            marke = getattr(self, "_marke_" + teil)()
        except Exception:
            return "fehlt"
        return "eingebaut" if marke else "original"

    def teil_einbauen(self, teil):
        b = self.bestandteile()[teil]
        if self.teil_zustand(teil) == "eingebaut":
            return 0
        # Das Hauptmenue ist eine Einstellung - sie soll den Einbau ueberleben.
        vorher = None
        if "System\\Win32_x86\\MSystem.dll" in b["dateien"]:
            try:
                vorher = self.plattform()
            except Exception:
                pass
        for rel in b["dateien"]:
            self.sichern(rel)
        for skript, args in b["schritte"]:
            self._skript(skript, args)
        if teil == "rumble":
            shutil.copyfile(os.path.join(HIER, "rumble", "bin", "RiddickRumble.dll"),
                            os.path.join(self.sys, "RiddickRumble.dll"))
            ini = os.path.join(self.sys, "RiddickRumble.ini")
            if not os.path.exists(ini):
                shutil.copyfile(os.path.join(HIER, "rumble", "RiddickRumble.ini"), ini)
        if vorher and vorher != "unbekannt":
            self.plattform_setzen(vorher)
        return len(b["dateien"])

    def _skript(self, name, args):
        pfad = os.path.join(self.PATCHES, name)
        if not os.path.exists(pfad):
            raise IOError("Skript fehlt: " + pfad)
        r = subprocess.run([sys.executable, pfad] + args,
                           cwd=self.PATCHES, capture_output=True, text=True)
        if r.returncode != 0:
            raise IOError("%s ist fehlgeschlagen:\n%s"
                          % (name, (r.stderr or r.stdout).strip()[:900]))

    def teil_entfernen(self, teil):
        n = 0
        for rel in self.bestandteile()[teil]["dateien"]:
            kopie = os.path.join(self.bak, rel)
            ziel = os.path.join(self.wurzel, rel)
            if os.path.exists(kopie):
                shutil.copy2(kopie, ziel)
                n += 1
                if rel in self.verz["dateien"]:
                    self.verz["dateien"].remove(rel)
            elif rel in self.verz["neu"] and os.path.exists(ziel):
                os.remove(ziel)
                n += 1
                self.verz["neu"].remove(rel)
        self._verz_schreiben()
        return n

    # ---------------------------------------------------------- Plattform
    def msystem(self):
        return os.path.join(self.sys, "MSystem.dll")

    def plattform(self):
        """-> 'pc' | 'xenon' | 'ps3' | 'unbekannt'"""
        d = open(self.msystem(), "rb").read()
        if d.count(PLAT_PC + PLAT_FOLGE) == 1:
            return "pc"
        for name in PLAT_IDX:
            if d.count(plat_bytes(name) + PLAT_FOLGE) == 1:
                return name
        return "unbekannt"

    def plattform_setzen(self, ziel):
        """ziel: 'pc' | 'xenon' | 'ps3'"""
        pfad = self.msystem()
        d = bytearray(open(pfad, "rb").read())
        alt = self.plattform()
        if alt == ziel:
            return False
        if alt == "unbekannt":
            raise IOError("Plattformschalter in MSystem.dll nicht gefunden.")
        vorher = PLAT_PC if alt == "pc" else plat_bytes(alt)
        nachher = PLAT_PC if ziel == "pc" else plat_bytes(ziel)
        stellen = [m.start() for m in re.finditer(re.escape(vorher + PLAT_FOLGE), bytes(d))]
        if len(stellen) != 1:
            raise IOError("Plattformschalter nicht eindeutig (%d Treffer)." % len(stellen))
        self.sichern(os.path.relpath(pfad, self.wurzel))
        o = stellen[0]
        d[o:o + 6] = nachher
        open(pfad, "wb").write(bytes(d))
        return True

    # ----------------------------------------------------------- Zielhilfe
    def waffen(self):
        return os.path.join(self.wurzel, "Content", "Registry", "RpgWeapons.xrg")

    def zielhilfe(self):
        """-> True (an) | False (aus) | None (Datei fehlt)"""
        p = self.waffen()
        if not os.path.exists(p):
            return None
        d = open(p, "rb").read()
        return bool(re.search(rb"(?<![a-zA-Z])autoaim", d))

    def zielhilfe_setzen(self, an):
        """Zielhilfe ein- oder ausschalten.

        Ausschalten rechnet die Flagge aus der vorhandenen Datei heraus;
        vorher wird gesichert. Einschalten spielt genau diese Sicherung
        zurueck - eine mitgelieferte Vorlage gibt es bewusst nicht, im
        Projekt liegen keine Spieldateien.
        """
        p = self.waffen()
        if not os.path.exists(p):
            raise IOError("RpgWeapons.xrg nicht gefunden: " + p)
        rel = os.path.relpath(p, self.wurzel)
        kopie = os.path.join(self.bak, rel)
        if self.zielhilfe() == bool(an):
            return False
        if an:
            if not os.path.exists(kopie):
                raise IOError(
                    "Zum Wiedereinschalten wird die Sicherung gebraucht, es gibt "
                    "aber keine: " + kopie + " - sie entsteht beim Abschalten. "
                    "Ohne sie hilft nur, die Datei neu zu installieren.")
            shutil.copy2(kopie, p)
            return True
        d = open(p, "rb").read()
        ohne = self._ohne_autoaim(d)
        if ohne == d:
            raise IOError("In RpgWeapons.xrg steht keine Flagge 'autoaim' - "
                          "die Datei wird nicht angefasst.")
        self.sichern(rel)
        open(p, "wb").write(ohne)
        return True

    @staticmethod
    def _ohne_autoaim(d):
        """Die Flagge 'autoaim' aus allen *flags-Zeilen nehmen.

        'noautoaim' bleibt stehen - vor 'autoaim' darf kein Buchstabe stehen.
        """
        zeilen0 = d.count(b"\r\n")
        aus = bytearray()
        rest = 0
        n = 0
        for m in re.finditer(rb"(?m)^[^\r\n]*\*flags[^\r\n]*", d):
            zeile = m.group(0)
            neu = re.sub(rb"(?<![a-zA-Z])autoaim\+", b"", zeile)
            neu = re.sub(rb"\+(?<![a-zA-Z]\+)autoaim(?![a-zA-Z])", b"", neu)
            if neu == zeile:
                continue
            aus += d[rest:m.start()] + neu
            rest = m.end()
            n += 1
        aus += d[rest:]
        if bytes(aus).count(b"\r\n") != zeilen0:
            raise IOError("Zeilenenden veraendert - abgebrochen.")
        return bytes(aus)

    # ------------------------------------------------------ Environment.cfg
    def cfg_pfad(self):
        """Die massgebliche cfg. Das Spiel liest die unter %LOCALAPPDATA%."""
        lokal = os.environ.get("LOCALAPPDATA", "")
        kandidat = os.path.join(lokal, "Atari",
                                "The Chronicles of Riddick - Assault on Dark Athena",
                                "Environment.cfg")
        if os.path.exists(kandidat):
            return kandidat
        return os.path.join(self.wurzel, "Environment.cfg")

    def cfg_lesen(self):
        p = self.cfg_pfad()
        if not os.path.exists(p):
            return {}
        d = open(p, "rb").read()
        werte = {}
        for zeile in re.split(rb"\r\n|\n", d):
            m = re.match(rb"([A-Za-z_0-9]+)=(.*)$", zeile)
            if m:
                werte[m.group(1).decode("latin1")] = m.group(2).decode("latin1")
        return werte

    def cfg_schreiben(self, aenderungen):
        """{Schluessel: Wert} setzen oder anhaengen. Zeilenenden bleiben CRLF."""
        p = self.cfg_pfad()
        if not os.path.exists(p):
            raise IOError("Environment.cfg nicht gefunden:\n" + p)
        # Die cfg liegt ausserhalb des Spielordners - eigene Sicherung daneben.
        if not os.path.exists(p + ".launcher_bak"):
            shutil.copy2(p, p + ".launcher_bak")
        d = open(p, "rb").read()
        for k, v in aenderungen.items():
            zeile = ("%s=%s" % (k, v)).encode("latin1")
            mu = re.compile(rb"(?m)^" + re.escape(k.encode()) + rb"=[^\r\n]*")
            if mu.search(d):
                d = mu.sub(lambda m: zeile, d, count=1)
            else:
                if not d.endswith(b"\r\n"):
                    d += b"\r\n"
                d += zeile + b"\r\n"
        d = re.sub(rb"(?<!\r)\n", b"\r\n", d)          # nie ein nacktes LF hinterlassen
        open(p, "wb").write(d)

    def cfg_zurueck(self):
        p = self.cfg_pfad()
        if os.path.exists(p + ".launcher_bak"):
            shutil.copy2(p + ".launcher_bak", p)
            return True
        return False

    # ------------------------------------------------------------- Starten

    # ---------------------------------------------------- Shader-Vertraeglichkeit
    # `System\GL\HLInclude_GLSL.xrg` definiert zwei Hilfsfunktionen mit der
    # dreiargumentigen Form von texture2D/textureCube:
    #     float4 tex2DBias(...)   { return texture2D(_tex, _st, _bias); }
    #     float4 texCubeBias(...) { return textureCube(_tex, _str, _bias); }
    # Die Bias-Form ist im **Fragment**-Shader nicht zulaessig. Aeltere Treiber
    # haben das geschluckt, neuere weisen es ab - der Shader uebersetzt nicht,
    # und das Spiel bricht beim Start mit
    #     Starbreeze CCException, CRenderContextGL::GLSL_LoadSrc
    # ab. Der Behelf laesst die Signaturen stehen und streicht nur das dritte
    # Argument im Aufruf; alle Aufrufer bleiben damit unveraendert gueltig.
    GLSL_DATEI = os.path.join("System", "GL", "HLInclude_GLSL.xrg")
    GLSL_PAARE = [
        (b"{ return texture2D(_tex, _st, _bias); }",
         b"{ return texture2D(_tex, _st); }"),
        (b"{ return textureCube(_tex, _str, _bias); }",
         b"{ return textureCube(_tex, _str); }"),
    ]

    def glsl_pfad(self):
        return os.path.join(self.wurzel, self.GLSL_DATEI)

    def glsl_zustand(self):
        """'gefixt' | 'original' | 'fremd' | 'fehlt'"""
        p = self.glsl_pfad()
        if not os.path.exists(p):
            return "fehlt"
        d = open(p, "rb").read()
        alt = sum(d.count(a) for a, _n in self.GLSL_PAARE)
        neu = sum(d.count(n) for _a, n in self.GLSL_PAARE)
        if alt == 0 and neu == len(self.GLSL_PAARE):
            return "gefixt"
        if neu == 0 and alt == len(self.GLSL_PAARE):
            return "original"
        return "fremd"

    def glsl_setzen(self, an):
        """Behelf ein- oder ausschalten. Gibt True zurueck, wenn sich etwas
        geaendert hat."""
        zustand = self.glsl_zustand()
        if zustand == "fehlt":
            raise IOError("Datei nicht gefunden:\n" + self.glsl_pfad())
        if zustand == "fremd":
            raise IOError("Die Datei ist weder im Original- noch im behobenen "
                          "Zustand - sie wird nicht angefasst:\n" + self.glsl_pfad())
        if (zustand == "gefixt") == bool(an):
            return False
        self.sichern(self.GLSL_DATEI)
        d = open(self.glsl_pfad(), "rb").read()
        zeilen = d.count(b"\r\n")
        for alt, neu in self.GLSL_PAARE:
            von, nach = (alt, neu) if an else (neu, alt)
            if d.count(von) != 1:
                raise IOError("Zeile nicht eindeutig: %r" % von.decode())
            d = d.replace(von, nach, 1)
        if d.count(b"\r\n") != zeilen:
            raise IOError("Zeilenenden veraendert - abgebrochen")
        open(self.glsl_pfad(), "wb").write(d)
        return True

    # Bereiche, die im Code nachgewiesen sind. Alles andere wird nicht geprueft -
    # lieber gar keine Aussage als eine erfundene.
    GEPRUEFTE_BEREICHE = {
        "XR_SHADERMODE": (0, 6),
    }

    def cfg_probleme(self):
        """[(Schluessel, Wert, erlaubt_von, erlaubt_bis)] fuer Werte ausserhalb
        eines nachgewiesenen Bereichs.

        Anlass: die ausgelieferte Environment.cfg fuehrt XR_SHADERMODE=11,
        obwohl nur 0..6 existieren. Beim ersten Start - wenn es noch keine cfg
        unter AppData gibt - stuerzt das Spiel deshalb in
        CRenderContextGL::GLSL_LoadSrc ab.
        """
        aus = []
        werte = self.cfg_lesen()
        for k, (von, bis) in self.GEPRUEFTE_BEREICHE.items():
            w = werte.get(k)
            if w is None:
                continue
            try:
                z = int(float(w))
            except ValueError:
                continue
            if not (von <= z <= bis):
                aus.append((k, w, von, bis))
        return aus

    def starten(self):
        subprocess.Popen([self.exe], cwd=self.sys, close_fds=True)


def sha256(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for stueck in iter(lambda: f.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


# ------------------------------------------------------------ Anzeigemodi
class _DEVMODE(ctypes.Structure):
    _fields_ = [("dmDeviceName", wt.WCHAR * 32), ("dmSpecVersion", wt.WORD),
                ("dmDriverVersion", wt.WORD), ("dmSize", wt.WORD),
                ("dmDriverExtra", wt.WORD), ("dmFields", wt.DWORD),
                ("dmPosX", wt.LONG), ("dmPosY", wt.LONG),
                ("dmDisplayOrientation", wt.DWORD), ("dmDisplayFixedOutput", wt.DWORD),
                ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short), ("dmFormName", wt.WCHAR * 32),
                ("dmLogPixels", wt.WORD), ("dmBitsPerPel", wt.DWORD),
                ("dmPelsWidth", wt.DWORD), ("dmPelsHeight", wt.DWORD),
                ("dmDisplayFlags", wt.DWORD), ("dmDisplayFrequency", wt.DWORD),
                ("dmICMMethod", wt.DWORD), ("dmICMIntent", wt.DWORD),
                ("dmMediaType", wt.DWORD), ("dmDitherType", wt.DWORD),
                ("dmReserved1", wt.DWORD), ("dmReserved2", wt.DWORD),
                ("dmPanningWidth", wt.DWORD), ("dmPanningHeight", wt.DWORD)]


def anzeigemodi():
    """-> {(Breite, Hoehe): [Hz, ...]} - nur 32 Bit, wie das Spiel sie filtert."""
    u = ctypes.windll.user32
    modi = {}
    i = 0
    while True:
        m = _DEVMODE()
        m.dmSize = ctypes.sizeof(_DEVMODE)
        if not u.EnumDisplaySettingsW(None, i, ctypes.byref(m)):
            break
        if m.dmBitsPerPel > 16:
            modi.setdefault((m.dmPelsWidth, m.dmPelsHeight), set()).add(m.dmDisplayFrequency)
        i += 1
    return {k: sorted(v, reverse=True) for k, v in modi.items()}


def aktueller_modus():
    u = ctypes.windll.user32
    m = _DEVMODE()
    m.dmSize = ctypes.sizeof(_DEVMODE)
    u.EnumDisplaySettingsW(None, -1, ctypes.byref(m))
    return int(m.dmPelsWidth), int(m.dmPelsHeight), int(m.dmDisplayFrequency)
