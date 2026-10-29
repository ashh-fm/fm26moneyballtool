"""List RTTI class names in game_plugin.dll matching a pattern:  python classes.py MANAGER HUMAN"""
import re
import sys

from game import engine_build
from winproc import Process

with Process.attach() as p:
    m = engine_build(p).module
    image = b"".join(p.read(m.base + o, min(16 << 20, m.size - o)) or b"\0" * min(16 << 20, m.size - o)
                     for o in range(0, m.size, 16 << 20))
    names = sorted(set(re.findall(rb"\.\?AV[A-Za-z0-9_@?$]{2,120}@@", image)))
    pats = [s.upper().encode() for s in sys.argv[1:]]
    for n in names:
        if any(x in n.upper() for x in pats):
            print(n.decode())
