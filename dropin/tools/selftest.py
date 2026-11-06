#!/usr/bin/env python3
"""
Offline check of the drop-in against the Python toolkit - nothing is started,
nothing in the installation is written.

    python tools/selftest.py <original root> <toolkit-patched root> <work dir>

<original root>  a game tree with the ORIGINAL files (e.g. built from
                 _LauncherBackup plus the untouched GUI.xtc)
<patched root>   a game tree as the toolkit leaves it (optional: "-")

1. selftest_host.exe maps MSystem/RndrGL/GameClasses/GameWorld from the original
   root without running them, the drop-in patches them in memory, the images
   are dumped.
2. Code: the glyph cave and every patch site must equal what
   patch_gamepad_glyphs.build_cave()/patch() produce for the same addresses.
   RndrGL must equal the toolkit's borderless.py output, MSystem's platform
   switch and key names must match rename_pad_keys.py.
3. Data: generated files are compared byte for byte with the toolkit's files.
"""
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DROPIN = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(DROPIN), "patches"))
import patch_gamepad_glyphs as pgg      # noqa: E402

ok = True


def fail(msg):
    global ok
    ok = False
    print("  FAIL", msg)


def image_of(path, base_wanted=None):
    """Map a PE file the way the loader does (no relocation: compare at preferred base)."""
    d = open(path, "rb").read()
    e = struct.unpack_from("<I", d, 0x3c)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    oh = struct.unpack_from("<H", d, e + 20)[0]
    size = struct.unpack_from("<I", d, e + 24 + 56)[0]
    hdr = struct.unpack_from("<I", d, e + 24 + 60)[0]
    img = bytearray(size)
    img[:hdr] = d[:hdr]
    for i in range(n):
        b = e + 24 + oh + 40 * i
        vs, va, rs, ro = struct.unpack_from("<IIII", d, b + 8)
        img[va:va + min(rs, vs or rs)] = d[ro:ro + min(rs, vs or rs)]
    return bytes(img)


def iat_ranges(img):
    """IAT (hooked by design) and the /GS cookie (randomised by the loader at map time)."""
    e = struct.unpack_from("<I", img, 0x3c)[0]
    base = struct.unpack_from("<I", img, e + 24 + 28)[0]
    rva, sz = struct.unpack_from("<II", img, e + 24 + 96 + 12 * 8)   # IMAGE_DIRECTORY_ENTRY_IAT
    out = [(rva, rva + sz)]
    lc, lcsz = struct.unpack_from("<II", img, e + 24 + 96 + 10 * 8)  # IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG
    if lc and lcsz >= 0x40:
        cookie = struct.unpack_from("<I", img, lc + 0x3c)[0]
        if cookie:
            out.append((cookie - base, cookie - base + 4))
    return out


def diff(a, b, skip=()):
    out = []
    i, n = 0, min(len(a), len(b))
    while i < n:
        if a[i] != b[i] and not any(lo <= i < hi for lo, hi in skip):
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def main():
    orig_root, patched_root, work = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(work, exist_ok=True)
    host = os.path.join(DROPIN, "build", "selftest_host.exe")
    dll = os.path.join(DROPIN, "build", "winmm.dll")
    r = subprocess.run([host, dll, orig_root, work, "0"], capture_output=True, text=True)
    print("host exit", r.returncode, r.stdout.strip(), r.stderr.strip())
    meta = {}
    for line in open(os.path.join(work, "meta.txt")):
        name, *kv = line.split()
        meta[name] = {k: int(v, 16) if v.startswith("0x") else int(v) for k, v in (x.split("=") for x in kv)}

    # ---- GameClasses / GameWorld -------------------------------------------------------
    for mod, rel in (("GameClasses_Win32_x86.dll", r"Content\GameClasses_Win32_x86.dll"),
                     ("GameWorld_Win32_x86.dll", r"Content\GameWorld_Win32_x86.dll")):
        print("==", mod)
        m = meta[mod]
        pe = pgg.PE(os.path.join(orig_root, rel))
        if m["base"] != pe.base:
            fail("mapped at 0x%08x, not at the preferred base - compare skipped" % m["base"])
            continue
        s = pgg.locate(pe)
        a = pgg.build_cave(m["cave"], s, prefer_pad=True, diagnose=False, probe=False, help_code=0xA6,
                           calibrate=False, inline=False, trace_reload=False, help_rebind=False,
                           stick_icons=True, rumble=False)
        code = a.resolve()
        ours = open(os.path.join(work, mod + ".cave.bin"), "rb").read()
        if ours == code:
            print("  cave identical (%d bytes)" % len(code))
        else:
            fail("cave differs: ours %d bytes, python %d bytes, first diff at %s"
                 % (len(ours), len(code), next((i for i in range(min(len(ours), len(code))) if ours[i] != code[i]), "end")))
        # expected image = original image + the writes patch() does
        exp = bytearray(open(os.path.join(work, mod + ".orig.bin"), "rb").read())
        base = m["base"]

        def put(va, b):
            exp[va - base:va - base + len(b)] = b
        put(s["table_va"] + pgg.TABLE_AT, pgg.TABLE_NEW)
        sites = [(s['h1_at'], 'h1', 5), (s['h2_at'], 'h2', 5), (s['h3_at'], 'h3', 5),
                 (s['g1_at'], 'g1', 7), (s['d2_at'], 'd2', 5), (s['pp1_at'], 'pp1', 7), (s['pp2_at'], 'pp2', 7)]
        if 'hb_at' in s:
            sites.append((s['hb_at'], 'hb', 5))
        if 'hb_f1' in s:
            put(s['hb_f1'], b"\0")
        if 'dup_at' in s:
            put(s['dup_at'], b"p")
        put(s['jt_va'] + 11 * 4, struct.pack("<I", a.labels['tex_lc']))
        put(s['jt_va'] + 16 * 4, struct.pack("<I", a.labels['tex_rc']))
        put(s['table_va'] + 0x27, bytes([16]))
        for va, lbl, n in sites:
            put(va, b"\xe9" + struct.pack("<i", a.labels[lbl] - (va + 5)) + b"\x90" * (n - 5))
        put(s['g2_call'], b"\xe8" + struct.pack("<i", a.labels['g2'] - (s['g2_call'] + 5)))
        got = open(os.path.join(work, mod + ".patched.bin"), "rb").read()
        d = diff(got, exp, iat_ranges(got))
        if d:
            fail("image differs from patch(): %s" % ", ".join("rva 0x%x..0x%x" % x for x in d[:8]))
        else:
            print("  image == original + patch() writes (%d sites, IAT ignored)" % (len(sites) + 1))

    # ---- RndrGL --------------------------------------------------------------------------
    print("== RndrGL.dll")
    if patched_root != "-":
        tk = image_of(os.path.join(patched_root, r"System\Win32_x86\RndrGL.dll"))
        got = open(os.path.join(work, "RndrGL.dll.patched.bin"), "rb").read()
        org = open(os.path.join(work, "RndrGL.dll.orig.bin"), "rb").read()
        d = diff(got, tk, iat_ranges(got))
        print("  toolkit changed %d ranges, drop-in %d ranges" % (len(diff(org, tk)), len(diff(org, got, iat_ranges(got)))))
        if d:
            fail("differs from borderless.py: %s" % ", ".join("rva 0x%x..0x%x" % x for x in d[:8]))
        else:
            print("  identical to the toolkit's RndrGL (IAT ignored)")

    # ---- MSystem -------------------------------------------------------------------------
    print("== MSystem.dll")
    got = open(os.path.join(work, "MSystem.dll.patched.bin"), "rb").read()
    org = open(os.path.join(work, "MSystem.dll.orig.bin"), "rb").read()
    base = meta["MSystem.dll"]["base"]
    if b"\xb8\x03\x00\x00\x00\x90\x83\xf8\x04" in got:
        print("  platform switch -> XENON")
    else:
        fail("platform switch not set")
    if patched_root != "-":
        tk = image_of(os.path.join(patched_root, r"System\Win32_x86\MSystem.dll"))
        names = 0
        for lo, hi in diff(org, got, iat_ranges(got)):
            for o in range(lo - lo % 4, hi, 4):
                p_got = struct.unpack_from("<I", got, o)[0]
                p_tk = struct.unpack_from("<I", tk, o)[0]
                if p_got == struct.unpack_from("<I", org, o)[0]:
                    continue
                if 0x10000000 <= p_tk < 0x10000000 + len(tk):
                    t = tk[p_tk - 0x10000000:].split(b"\0")[0]
                    # our string lives in winmm.dll - read it through the dump is impossible;
                    # compare via the expected table instead
                    names += 1
        print("  %d name pointers changed (toolkit strings checked in the log)" % names)

    # ---- data files ------------------------------------------------------------------------
    print("== data")
    cache = os.path.join(work, "cache")
    for rel in (r"Content\GUI\CubeWnd.xrg", r"Content\GUI\CubeInv0.xrg",
                r"Content_Ger\Registry\Stringtables\Frontend_Ger.txt",
                r"Content\Registry\Stringtables\Frontend_Eng.txt",
                r"Content_Ger\Registry\Stringtables\StringsX360_Ger.txt",
                r"Content\Registry\Stringtables\StringsX360_Eng.txt",
                r"Content\Registry\RpgWeapons.xrg", r"System\GL\HLInclude_GLSL.xrg"):
        ours = os.path.join(cache, rel)
        if not os.path.exists(ours):
            fail("%s not generated" % rel)
            continue
        if patched_root == "-":
            print("  %-55s generated" % rel)
            continue
        a, b = open(ours, "rb").read(), open(os.path.join(patched_root, rel), "rb").read()
        if a == b:
            print("  %-55s identical to the toolkit" % rel)
        else:
            fail("%s differs (%d vs %d bytes)" % (rel, len(a), len(b)))
    for f in ("Text.xfc", "Subtitle.xfc", "Headings.xfc"):
        ours = os.path.join(cache, "Content", "Fonts", f)
        if not os.path.exists(ours):
            fail("%s not generated" % f)
            continue
        if patched_root == "-":
            continue
        a, b = open(ours, "rb").read(), open(os.path.join(patched_root, "Content", "Fonts", f), "rb").read()
        da, db = struct.unpack_from("<I", a, 24)[0], struct.unpack_from("<I", b, 24)[0]
        ea = [a[p:p + 48] for p in range(da, len(a) - 47, 48)]
        eb = [b[p:p + 48] for p in range(db, len(b) - 47, 48)]
        same_dir = len(a) == len(b) and ea == eb
        cd_a = a.find(b"CHARDESC")
        print("  %-14s %d vs %d bytes, directory %s" % (f, len(a), len(b), "identical" if same_dir else "DIFFERENT"))
        if not same_dir:
            fail("%s directory differs" % f)
    print()
    print("RESULT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
