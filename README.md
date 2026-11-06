# Riddick AoDA Toolkit

A fix for the PC version of **The Chronicles of Riddick: Assault on Dark
Athena** (2009). It brings the game back in line with the Xbox 360 release and
repairs what the PC port left broken - as a drop-in `winmm.dll`, or as a Python
launcher that patches the files.

> **No game files are included in this repository.** Every change is computed
> from the files of your own installation. The repository contains only its
> own source code.

*Deutsche Fassung: [LIESMICH.md](LIESMICH.md)*

**Download:** the ready-built drop-in is on the [Releases](https://github.com/frankyfife/riddick-aoda-toolkit/releases) page.

---

## Compatibility

Developed and tested against the **GOG release**, build `GMC-1.161`
(`BuildInfo.txt`: code and content 2009-03-25, changelist 159290):

| File | Size (bytes) | SHA-256 (first 16) |
|---|---|---|
| `System\Win32_x86\DarkAthena.exe` | 5140336 | `27ADAC97C5F59612` |
| `System\Win32_x86\MSystem.dll` | 5113072 | `8CDE669FB7B4F742` |
| `System\Win32_x86\RndrGL.dll` | 939248 | `B07BAAC43CE4BBF6` |
| `Content\GameClasses_Win32_x86.dll` | 9016560 | `D7E81D7D3726D8F7` |
| `Content\GameWorld_Win32_x86.dll` | 4994288 | `A910A39BAE87F41C` |

Every patch looks for its byte pattern and leaves a file alone if it does not
match exactly, so another build is not damaged - it just goes without that fix.
`AodaFix.log` lists what was applied.

---

## Drop-in: AodaFix (recommended)

`dropin/` builds a 32-bit `winmm.dll` that the game loads by itself. It patches
the code in memory and writes the changed data (menus, fonts, texts, weapons,
shader include) to a cache folder on first start; the game reads those in place
of the originals. No Python, no launcher, no modified game file.

**Install:** copy `winmm.dll` and `AodaFix.ini` to `<Game>\System\Win32_x86\`.
**Remove:** delete both files and the `AodaFix_cache` folder.

* If you used the launcher before, run **Revert everything** there first - the
  drop-in only recognises the original files.
* All settings are in `AodaFix.ini` with comments, a log is written to
  `AodaFix.log`.

**Build:** `dropin\build.cmd` (MSVC Build Tools 2022, Python 3 with `pefile`).
`python dropin\tools\selftest.py <original tree> <launcher-patched tree> <work dir>`
maps the game modules without running them, applies the drop-in and compares
the result with what the Python scripts write.

---

## What it does

**Xbox 360 button prompts everywhere.** Menus, corner hints and inline text use
the original 360 artwork that ships with the game but is never shown on PC, in
its full colours instead of the washed-out `_32` variants. Button names in info
texts become icons. Help sits on L3 with an unambiguous stick icon.

**Console menus.** Six bytes in `MSystem.dll` decide which `PLATFORM_` symbols
the registry preprocessor defines - the Xbox 360 cube menu with its button
hints, the PC cube, or the PS3 cube (without the PS3 trophy installation).

**Tidier menu hints** *(drop-in)*. "Continue"/"Back" and their icons were drawn
at full line height; they are smaller now (`HintSize`, `HintIconSize`), the icons
stay round on the stretched inventory overlay, and the help bar's icon sits next
to its label.

**Working vibration.** The PC port ships the complete envelope data -
`Content\Feedback\feedback.xrg` is byte for byte the Xbox 360 file - but no
output stage: `XInputSetState` appears in no PC binary. The envelopes are read,
up to eight effects mixed at 60 Hz and sent to both motors.

**4K without letterboxing.** The renderer stopped enumerating display modes
after 512; current systems report about 650 and 3840×2160 sits near the end, so
the game fell back to 1920×1440 (4:3, hence the bars). The limit is raised, the
window is borderless across the whole monitor, and the drop-in sets `VID_MODE`
to the desktop mode.

**Shader compatibility.** `System\GL\HLInclude_GLSL.xrg` uses the
three-argument `texture2D`/`textureCube`, which is not legal in a fragment
shader; current drivers reject it and the game aborts in
`CRenderContextGL::GLSL_LoadSrc`. The bias argument is dropped. The drop-in also
fixes the shipped `XR_SHADERMODE=11` (valid: 0-6) that crashes a fresh install.

**Aim assist you can actually switch off.** The options slider is inert - its
value is stored but never read. The real switch is the weapon flag `autoaim` on
23 weapons.

**Windows HDR** *(drop-in)*. With HDR on, the game's gamma ramp is ignored and
the original ramp is restored on exit.

**Graphics settings** *(launcher)*. Every key the engine really reads from
`Environment.cfg`, with the module that reads it and its default, both taken
from the binaries rather than guessed.

---

## Launcher (alternative)

The launcher writes the same changes into the game files - useful to inspect a
single change, or where a proxy DLL is not wanted.

* Requirements: Windows, Python 3 with tkinter; **Pillow** for the fonts
  component (`pip install pillow`); MSVC Build Tools only to rebuild the
  vibration DLL (a compiled copy is included).
* Start `RiddickLauncher.cmd` and pick `<Game>\System\Win32_x86\DarkAthena.exe`.
  The choice and the interface language are remembered in
  `%LOCALAPPDATA%\RiddickLauncher\launcher.json`.
* Before a file is changed for the first time it is copied to
  `<Game>\_LauncherBackup\`; **Revert everything** restores all copies and
  removes anything that was added. `Environment.cfg` gets its own backup.

| Component | What it touches |
|---|---|
| `kern`    | GameClasses, GameWorld, MSystem, CubeWnd.xrg, CubeInv0.xrg |
| `grafik`  | RndrGL.dll - borderless window, 4K mode list, viewport |
| `schrift` | Text.xfc, Subtitle.xfc, Headings.xfc - coloured button icons |
| `texte`   | Frontend / StringsX360 string tables |
| `rumble`  | RiddickRumble.dll + .ini |

Each component is produced by the scripts in `patches/`, which also run on their
own - every one takes a path and has `--apply` and `--restore`.

## Layout

```
dropin/               AodaFix - the drop-in winmm.dll (C++), build script, self test
RiddickLauncher.pyw   launcher interface
rmod.py               launcher logic: paths, backups, components, settings
sprachen.py           German / English strings
patches/              the patch scripts, one per concern
rumble/               vibration DLL for the launcher, C source and a prebuilt binary
tools/                fix_riddick_dds.py - repairs DDS files written by the
                      game's own exporter (wrong FourCC, mip count off by one)
docs/                 what the reverse engineering turned up
```

## Licence

MIT, see [LICENSE](LICENSE). This covers the code in this repository. It is a
tool that modifies an installation you own; it neither contains nor
distributes any part of the game.

This is an unofficial, fan-made tool. It is not affiliated with, endorsed by
or connected to Starbreeze Studios, Atari or any present rights holder.
*The Chronicles of Riddick* and all related names belong to their respective
owners.
