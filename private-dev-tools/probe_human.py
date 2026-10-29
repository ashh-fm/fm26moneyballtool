"""Find the human manager object(s) and which club/team pointers they hold."""
import struct

from fm26 import CLUB_LONG, CLUB_SHORT, P_CONTRACT, P_LOANS, TEAM_CLUB, Game
from rtti import vtables_for

g = Game()
m = g.build.module
today = g.today()
teams, clubs = {}, {}
for a in g.players():
    c = g.p.ptr(a + P_CONTRACT)
    t = g.p.ptr(c + 0x10) if c else None
    if t:
        cl = g.p.ptr(t + TEAM_CLUB)
        teams[t] = cl
        if cl:
            clubs[cl] = g.lstr(g.p.ptr(cl + CLUB_SHORT)) or g.lstr(g.p.ptr(cl + CLUB_LONG))
print(len(teams), "teams", len(clubs), "clubs")

for cls in (".?AVHUMAN_NON_PLAYER@db@@", ".?AVGAME_HUMAN_NON_PLAYER@@"):
    vts = vtables_for(g.p, m, cls)
    print(cls, {hex(v - m.base): hex(o) for v, o in vts.items()})
    for vt, off in vts.items():
        pat = struct.pack("<Q", vt)
        hits = []
        for base, buf in g.p.chunks(g.p.regions(private_only=True), overlap=0):
            i = buf.find(pat)
            while i != -1:
                if i % 8 == 0:
                    hits.append(base + i)
                i = buf.find(pat, i + 8)
        print(f"  vt +{vt - m.base:X} off {off:X}: {len(hits)} instances")
        for h in hits[:6]:
            obj = h - off
            b = g.p.read(obj, 0x600) or b""
            for o in range(0, len(b) - 7, 8):
                q = struct.unpack_from("<Q", b, o)[0]
                if q in clubs:
                    print(f"    obj {obj:X} +{o:X} -> club {clubs[q]}")
                elif q in teams:
                    print(f"    obj {obj:X} +{o:X} -> team of {clubs.get(teams[q])}")
                else:
                    # one level down: contract-like object whose +0x10 is a team
                    t = g.p.ptr(q + 0x10) if 0x10000 < q < 1 << 47 else None
                    if t in teams:
                        print(f"    obj {obj:X} +{o:X} -> [+10] team of {clubs.get(teams[t])}")
