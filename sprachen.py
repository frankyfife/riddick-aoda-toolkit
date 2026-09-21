#!/usr/bin/env python3
r"""
Sprachtabelle des Launchers / language table for the launcher.

Jeder Eintrag ist (Deutsch, English). `T(schluessel)` liefert den Text in der
gerade gesetzten Sprache; `setzen("en")` schaltet um.
"""

SPRACHEN = ["de", "en"]
NAMEN = {"de": "Deutsch", "en": "English"}

_aktuell = "de"

TEXTE = {
    # ------------------------------------------------------------ Rahmen
    "titel":            ("Riddick - Assault on Dark Athena - Launcher",
                         "Riddick - Assault on Dark Athena - Launcher"),
    "spiel_label":      ("Spiel:", "Game:"),
    "durchsuchen":      ("Durchsuchen ...", "Browse ..."),
    "sprache":          ("Sprache", "Language"),
    "starten":          ("Spiel starten", "Start game"),
    "bereit":           ("Bereit.", "Ready."),
    "kein_spiel":       ("Kein Spiel gewaehlt.", "No game selected."),

    # ------------------------------------------------------------- Reiter
    "reiter_spiel":     ("  Spiel  ", "  Game  "),
    "reiter_menue":     ("  Menue und Steuerung  ", "  Menu and controls  "),
    "reiter_grafik":    ("  Grafik  ", "  Graphics  "),
    "reiter_einbau":    ("  Einbau  ", "  Install  "),

    # -------------------------------------------------------- Reiter Spiel
    "zustand_titel":    ("Zustand der Bestandteile", "Component status"),
    "zustand_hinweis":  ("Jede Datei, die zum ersten Mal geaendert wird, bekommt vorher "
                         "eine Kopie unter <Spiel>\\_LauncherBackup. 'Alles zuruecknehmen' "
                         "im Reiter Einbau stellt daraus den Auslieferungszustand her.",
                         "Every file is copied to <Game>\\_LauncherBackup before it is "
                         "modified for the first time. 'Revert everything' on the Install "
                         "tab restores the shipped state from those copies."),
    "pfad_wurzel":      ("Spielordner:", "Game folder:"),
    "pfad_exe":         ("Programm:", "Executable:"),
    "pfad_cfg":         ("Einstellungen:", "Settings file:"),

    # Zustaende
    "z_eingebaut":      ("eingebaut", "installed"),
    "z_original":       ("Originalzustand", "stock"),
    "z_fremd":          ("fremd/abweichend", "unrecognised"),
    "z_unvollstaendig": ("unvollstaendig", "incomplete"),

    # ------------------------------------------------------- Reiter Menue
    "hauptmenue":       ("Hauptmenue", "Main menu"),
    "hauptmenue_info":  ("Sechs Bytes in MSystem.dll entscheiden, welche PLATFORM_-Symbole "
                         "der Registry-Praeprozessor setzt. Damit haengt zusammen: "
                         "Cube-Hauptmenue, Optionsmenue, Knopfhinweise und der "
                         "Vibrationspunkt.",
                         "Six bytes in MSystem.dll decide which PLATFORM_ symbols the "
                         "registry preprocessor defines. That governs the cube main menu, "
                         "the options menu, the button prompts and the vibration entry."),
    "plat_pc":          ("PC-Cube  (Originalmenue der PC-Fassung)",
                         "PC cube  (the PC version's own menu)"),
    "plat_xenon":       ("Xbox-Cube  (Konsolenmenue, Xbox-360-Zweig)",
                         "Xbox cube  (console menu, Xbox 360 branch)"),
    "plat_ps3":         ("PS3-Cube  (Konsolenmenue, PS3-Zweig)",
                         "PS3 cube  (console menu, PS3 branch)"),

    "zielhilfe":        ("Zielhilfe", "Aim assist"),
    "zielhilfe_info":   ("Der Regler im Optionsmenue ist wirkungslos: sein Wert wird zwar "
                         "gelesen und abgelegt, aber von der Zielrechnung nie abgefragt. "
                         "Wirksam ist die Waffenflagge 'autoaim' - sie steht an 23 Waffen "
                         "in Content\\Registry\\RpgWeapons.xrg.",
                         "The slider in the options menu does nothing: its value is read "
                         "and stored, but the aiming code never looks at it. What does "
                         "work is the weapon flag 'autoaim', set on 23 weapons in "
                         "Content\\Registry\\RpgWeapons.xrg."),
    "zielhilfe_an":     ("Zielhilfe eingeschaltet", "Aim assist enabled"),

    "vibration":        ("Vibration", "Vibration"),
    "vibration_info":   ("Einstellungen der RiddickRumble.dll. Wirken beim naechsten Start.",
                         "Settings for RiddickRumble.dll. They take effect on the next start."),
    "staerke":          ("Staerke", "Strength"),
    "motoren_tauschen": ("Motoren tauschen", "Swap motors"),
    "protokoll":        ("Protokoll schreiben (RiddickRumble.log)",
                         "Write a log (RiddickRumble.log)"),
    "vib_sichern":      ("Vibrationseinstellungen sichern", "Save vibration settings"),
    "vib_fehlt":        ("RiddickRumble.ini ist nicht da - erst den Bestandteil "
                         "'Vibration' einbauen.",
                         "RiddickRumble.ini is missing - install the 'Vibration' "
                         "component first."),
    "vib_gesichert":    ("Vibrationseinstellungen gesichert.", "Vibration settings saved."),

    # ------------------------------------------------------ Reiter Grafik
    "glsl_titel":       ("Shader-Vertraeglichkeit", "Shader compatibility"),
    "glsl_info":        ("System\\GL\\HLInclude_GLSL.xrg benutzt die dreiargumentige Form "
                         "von texture2D/textureCube. Die ist im Fragment-Shader nicht "
                         "zulaessig; neuere Treiber weisen sie ab, und das Spiel bricht beim "
                         "Start in CRenderContextGL::GLSL_LoadSrc ab. Der Behelf streicht nur "
                         "das dritte Argument im Aufruf, die Signaturen bleiben stehen.",
                         "System\\GL\\HLInclude_GLSL.xrg uses the three-argument form of "
                         "texture2D/textureCube. That is not legal in a fragment shader; "
                         "newer drivers reject it and the game aborts on start in "
                         "CRenderContextGL::GLSL_LoadSrc. The fix drops the third argument "
                         "from the call and leaves the signatures alone."),
    "glsl_an":          ("Behelf angewandt (bei Absturz beim Start noetig)",
                         "Fix applied (needed if the game crashes on start)"),
    "glsl_warnung":     ("Der Shader-Behelf ist NICHT angewandt - auf neueren Treibern "
                         "stuerzt das Spiel damit beim Start ab. Reiter Grafik, ganz oben.",
                         "The shader fix is NOT applied - on newer drivers the game crashes "
                         "on start without it. See the top of the Graphics tab."),
    "glsl_fremd":       ("HLInclude_GLSL.xrg ist weder im Original- noch im behobenen "
                         "Zustand - der Launcher fasst sie nicht an.",
                         "HLInclude_GLSL.xrg is in neither the original nor the fixed "
                         "state - the launcher will not touch it."),
    "aufloesung":       ("Aufloesung", "Resolution"),
    "aufloesung_info":  ("VID_MODE hat die Form 'Breite Hoehe Farbtiefe Hz'. Nur das Wort "
                         "'desktop' zweigt in den Fensterpfad ab - dort kommen die "
                         "Randprobleme her, deshalb steht hier ein echter Modus.",
                         "VID_MODE takes the form 'width height depth Hz'. Only the word "
                         "'desktop' branches into the windowed path, which is where the "
                         "border and letterbox trouble comes from - so a real mode is "
                         "used here."),
    "bei":              ("  bei  ", "  at  "),
    "darstellung":      ("Darstellung", "Rendering"),
    "gelesen_von":      ("gelesen von", "read by"),
    "vorgabe":          ("Vorgabe", "default"),
    "wert_geprueft":    ("Wertebereich im Code geprueft",
                         "value range verified in code"),
    "erweitert":        ("Erweitert (Rohwerte)", "Advanced (raw values)"),
    "erweitert_info":   ("Diese Schluessel kommen in den Binaerdateien vor, ihre Wirkung "
                         "ist nicht im Einzelnen geprueft. Leeres Feld = Schluessel "
                         "bleibt, wie er ist.",
                         "These keys do occur in the binaries, but their effect has not "
                         "been verified one by one. An empty field leaves the key "
                         "untouched."),
    "uebernehmen":      ("Uebernehmen", "Apply"),
    "neu_einlesen":     ("Neu einlesen", "Reload"),
    "cfg_zurueck":      ("cfg zuruecksetzen", "Reset cfg"),
    "cfg_gelesen":      ("Gelesen aus %s", "Read from %s"),
    "cfg_geschrieben":  ("Geschrieben nach %s   (Sicherung: Environment.cfg.launcher_bak)",
                         "Written to %s   (backup: Environment.cfg.launcher_bak)"),
    "cfg_zurueckgesetzt": ("Environment.cfg zurueckgesetzt.", "Environment.cfg reset."),
    "cfg_keine_sicherung": ("Keine Sicherung der Environment.cfg vorhanden.",
                            "There is no backup of Environment.cfg."),
    "wert_ausserhalb":  ("%s=%s liegt ausserhalb des gueltigen Bereichs %d..%d - das Spiel stuerzt damit beim Start ab. Im Reiter Grafik richtigstellen.",
                         "%s=%s is outside the valid range %d..%d - the game crashes on start with it. Correct it on the Graphics tab."),
    "n_geschrieben":    ("%d Einstellungen geschrieben.", "%d settings written."),

    # ------------------------------------------------------ Reiter Einbau
    "bestandteile":     ("Bestandteile", "Components"),
    "einbau_info":      ("Die fertigen Dateien liegen in data\\ neben dem Launcher und "
                         "werden mit Pruefsumme abgeglichen: nur wenn die Zieldatei dem "
                         "erwarteten Original oder der bearbeiteten Fassung entspricht, "
                         "wird sie angefasst. Eine fremde Spielfassung bleibt unberuehrt.",
                         "The finished files live in data\\ next to the launcher and are "
                         "checked by hash: a file is only touched when it matches either "
                         "the expected original or the modified version. A different "
                         "build of the game is left alone."),
    "einbauen":         ("einbauen", "install"),
    "entfernen":        ("entfernen", "remove"),
    "alles_einbauen":   ("Alles einbauen", "Install everything"),
    "alles_zurueck":    ("Alles zuruecknehmen", "Revert everything"),
    "sicherungen":      ("Sicherungen: %d Dateien unter\n%s",
                         "Backups: %d files under\n%s"),
    "frage_zurueck":    ("Alle gesicherten Dateien zurueckspielen und alle "
                         "hinzugefuegten entfernen?\n\nDie Environment.cfg wird dabei "
                         "ebenfalls zurueckgesetzt, falls eine Sicherung besteht.",
                         "Restore every backed-up file and delete every added one?"
                         "\n\nEnvironment.cfg is reset as well if a backup exists."),
    "n_eingebaut":      ("%s: %d Dateien eingebaut.", "%s: %d files installed."),
    "n_zurueck":        ("%s: %d Dateien zurueckgespielt.", "%s: %d files restored."),
    "n_zurueckgenommen": ("%d Dateien zurueckgenommen.", "%d files reverted."),
    "alles_fertig":     ("Alles eingebaut.", "Everything installed."),
    "menue_umgestellt": ("Hauptmenue umgestellt auf %s.", "Main menu switched to %s."),
    "zielhilfe_status": ("Zielhilfe %s.", "Aim assist %s."),
    "an":               ("an", "on"),
    "aus":              ("aus", "off"),
    "erst_waehlen":     ("Erst das Spiel waehlen.", "Select the game first."),
    "exe_waehlen":      ("DarkAthena.exe waehlen (System\\Win32_x86)",
                         "Select DarkAthena.exe (System\\Win32_x86)"),
    "alle_dateien":     ("Alle Dateien", "All files"),

    # ---------------------------------------------------------- Bestandteile
    "teil_kern":        ("Xbox-Knopfsymbole, Menue, Vibrationshaken",
                         "Xbox button icons, menu, vibration hook"),
    "teil_grafik":      ("Fenster ohne Rahmen, 4K-Modusliste, Viewport",
                         "Borderless window, 4K mode list, viewport"),
    "teil_schrift":     ("Farbige Knopfsymbole in den Schriften",
                         "Coloured button icons in the fonts"),
    "teil_texte":       ("Startbildschirm und Pause-Einblendung",
                         "Start screen and pause overlay"),
    "teil_rumble":      ("Vibration (XInput-Ausgabe)", "Vibration (XInput output)"),

    # ------------------------------------------------------------- Meldungen
    "fehler_pfad":      ("Pfad", "Path"),
    "fehler_menue":     ("Hauptmenue", "Main menu"),
    "fehler_zielhilfe": ("Zielhilfe", "Aim assist"),
    "fehler_grafik":    ("Grafik", "Graphics"),
    "fehler_einbau":    ("Einbau", "Install"),
    "fehler_entfernen": ("Entfernen", "Remove"),
    "fehler_start":     ("Start", "Start"),
}


def setzen(kuerzel):
    global _aktuell
    if kuerzel in SPRACHEN:
        _aktuell = kuerzel


def aktuell():
    return _aktuell


def T(schluessel):
    paar = TEXTE.get(schluessel)
    if not paar:
        return schluessel
    return paar[SPRACHEN.index(_aktuell)]
