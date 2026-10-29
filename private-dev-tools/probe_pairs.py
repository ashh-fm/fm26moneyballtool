"""Second probe: anchor on a pair of large, distinctive stats (e.g. passes attempted and
completed) sitting close together, in several encodings. If the pair is found, score the
window around it against all the player's other stats."""
import struct
import sys

from oracle import INT_STATS, Oracle
from probe_stats import field_offsets
from winproc import Process

PAIR_GAP = 0x40
ENCODINGS = {"u16": ("<H", 2), "u32": ("<I", 4), "f32": ("<f", 4)}


def pair_hits(p, a, b):
    out = []
    for name, (fmt, w) in ENCODINGS.items():
        pa, pb = struct.pack(fmt, a), struct.pack(fmt, b)
        for base, buf in p.chunks(p.regions(private_only=True)):
            i = buf.find(pa)
            while i != -1:
                if i % w == 0:
                    lo, hi = max(0, i - PAIR_GAP), i + PAIR_GAP
                    j = buf.find(pb, lo, hi + w)
                    while j != -1:
                        if j % w == 0:
                            out.append((name, w, base, buf, i, j - i))
                            break
                        j = buf.find(pb, j + 1, hi + w)
                i = buf.find(pa, i + 1)
    return out


if __name__ == "__main__":
    fa, fb = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("passes_attempted", "passes_completed")
    o = Oracle()
    with Process.attach() as p:
        for pl in o.candidates(3):
            want = {k: pl[k] for k in INT_STATS if pl.get(k) and pl[k] >= 2}
            hits = pair_hits(p, pl[fa], pl[fb])
            print(f"\n=== {pl['name']}: {fa}={pl[fa]} {fb}={pl[fb]} -> {len(hits)} pair hits")
            scored = []
            for enc, w, base, buf, i, gap in hits:
                if enc == "f32":
                    scored.append((0, enc, base + i, gap, {}))
                    continue
                f = field_offsets(buf, i, want, w)
                scored.append((len(f), enc, base + i, gap, f))
            scored.sort(key=lambda s: -s[0])
            for sc, enc, addr, gap, f in scored[:6]:
                rel = {k: min(v, key=abs) for k, v in f.items()}
                print(f"  {enc} @0x{addr:X} gap {gap:+#x} score {sc}/{len(want)}")
                if f:
                    print("    ", ", ".join(f"{k}{rel[k]:+#x}" for k in sorted(rel, key=rel.get)))
