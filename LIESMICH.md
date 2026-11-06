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

* Wer vorher den Launcher benutzt hat, setzt dort zuerst **Alles
  zurücksetzen** - die Drop-in erkennt nur die Originaldateien.
* Alle Einstellungen stehen kommentiert in `AodaFix.ini`, ein Protokoll in
  `AodaFix.log`.

**Bauen:** `dropin\build.cmd` (MSVC Build Tools 2022, Python 3 mit `pefile`).
`python dropin\tools\selftest.py <Originalbaum> <vom Launcher gepatchter Baum> <Arbeitsordner>`
lädt die Spielmodule, ohne sie auszuführen, wendet die Drop-in an und
vergleicht das Ergebnis mit dem, was die Python-Skripte schreiben.

---

## Was es macht

**Xbox-360-Knopfsymbole überall.** Menüs, Eckhinweise und Fließtext benutzen
die Originalgrafiken der 360, die im PC-Build mitgeliefert, aber nie gezeigt
werden - in den kräftigen Farben statt der blassen `_32`-Fassungen.
Tastennamen in Infotexten werden zu Symbolen. Die Hilfe liegt auf L3 mit einem
eindeutigen Stick-Symbol.

**Konsolenmenüs.** Sechs Bytes in `MSystem.dll` entscheiden, welche
`PLATFORM_`-Symbole der Registry-Präprozessor setzt: das Xbox-360-Würfelmenü
mit seinen Knopf-Hinweisen, der PC-Würfel oder der PS3-Würfel (ohne dessen
Trophäen-Installation).

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

**Shader-Verträglichkeit.** `System\GL\HLInclude_GLSL.xrg` benutzt die
dreiargumentige Form von `texture2D`/`textureCube`, die im Fragment-Shader
nicht zulässig ist; heutige Treiber weisen sie ab, und das Spiel bricht in
`CRenderContextGL::GLSL_LoadSrc` ab. Das Bias-Argument fällt weg. Die Drop-in
korrigiert außerdem das ausgelieferte `XR_SHADERMODE=11` (gültig: 0-6), an dem
eine frische Installation abstürzt.

**Zielhilfe, die sich wirklich abschalten lässt.** Der Regler im Optionsmenü
ist wirkungslos - sein Wert wird gespeichert, aber nie gelesen. Der echte
Schalter ist die Waffenflagge `autoaim` an 23 Waffen.

**Windows-HDR** *(Drop-in)*. Bei eingeschaltetem HDR wird die Gammarampe des
Spiels ignoriert und beim Beenden die ursprüngliche wiederhergestellt.

**Grafikeinstellungen** *(Launcher)*. Alle Schlüssel, die die Engine wirklich
aus der `Environment.cfg` liest, mit dem auswertenden Modul und dem
Vorgabewert - beides aus den Binärdateien abgelesen, nicht geraten.

---

## Launcher (Alternative)

Der Launcher schreibt dieselben Änderungen in die Spieldateien - nützlich, um
einen einzelnen Eingriff anzusehen, oder wo keine Proxy-DLL gewünscht ist.

* Voraussetzungen: Windows, Python 3 mit tkinter; **Pillow** für den
  Bestandteil Schrift (`pip install pillow`); MSVC Build Tools nur, um die
  Vibrations-DLL selbst zu bauen (eine übersetzte Fassung liegt bei).
* `RiddickLauncher.cmd` starten und `<Spiel>\System\Win32_x86\DarkAthena.exe`
  wählen. Die Wahl und die Sprache der Oberfläche werden in
  `%LOCALAPPDATA%\RiddickLauncher\launcher.json` gemerkt.
* Jede Datei bekommt vor der ersten Änderung eine Kopie unter
  `<Spiel>\_LauncherBackup\`; **Alles zurücksetzen** spielt alle Kopien zurück
  und entfernt Hinzugefügtes. Die `Environment.cfg` bekommt eine eigene
  Sicherung.

| Bestandteil | Was angefasst wird |
|---|---|
| `kern`    | GameClasses, GameWorld, MSystem, CubeWnd.xrg, CubeInv0.xrg |
| `grafik`  | RndrGL.dll - randloses Fenster, 4K-Modusliste, Viewport |
| `schrift` | Text.xfc, Subtitle.xfc, Headings.xfc - farbige Knopfsymbole |
| `texte`   | Frontend- und StringsX360-Tabellen |
| `rumble`  | RiddickRumble.dll + .ini |

Jeder Bestandteil wird von den Skripten unter `patches/` erzeugt. Die laufen
auch einzeln - jedes nimmt einen Pfad und kennt `--apply` und `--restore`.

## Aufbau

```
dropin/               AodaFix - die Drop-in-winmm.dll (C++), Build-Skript, Selbsttest
RiddickLauncher.pyw   Oberfläche des Launchers
rmod.py               Logik des Launchers: Pfade, Sicherungen, Bestandteile, Einstellungen
sprachen.py           Deutsch / English
patches/              die Eingriffe, je Thema ein Skript
rumble/               Vibrations-DLL für den Launcher, C-Quelltext und übersetzte Fassung
tools/                fix_riddick_dds.py - repariert DDS-Dateien, die der
                      Exporter des Spiels falsch schreibt (falscher FourCC,
                      Mip-Zähler um eins zu hoch)
docs/                 was die Untersuchung ergeben hat
```

## Lizenz

MIT, siehe [LICENSE](LICENSE). Das gilt für den Quelltext in diesem Projekt.
Es ist ein Werkzeug, das eine Installation ändert, die einem selbst gehört; es
enthält und verbreitet keinen Teil des Spiels.

Dies ist ein inoffizielles Werkzeug aus der Fangemeinde. Es steht in keiner
Verbindung zu Starbreeze Studios, Atari oder heutigen Rechteinhabern und ist
von ihnen weder unterstützt noch gebilligt. *The Chronicles of Riddick* und
alle zugehörigen Namen gehören ihren jeweiligen Eigentümern.
