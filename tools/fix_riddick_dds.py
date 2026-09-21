#!/usr/bin/env python3
"""
Repariert DDS-Dateien, die der Riddick-Exporter kaputt geschrieben hat.

Zwei Fehler im Header:

1) FourCC steht immer auf "DXT1", auch bei Texturen, die in Wahrheit
   DXT5-Daten enthalten (16 Byte pro 4x4-Block statt 8).
   Erkennbar an dwPitchOrLinearSize: steht dort die DXT5-Groesse
   (blocks*16), sind die Daten DXT5.
2) dwMipMapCount ist bei ALLEN Dateien um 1 zu hoch - die kleinste
   Mip-Stufe (1x1) fehlt in den Daten. Loader lesen ueber das Dateiende.

Default: die fehlende letzte Mip wird aus der vorletzten erzeugt und
angehaengt (Mip-Kette bleibt vollstaendig). Mit --fix-count wird
stattdessen dwMipMapCount heruntergesetzt.

Aufruf:
    python fix_riddick_dds.py <ordner_oder_datei> [-o AUSGABEORDNER]
                              [--inplace] [--fix-count] [--dry-run]
"""

import argparse
import os
import struct
import sys

HDR = 128
OFF_FLAGS, OFF_H, OFF_W, OFF_PITCH, OFF_MIPS = 8, 12, 16, 20, 28
OFF_PF_FLAGS, OFF_FOURCC, OFF_CAPS = 80, 84, 108

DDSD_LINEARSIZE = 0x00080000
DDSD_MIPMAPCOUNT = 0x00020000
DDPF_FOURCC = 0x4


def blocks(w, h):
    return ((w + 3) // 4) * ((h + 3) // 4)


def chain_size(w, h, mips, bs):
    total = 0
    for _ in range(mips):
        total += blocks(w, h) * bs
        w, h = max(1, w // 2), max(1, h // 2)
    return total


def mip_dims(w, h, level):
    for _ in range(level):
        w, h = max(1, w // 2), max(1, h // 2)
    return w, h


def rgb565(c):
    return ((c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31)


def to565(r, g, b):
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def flat_block(block, bs):
    """Erzeugt einen 1x1-Block in der Durchschnittsfarbe von 'block'."""
    cb = block[8:16] if bs == 16 else block[0:8]
    c0, c1, idx = struct.unpack('<HHI', cb)
    p0, p1 = rgb565(c0), rgb565(c1)
    if c0 > c1 or bs == 16:
        pal = [p0, p1,
               tuple((2 * p0[i] + p1[i]) // 3 for i in range(3)),
               tuple((p0[i] + 2 * p1[i]) // 3 for i in range(3))]
    else:
        pal = [p0, p1, tuple((p0[i] + p1[i]) // 2 for i in range(3)), (0, 0, 0)]
    cols = [pal[(idx >> (2 * i)) & 3] for i in range(16)]
    avg = [sum(c[k] for c in cols) // 16 for k in range(3)]
    c = to565(*avg)
    colpart = struct.pack('<HHI', c, c, 0)
    if bs == 8:
        return colpart
    # DXT5-Alpha: Durchschnitt der 16 Alphawerte des Quellblocks
    a0, a1 = block[0], block[1]
    bits = int.from_bytes(block[2:8], 'little')
    tbl = [a0, a1]
    if a0 > a1:
        tbl += [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    else:
        tbl += [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
    aavg = sum(tbl[(bits >> (3 * i)) & 7] for i in range(16)) // 16
    return bytes([aavg, aavg]) + b'\x00' * 6 + colpart


def fix(raw, fix_count=False):
    """-> (neue_bytes, liste_der_aenderungen) oder (None, grund)"""
    if raw[:4] != b'DDS ' or len(raw) < HDR:
        return None, ['keine DDS-Datei']
    hdr = bytearray(raw[:HDR])
    data = raw[HDR:]
    h, w = struct.unpack_from('<II', hdr, OFF_H)
    pitch = struct.unpack_from('<I', hdr, OFF_PITCH)[0]
    mips = max(1, struct.unpack_from('<I', hdr, OFF_MIPS)[0])
    fourcc = bytes(hdr[OFF_FOURCC:OFF_FOURCC + 4])
    if fourcc not in (b'DXT1', b'DXT3', b'DXT5'):
        return None, ['unbekanntes Format %r' % fourcc]

    nb = blocks(w, h)
    # Blockgroesse aus den Fakten ableiten: erst LinearSize, dann Dateilaenge
    if pitch == nb * 16:
        bs = 16
    elif pitch == nb * 8:
        bs = 8
    elif len(data) in (chain_size(w, h, mips, 16), chain_size(w, h, mips, 16) - 16):
        bs = 16
    elif len(data) in (chain_size(w, h, mips, 8), chain_size(w, h, mips, 8) - 8):
        bs = 8
    else:
        return None, ['Groesse passt zu keinem Blockformat (%d Byte, %dx%d, %d Mips)'
                      % (len(data), w, h, mips)]

    log = []
    want = b'DXT5' if bs == 16 else b'DXT1'
    if fourcc != want:
        hdr[OFF_FOURCC:OFF_FOURCC + 4] = want
        log.append('FourCC %s -> %s' % (fourcc.decode('latin1'), want.decode('latin1')))

    full = chain_size(w, h, mips, bs)
    if len(data) < full:
        # wie viele Stufen sind vollstaendig da?
        have, off = 0, 0
        for lvl in range(mips):
            mw, mh = mip_dims(w, h, lvl)
            n = blocks(mw, mh) * bs
            if off + n > len(data):
                break
            off += n
            have += 1
        if off < len(data):
            log.append('%d Byte Rest am Ende entfernt' % (len(data) - off))
            data = data[:off]
        if have == 0:
            return None, ['nicht einmal Mip 0 vollstaendig']
        if fix_count:
            struct.pack_into('<I', hdr, OFF_MIPS, have)
            log.append('MipMapCount %d -> %d' % (mips, have))
            mips = have
        else:
            last = data[-bs:]
            add = b''
            for _ in range(mips - have):
                last = flat_block(last, bs)
                add += last
            data += add
            log.append('%d fehlende Mip-Stufe(n) ergaenzt (%d Byte)'
                       % (mips - have, len(add)))
    elif len(data) > full:
        log.append('%d Byte Ueberhang entfernt' % (len(data) - full))
        data = data[:full]

    if pitch != nb * bs:
        struct.pack_into('<I', hdr, OFF_PITCH, nb * bs)
        log.append('LinearSize %d -> %d' % (pitch, nb * bs))

    flags = struct.unpack_from('<I', hdr, OFF_FLAGS)[0]
    nf = flags | DDSD_LINEARSIZE | (DDSD_MIPMAPCOUNT if mips > 1 else 0)
    if nf != flags:
        struct.pack_into('<I', hdr, OFF_FLAGS, nf)
        log.append('Header-Flags korrigiert')
    pff = struct.unpack_from('<I', hdr, OFF_PF_FLAGS)[0]
    if not pff & DDPF_FOURCC:
        struct.pack_into('<I', hdr, OFF_PF_FLAGS, pff | DDPF_FOURCC)
        log.append('DDPF_FOURCC gesetzt')

    return bytes(hdr) + data, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src', help='Ordner oder einzelne .dds-Datei')
    ap.add_argument('-o', '--out', help='Ausgabeordner (Default: <src>-fixed)')
    ap.add_argument('--inplace', action='store_true', help='Dateien direkt ueberschreiben')
    ap.add_argument('--fix-count', action='store_true',
                    help='MipMapCount senken statt fehlende Mip zu ergaenzen')
    ap.add_argument('--dry-run', action='store_true', help='nur anzeigen, nichts schreiben')
    a = ap.parse_args()

    src = os.path.abspath(a.src)
    if os.path.isdir(src):
        files = [os.path.join(src, f) for f in sorted(os.listdir(src))
                 if f.lower().endswith('.dds')]
        base = src
    else:
        files, base = [src], os.path.dirname(src)
    if not files:
        sys.exit('keine .dds-Dateien in %s' % src)

    out = None
    if not a.inplace and not a.dry_run:
        out = a.out or (base.rstrip('\\/') + '-fixed')
        os.makedirs(out, exist_ok=True)

    ok = skip = 0
    for f in files:
        raw = open(f, 'rb').read()
        new, log = fix(raw, a.fix_count)
        name = os.path.basename(f)
        if new is None:
            print('SKIP %-40s %s' % (name, '; '.join(log)))
            skip += 1
            continue
        if not log:
            print('  OK %-40s war schon in Ordnung' % name)
        else:
            print(' FIX %-40s %s' % (name, '; '.join(log)))
        ok += 1
        if a.dry_run:
            continue
        dst = f if a.inplace else os.path.join(out, name)
        with open(dst, 'wb') as fh:
            fh.write(new)

    print('\n%d Dateien verarbeitet, %d uebersprungen.' % (ok, skip))
    if out:
        print('Ausgabe: %s' % out)


if __name__ == '__main__':
    main()
