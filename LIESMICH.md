# Riddick AoDA Toolkit

Ein Fix für die PC-Fassung von **The Chronicles of Riddick: Assault on Dark
Athena** (2009). Er holt das Spiel an die Xbox-360-Fassung heran und behebt,
was der PC-Port liegengelassen hat - als Drop-in-`winmm.dll` oder als
Python-Launcher, der die Dateien patcht.

> **Es liegen keine Spieldateien in diesem Projekt.** Jede Änderung wird aus
> den Dateien der vorhandenen Installation berechnet. Im Projekt steht
> ausschließlich eigener Quelltext.

*English version: [README.md](README.md)*

**Download:** die fertige Drop-in steht unter [Releases](https://github.com/frankyfife/riddick-aoda-toolkit/releases).

---

## Kompatibilität

Entwickelt und geprüft mit der **GOG-Fassung**, Build `GMC-1.161`
(`BuildInfo.txt`: Code und Inhalt vom 25.03.2009, Changelist 159290):

| Datei | Größe (Byte) | SHA-256 (erste 16) |
|---|---|---|
| `System\Win32_x86\DarkAthena.exe` | 5140336 | `27ADAC97C5F59612` |
| `System\Win32_x86\MSystem.dll` | 5113072 | `8CDE669FB7B4F742` |
| `System\Win32_x86\RndrGL.dll` | 939248 | `B07BAAC43CE4BBF6` |
| `Content\GameClasses_Win32_x86.dll` | 9016560 | `D7E81D7D3726D8F7` |
| `Content\GameWorld_Win32_x86.dll` | 4994288 | `A910A39BAE87F41C` |

Jeder Eingriff sucht sein Bytemuster und lässt eine Datei in Ruhe, wenn es nicht
genau passt. Eine andere Fassung wird also nicht beschädigt, ihr fehlt nur der
jeweilige Fix. `AodaFix.log` zeigt, was angewendet wurde.

---

## Drop-in: AodaFix (empfohlen)

`dropin/` baut eine 32-Bit-`winmm.dll`, die das Spiel beim Start selbst lädt.
Sie patcht die Programmteile im Speicher und erzeugt die geänderten Daten
(Menüs, Schriften, Texte, Waffen, Shader-Include) beim ersten Start in einen
Zwischenspeicher, aus dem das Spiel sie statt der Originale liest. Kein Python,
kein Launcher, keine veränderte Spieldatei.

**Einbau:** `winmm.dll` und `AodaFix.ini` nach `<Spiel>\System\Win32_x86\`
kopieren. **Ausbau:** beide Dateien und den Ordner `AodaFix_cache` löschen.

* Wurde die Installation von einer älteren Fassung dieses Projekts direkt
  geändert, zuerst die Originale zurückholen (`<Spiel>\_LauncherBackup\`
  darüberkopieren). Die Drop-in erkennt nur die Originaldateien.
* Alle Einstellungen stehen kommentiert in `AodaFix.ini`, ein Protokoll in
  `AodaFix.log`.

**Bauen:** `dropin\build.cmd` (MSVC Build Tools 2022, Python 3 mit `pefile`).
`python dropin\tools\selftest.py <Originalbaum> <von den Skripten gepatchter Baum> <Arbeitsordner>`
lädt die Spielmodule, ohne sie auszuführen, wendet die Drop-in an und
vergleicht das Ergebnis mit dem, was die Python-Skripte schreiben.

---

## Was es macht

**Xbox-360-Knopfsymbole überall.** Menüs, Eckhinweise und Fließtext benutzen
die Originalgrafiken der 360, die im PC-Build mitgeliefert, aber nie gezeigt
werden - in den kräftigen Farben statt der blassen `_32`-Fassungen.
Tastennamen in Infotexten werden zu Symbolen. Die beiden Stick-Klicks haben
je ein eigenes Symbol, statt sich eines zu teilen. Eine Aktion hat zwei
Belegungen, zuerst die Tastatur, dann den Controller, und die Info- und
Hilfetexte nennen die erste: bei einem neuen Profil also die Taste, nicht den
Knopf. Das Drop-in gibt diesen Texten die Controller-Belegung (`TextButtons`),
das Profil selbst bleibt, wie es ist.

**Hilfe auf dem Controller** *(Drop-in)*. Die Hilfe-Leiste zeigt B wie auf der
Konsole, und B öffnet die Hilfe, solange die Leiste zu sehen ist; sonst tut B,
was darauf liegt. Keine Belegung wird geändert, F1 geht weiter. Ein anderer
Knopf lässt sich mit `HelpButton` wählen, `HelpButtonOpensHelp=0` belässt es
beim Symbol.

**Konsolenmenüs.** Sechs Bytes in `MSystem.dll` entscheiden, welche
`PLATFORM_`-Symbole der Registry-Präprozessor setzt: das Xbox-360-Würfelmenü
mit seinen Knopf-Hinweisen, der PC-Würfel oder der PS3-Würfel (ohne dessen
Trophäen-Installation). Die Konsolenmenüs kennen keine eigenen Profile, auf der
Konsole liefert sie das System; sie bekommen deshalb die Profilliste des PC:
eine frische Installation kann ihr Profil dort anlegen, und die
Xbox-Optionsseite bietet „Profile“ an, wo „Speichergerät auswählen“ stand. Bei
der Namenseingabe löscht X das letzte Zeichen (`XDeletesCharacter`, Drop-in):
die Bildschirmtastatur hat dafür keine Taste.

**Jede Sprache des Spiels** *(Drop-in)*. Die Knopfsymbole liegen auf Buchstaben,
die keine der fünf Sprachen benutzt, gezählt über Texttabellen, Dialoge und
Abspann; Titelbild und Pausemenü sind in allen angepasst, und die
Stick-Richtungen heißen in der Sprache des Spiels (`AxisNames`).

**Aufgeräumte Menü-Hinweise** *(Drop-in)*. „Weiterspielen“/„Zurück“ und ihre
Symbole standen in voller Zeilenhöhe; jetzt sind sie kleiner (`HintSize`,
`HintIconSize`), die Symbole bleiben auf dem gestreckten Inventar-Overlay rund,
und das Symbol der Hilfe-Leiste sitzt am Text.

**Vibration, die funktioniert.** Der PC-Port liefert die vollständigen
Hüllkurven mit - `Content\Feedback\feedback.xrg` ist bytegleich mit der Datei
der Xbox 360 -, aber keine Ausgabe: `XInputSetState` kommt in keiner
PC-Binärdatei vor. Die Hüllkurven werden gelesen, bis zu acht Effekte mit 60 Hz
gemischt und an beide Motoren geschickt.

**4K ohne Balken.** Der Renderer brach die Aufzählung der Anzeigemodi nach 512
ab; heutige Rechner melden rund 650, und 3840×2160 liegt weit hinten - das Spiel
fiel auf 1920×1440 zurück (4:3, daher die Balken). Die Grenze ist angehoben,
das Fenster randlos über den ganzen Monitor, und die Drop-in setzt `VID_MODE`
auf den Desktop-Modus.

**Anzeigeskalierung** *(Drop-in)*. Das Spiel erklärt sich nicht als
DPI-bewusst, also vergrößert Windows ab 125 Prozent Skalierung sein Fenster:
user32 meldet der Engine logische Pixel, der gerenderte Anzeigemodus bleibt
physisch. Fenster und Bildpuffer passen nicht mehr zusammen, das Bild reicht
über den Bildschirmrand hinaus, sichtbar ist nur ein Teil. Die Drop-in erklärt
den Prozess in `DllMain` als DPI-bewusst, bevor das Spiel ein Fenster hat
(`[Display] DpiAware`). Trägt die exe schon den Kompatibilitätsschalter
*Hohe DPI-Skalierung überschreiben*, bleibt alles, wie es ist. `AodaFix.log`
hält Anzeigemodus, Fenster, Monitor und DPI fest, also genau das, was eine
Meldung über ein abgeschnittenes Bild braucht.

**Shader-Verträglichkeit.** `System\GL\HLInclude_GLSL.xrg` benutzt die
dreiargumentige Form von `texture2D`/`textureCube`, die im Fragment-Shader
nicht zulässig ist; heutige Treiber weisen sie ab, und das Spiel bricht in
`CRenderContextGL::GLSL_LoadSrc` ab. Das Bias-Argument fällt weg. Die Drop-in
korrigiert außerdem das ausgelieferte `XR_SHADERMODE=11` (gültig: 0-6), an dem
eine frische Installation abstürzt.

**Zielhilfe, die sich wirklich abschalten lässt.** Der Regler im Optionsmenü
ist wirkungslos - sein Wert wird gespeichert, aber nie gelesen. Der echte
Schalter ist die Waffenflagge `autoaim` an 23 Waffen.

**Später eingeschalteter Controller** *(Drop-in, `LateController`)*. Die Engine
legt ihre Eingabegeräte einmal beim Start an; ein Pad, das da aus war, blieb bis
zum nächsten Start tot. Ihre eigene Abfrageroutine kann die Geräte neu aufbauen;
die Drop-in löst das aus, sobald XInput ein Pad meldet, für das das Spiel kein
Gerät hat.

**Sprache** *(Drop-in, `Language=en|de|fr|it|es`)*. Das Spiel hat dafür kein
Menü; die Einstellung wird als `LANGUAGE` in die `Environment.cfg` geschrieben
und gilt ab dem nächsten Start, sofern die Sprache installiert ist.

**Alles freigeschaltet, zum Testen** *(Drop-in, `UnlockAll=1`, in der Vorgabe
aus)*. Alle Extras sind offen, und die Entwicklermenüs, die das Spiel noch
mitbringt, verlieren ihre Cheat-Sperre: die Liste aller Karten (X oder Leertaste
im Hauptmenü, dann „Zones“) und das Debug-Menü (X oder Leertaste im Pausemenü).
Die Kapitelauswahl des Spiels bleibt, wie sie ist - sie zeigt die
Kapitel-Spielstände, die ein Profil hat.

**Windows-HDR** *(Drop-in)*. Bei eingeschaltetem HDR wird die Gammarampe des
Spiels ignoriert und beim Beenden die ursprüngliche wiederhergestellt.

**Grafikeinstellungen.** Alle Schlüssel, die die Engine wirklich aus der
`Environment.cfg` liest, mit auswertendem Modul und Vorgabewert, stehen in
[docs/FINDINGS.md](docs/FINDINGS.md), aus den Binärdateien abgelesen und nicht
geraten. Die Drop-in selbst fasst nur `VID_MODE` an und ein `XR_SHADERMODE`
ausserhalb des gültigen Bereichs; alles andere trägt man selbst in die Datei ein.

---

## Die Eingriffsskripte

Unter `patches/` liegen die ursprünglichen Python-Eingriffe, je Thema eines.
Sie schreiben dieselben Änderungen in die Spieldateien statt in den Speicher.
Sie bleiben aus zwei Gründen: `dropin/tools/selftest.py` prüft die Drop-in
byteweise gegen sie, und jedes Skript zeigt einen Eingriff für sich allein.
Jedes nimmt einen Pfad und kennt `--apply` und `--restore`. Eine Ausnahme: der
Vibrationshaken in `patch_gamepad_glyphs.py` ruft eine Hilfs-DLL auf, die nicht
mehr mitgeliefert wird; fehlt sie, greift ein Stummel, der nichts tut. Die
Drop-in hat diesen Code eingebaut.

Zum Einbauen sind sie nicht mehr gedacht. Bis Fassung 1.0.1 steuerte sie ein
Python-Launcher; der ist entfallen, seit die Drop-in dasselbe leistet, ohne eine
Spieldatei anzufassen. Was er über die `Environment.cfg` wusste, steht in
[docs/FINDINGS.md](docs/FINDINGS.md).

## Aufbau

```
dropin/               AodaFix - die Drop-in-winmm.dll (C++), Build-Skript, Selbsttest
patches/              die Python-Eingriffe, je Thema einer, zugleich die
                      Vergleichsgrundlage des Selbsttests
tools/                fix_riddick_dds.py - repariert DDS-Dateien, die der
                      Exporter des Spiels falsch schreibt (falscher FourCC,
                      Mip-Zähler um eins zu hoch)
docs/                 was die Untersuchung ergeben hat
```

## Lizenz

GNU General Public License v3.0, siehe [LICENSE](LICENSE). Das gilt für den
Quelltext in diesem Projekt.
Es ist ein Werkzeug, das eine Installation ändert, die einem selbst gehört; es
enthält und verbreitet keinen Teil des Spiels.

Dies ist ein inoffizielles Werkzeug aus der Fangemeinde. Es steht in keiner
Verbindung zu Starbreeze Studios, Atari oder heutigen Rechteinhabern und ist
von ihnen weder unterstützt noch gebilligt. *The Chronicles of Riddick* und
alle zugehörigen Namen gehören ihren jeweiligen Eigentümern.
