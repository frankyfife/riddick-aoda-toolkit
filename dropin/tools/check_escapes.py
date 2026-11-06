# Reports C/C++ string literals with escape sequences the compiler would not
# accept (guards against shell tools that swallow backslashes).
import re, glob, sys, os
root = sys.argv[1] if len(sys.argv) > 1 else "."
lit = re.compile(r'"((?:[^"\\]|\\.)*)"')
bad = 0
for f in glob.glob(os.path.join(root, "*.cpp")) + glob.glob(os.path.join(root, "*.h")):
    if f.endswith("glyph_art.h") or f.endswith("proxy_names.h"):
        continue
    for i, l in enumerate(open(f, encoding="latin-1"), 1):
        if l.strip().startswith("//"):
            continue
        for m in lit.finditer(l):
            for e in re.finditer(r"\\(.)", m.group(1)):
                if e.group(1) not in "nrt0x\\\"'a":
                    print("%s:%d: %s" % (os.path.basename(f), i, l.strip()[:110]))
                    bad += 1
print("bad escapes:", bad)
