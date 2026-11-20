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

* If an older version of this project patched your installation in place, put
  the original files back first (copy `<Game>\_LauncherBackup\` over it). The
  drop-in only recognises the originals.
* All settings are in `AodaFix.ini` with comments, a log is written to
  `AodaFix.log`.

**Build:** `dropin\build.cmd` (MSVC Build Tools 2022, Python 3 with `pefile`).
`python dropin\tools\selftest.py <original tree> <script-patched tree> <work dir>`
maps the game modules without running them, applies the drop-in and compares
the result with what the Python scripts write.

---

## What it does

**Xbox 360 button prompts everywhere.** Menus, corner hints and inline text use
the original 360 artwork that ships with the game but is never shown on PC, in
its full colours instead of the washed-out `_32` variants. Button names in info
texts become icons. The two stick clicks get icons of their own instead of
sharing one. An action has two bindings, keyboard first and pad second, and the
info and help texts name the first: on a new profile that is the key, not the
button. The drop-in hands those texts the pad binding (`TextButtons`), the
profile itself stays as it is.

**Help on the controller** *(drop-in)*. The help bar shows B, as on the console,
and B opens the help while that bar is on screen; the rest of the time B does
what it is bound to. No binding is changed and F1 keeps working. Another button
can be chosen with `HelpButton`, and `HelpButtonOpensHelp=0` leaves it at the
icon.

**Console menus.** Six bytes in `MSystem.dll` decide which `PLATFORM_` symbols
the registry preprocessor defines - the Xbox 360 cube menu with its button
hints, the PC cube, or the PS3 cube (without the PS3 trophy installation). The
console menus have no profiles of their own, on the console the system supplies
one, so they get the PC's profile list: a new installation can create its
profile there, and the Xbox options page offers "Profiles" where it had "select
storage device". Where the name is typed, X deletes the last character
(`XDeletesCharacter`, drop-in): the on-screen keyboard has no key for it.

**Every language of the game** *(drop-in)*. The button icons sit on letters none
of the five languages uses, counted over string tables, dialogues and credits;
the title screen and the pause menu are adapted in all of them, and the stick
directions are named in the game's language (`AxisNames`).

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

**Display scaling** *(drop-in)*. The game declares no DPI awareness, so above
100 % scaling Windows virtualises its window: user32 reports logical pixels to
the engine while the display mode it renders at stays physical. Window and back
buffer no longer match and the picture reaches past the screen edges, so only
part of it is visible. The drop-in declares the process DPI aware in `DllMain`,
before the game has a window (`[Display] DpiAware`). An exe that already carries
the *Override high DPI scaling behaviour* compatibility flag is left as it is.
`AodaFix.log` notes the display mode, the window, the monitor and the DPI, which
is what a report of a cut off picture needs.

**Shader compatibility.** `System\GL\HLInclude_GLSL.xrg` uses the
three-argument `texture2D`/`textureCube`, which is not legal in a fragment
shader; current drivers reject it and the game aborts in
`CRenderContextGL::GLSL_LoadSrc`. The bias argument is dropped. The drop-in also
fixes the shipped `XR_SHADERMODE=11` (valid: 0-6) that crashes a fresh install.

**Aim assist you can actually switch off.** The options slider is inert - its
value is stored but never read. The real switch is the weapon flag `autoaim` on
23 weapons.

**A controller switched on later** *(drop-in, `LateController`)*. The engine
builds its input devices once at start, so a pad that was off then stayed dead
until the next start. Its own per-frame update can rebuild them; the drop-in
triggers that as soon as XInput reports a pad the game has no device for.

**Language** *(drop-in, `Language=en|de|fr|it|es`)*. The game has no menu for
it; the setting is written to `LANGUAGE` in `Environment.cfg` and applies from
the next start, if that language is installed.

**Everything unlocked, for testing** *(drop-in, `UnlockAll=1`, off by default)*.
All extras are unlocked, and the developers' menus that still ship with the game
lose their cheat gate: the list of all maps (X or Space in the main menu, then
"Zones") and the debug menu (X or Space in the pause menu). The game's own
chapter list is left alone - it shows the chapter saves a profile has.

**Windows HDR** *(drop-in)*. With HDR on, the game's gamma ramp is ignored and
the original ramp is restored on exit.

**Graphics settings.** Every key the engine really reads from `Environment.cfg`,
with the module that reads it and its default, is listed in
[docs/FINDINGS.md](docs/FINDINGS.md), read off the binaries rather than guessed.
The drop-in itself only touches `VID_MODE` and an out-of-range `XR_SHADERMODE`;
the rest you set in the file yourself.

---

## The patch scripts

`patches/` holds the original Python patches, one per concern, which write the
same changes into the game files instead of into memory. They are kept for two
reasons: they are the reference the drop-in is checked against, byte for byte, by
`dropin/tools/selftest.py`, and each one documents a single change in isolation.
Every one takes a path and has `--apply` and `--restore`. One exception: the
rumble hook in `patch_gamepad_glyphs.py` calls a helper DLL that is no longer
shipped, and falls back to a stub that does nothing if it is absent. The drop-in
has that code built in.

They are no longer the way to install anything. Up to version 1.0.1 a Python
launcher drove them; it has been dropped now that the drop-in covers the same
ground without touching a game file. What it knew about `Environment.cfg` is in
[docs/FINDINGS.md](docs/FINDINGS.md).

## Layout

```
dropin/               AodaFix - the drop-in winmm.dll (C++), build script, self test
patches/              the Python patches, one per concern, and the self test's
                      reference for what each change has to produce
tools/                fix_riddick_dds.py - repairs DDS files written by the
                      game's own exporter (wrong FourCC, mip count off by one)
docs/                 what the reverse engineering turned up
```

## Licence

GNU General Public License v3.0, see [LICENSE](LICENSE). This covers the code
in this repository. It is a
tool that modifies an installation you own; it neither contains nor
distributes any part of the game.

This is an unofficial, fan-made tool. It is not affiliated with, endorsed by
or connected to Starbreeze Studios, Atari or any present rights holder.
*The Chronicles of Riddick* and all related names belong to their respective
owners.
