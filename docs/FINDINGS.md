# What the reverse engineering turned up

Notes on the PC build of *The Chronicles of Riddick: Assault on Dark Athena*
(retail, 2009). Addresses are relative to each module's preferred base
(`0x10000000`); all three DLLs share it, so always check which module a value
belongs to.

No game content is reproduced here — this is a description of how the
software behaves.

---

## The engine

Starbreeze's Ogier engine. Data lives in `MOS DATAFILE2.0` containers
(`.xrg` text, `.xcr` compiled, `.xtc` textures, `.xfc` fonts). Three modules
carry the logic: `MSystem.dll` (platform, registry, input), `RndrGL.dll`
(OpenGL renderer), `MXR.dll` (effects), plus `GameClasses`/`GameWorld` under
`Content\`.

There is only an OpenGL path. `MSystem` knows `OpenGL` (loads `RndrGL.DLL`)
and `NULL`; no Direct3D string exists anywhere.

## The platform switch

`MSystem` decides in a single function which `PLATFORM_` symbols the registry
preprocessor defines. It reads the platform field and jumps through a table:
1 XBOX, 2 PS2, 3 DOLPHIN, 4 XENON, 5 PS3, otherwise WIN.

```
8b 40 68     mov eax,[eax+0x68]      <- the real platform
83 c0 ff     add eax,-1
83 f8 04     cmp eax,4
```

Replacing the first six bytes with `b8 <index> 00 00 00 90` pins the index.
With 3 (XENON) the menus, button prompts and the vibration entry all follow
the console branch. That is the whole switch.

## Display modes: why 4K was invisible

`ModeList_Init` (`MDispGL.cpp`, RndrGL `0x10040380`) calls
`EnumDisplaySettingsA` in a loop and stops after 512 entries:

```
100405b1  cmp eax, 0x200
100405ba  jl  0x100403c0
```

Windows reports about 650 modes on a current system. 3840×2160 sits at
positions 637–649, so it never made the list; the first mode larger than
1920×1440 is at 528, also past the limit. The "best match" search therefore
picked 1920×1440 — 4:3, hence the bars — and wrote that back to
`VID_MODE`. The apparent "the game overwrites my settings" was the game
faithfully recording what its own search had returned.

`VID_MODE` is not a switch but a mode description: `width height depth Hz`,
default `640 480 32 85`, separators space or comma. Only the literal word
`desktop` branches off into the windowed path — which is where the border and
letterbox trouble comes from.

## Vibration

Everything is present except the output.

* `Content\Feedback\feedback.xrg` holds 59 envelopes, two channels each (the
  two motors), points of `*TIME` in seconds and `*FORCE` from 0 to 1. The file
  is byte for byte the one the Xbox 360 version ships.
* GameClasses `0x102c5120` maps a rumble id of 1–29 onto effect names through
  the jump table at `0x102c554c`, checks `GAME_VIBRATION`, writes the name
  into a `CStr` — and discards it. A gutted stub.
* `XInputSetState` occurs in no PC binary; `MSystem` resolves only
  `XInputGetState` from `xinput1_3.dll`.
* The Xbox 360 executable imports `XamInputSetState` (ordinal `0x192` from
  `xam.xex`), so on the console it went through the standard API.

Of the three call sites of the dispatcher, the interesting one is the client
message handler at `0x1034623e`: the id arrives in the message
(`movsx edx, byte ptr [esi+2]`), so all 29 effects can occur. Observed in a
play session: assault rifle, shotgun and taking damage, plus explosions.

## Aim assist

The same pattern: the mechanism stayed, the setting was cut.

* `autoaim` is bit 9 of the item flags and is genuinely set on 23 weapons in
  `RpgWeapons.xrg`. `noaimassistance` (bit 23) and `noautoaim` (bit 24) are
  the per-character opt-outs and are used.
* The menu slider writes `OPT\CONTROLLER_AUTOAIM`. GameClasses `0x1030aad0`
  reads it with a default of 0.7, multiplies by a factor derived from
  `GAME_DIFFICULTY` and stores the result at `+0xac4` of the settings object.
  **Nothing ever reads that field.** All ten floating-point accesses to it lie
  between `0x10305e77` and `0x1030d2d5` and only set, copy and serialise it.

So aim assist is on or off, not a strength — and the weapon flag is the switch.

## Configuration keys

125 configuration keys occur in the binaries. The game fetches each one as

```
push <default> ; push "<KEY>" ; call [vtable+0x74]   (integer)
                                call [vtable+0x78]   (float)
                                call [vtable+0x70]   (string)
```

so the default sits right in front of the name and can be read off
mechanically. Two ranges were traced:

* **`R_ANTIALIAS`** — RndrGL `0x1005c6d0` splits the value into two 16-bit
  halves (`sar edx,16` / `and eax,0xffff`) and passes both to `0x1005c1e0`.
  There, 1 means off, the smaller half wins and it is clamped to what the
  hardware reports. So `(n<<16)|n` is the sensible form; the `1048592` found in
  the shipped config is exactly 16 samples.
* **`XR_SHADERMODE`** — 0 to 6. The names are in the game's own string table,
  `SYS_SHADERMODE0..6`: Auto, 0.5, 1.1, 1.1, 1.4, 2.0, 2.0++, each with a
  hardware recommendation.

Note that the shipped `Environment.cfg` carries `XR_SHADERMODE=11`, which is
outside that range.

Several keys present in the file are read by nobody: `VID_PIXELASPECT`,
`VID_CABLEPROFILE`, `VID_GAMMARAMP`, `SND_ENABLE`, `SKIPINTRO`,
`ENABLE_MULTITHREAD`. The `VIDEO_*` group goes through `[vtable+0x6c]`, the
menu's own `OPT\` branch — not the same thing as the renderer keys.

## Fonts

The 2D layer is a fixed virtual surface of 640×480; 267 GUI windows declare
`*RGN 0,0,640,480` and the glyph renderer divides by 640.0 and 480.0. That is
4:3 SDTV — the format *Escape from Butcher Bay* was designed for in 2004, and
the reason the type looks oversized. Higher resolution makes it sharper, never
smaller.

`.xfc` files carry a `CHARDESC` entry: n characters of 34 bytes each.

```
offset  0   int16   offset X
        2   int16   offset Y
        4   float   u0
        8   float   v0
       12   float   u1
       16   float   v1
       20   float   width      pixel width of the drawn quad
       24   float   height
       28   int16   -
       30   int16   advance
       32   uint16  character code
```

Verified across all 474 characters of the three fonts: `(u1-u0) * atlas width`
equals `width` exactly. Scaling those two floats down has no visible effect in
game, though — the renderer derives the quad from the UV rectangle.

`ORIGINALSIZE` is the size the atlas was rendered at: 35/26.923 = 1.3000,
36/27.692 = 1.2996, 31/23.846 = 1.3000, i.e. 130 % leading throughout.

## Button artwork

`GUI.xtc` holds 56 button glyphs in two families: an unprefixed set (Xbox 360,
including `GUI_Button_360_*`) and a `PS3_` set. There is no original-Xbox set —
no Black and White buttons, and `LB`/`RB` exist, which the first Xbox
controller did not have.

Each of A, B, X and Y appears twice, once plain and once as `_32`. Both are
32×32, so `_32` is not a size but different artwork — noticeably paler:

| | plain | `_32` |
|---|---|---|
| B | RGB (126, 48, 39) | (171, 94, 67) |
| A | (70, 123, 53) | (111, 137, 55) |
| X | (44, 63, 125) | (95, 120, 169) |
| Y | (144, 122, 23) | (188, 155, 22) |

The Xbox 360 atlas contains no `_32` variants at all. The console names them in
its descriptors, finds nothing and draws the full version — which is why B is
dark red there and orange on PC.

## String tables

The tables that matter are under `Content_Ger\Registry\Stringtables\*.txt` and
`Content\Registry\Stringtables\*.txt` — **not** `StringTable_*.txt`, which is
only the `*INCLUDE` list, and not the `Stringtables.zip` sitting next to them,
which is never read. Most are UTF-16LE with a BOM, a few are Latin-1. Any byte
search for ASCII text comes up empty.

## Shaders

`System\GL\HLInclude_GLSL.xrg` declares

```
float4 tex2DBias(sampler2D _tex, float2 _st, float _bias)
    { return texture2D(_tex, _st, _bias); }
float4 texCubeBias(samplerCube _tex, float3 _str, float _bias)
    { return textureCube(_tex, _str, _bias); }
```

The bias form is not legal in a fragment shader. Older drivers accepted it,
newer ones reject it, the shader fails to compile and the game aborts in
`CRenderContextGL::GLSL_LoadSrc` — reporting "OpenGL: no error", because no GL
error code is set. Dropping the third argument from the call, leaving the
signatures alone, fixes it.

## The DDS exporter

`tools/fix_riddick_dds.py` repairs two header faults the game's own exporter
writes: the FourCC always says `DXT1` even where the payload is DXT5 (16 bytes
per 4×4 block instead of 8, recognisable from `dwPitchOrLinearSize`), and
`dwMipMapCount` is one too high everywhere — the 1×1 level is missing from the
data, so loaders read past the end of the file.
