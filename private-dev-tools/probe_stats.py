"""Locate a player's season-stats block in live memory by fingerprint.

For each reference player: find every place their minutes value appears (as u16
and as u32), then score the surrounding window by how many of their other stat
values sit at aligned offsets nearby. A real stats block should match most of
them; random hits match a few. Prints the best windows and the offset of each
field relative to the minutes field, so layouts can be compared across players.
"""
import struct
import sys
import time
from collections import Counter

from game import engine_build
from oracle import INT_STATS, Oracle
from winproc import Process

WINDOW = 0x180  # bytes searched either side of the anchor


def field_offsets(buf: bytes, anchor: int, want: dict, width: int) -> dict:
    """For each wanted field, offsets (relative to anchor) where its value appears."""
    fmt = "<H" if width == 2 else "<I"
    lo = max(0, anchor - WINDOW) & ~(width - 1) | (anchor & (width - 1))
    hi = min(len(buf) - width, anchor + WINDOW)
    by_value = {}
    for k, v in want.items():
        by_value.setdefault(v, []).append(k)
    found = {}
    for off in range(lo, hi + 1, width):
        v = struct.unpack_from(fmt, buf, off)[0]
        for k in by_value.get(v, ()):
            found.setdefault(k, []).append(off - anchor)
    return found


def probe(p: Process, player: dict, top: int = 5):
    want = {k: player[k] for k in INT_STATS if player.get(k) and player[k] >= 2}
    anchor_v = player["minutes"]
    hits = []
    t = time.time()
    for width in (2, 4):
        pat = struct.pack("<H" if width == 2 else "<I", anchor_v)
        for base, buf in p.chunks(p.regions(private_only=True)):
            i = buf.find(pat)
            while i != -1:
                if i % width == 0:
                    f = field_offsets(buf, i, want, width)
                    score = len(f)
                    if score >= 8:
                        hits.append((score, width, base + i, f))
                i = buf.find(pat, i + 1)
    hits.sort(key=lambda h: -h[0])
    print(f"\n=== {player['uid']} {player['name']} ({len(want)} fields >=2, minutes={anchor_v}) "
          f"- {len(hits)} windows scored >=8 in {time.time() - t:.0f}s")
    for score, width, addr, f in hits[:top]:
        print(f"  score {score}/{len(want)}  u{width * 8}  minutes @ 0x{addr:X}")
        # nearest offset per field
        rel = {k: min(v, key=abs) for k, v in f.items()}
        print("   ", ", ".join(f"{k}{rel[k]:+#x}" for k in sorted(rel, key=rel.get)))
    return hits


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    o = Oracle()
    with Process.attach() as p:
        print("build", engine_build(p).id)
        layouts = []
        for pl in o.candidates(n):
            h = probe(p, pl)
            if h:
                best = h[0]
                layouts.append({k: min(v, key=abs) for k, v in best[3].items()})
        if len(layouts) > 1:
            agree = Counter()
            for k in INT_STATS:
                offs = [lay.get(k) for lay in layouts]
                if None not in offs and len(set(offs)) == 1:
                    agree[k] = offs[0]
            print(f"\nfields at the SAME offset in all {len(layouts)} best windows: {len(agree)}")
            for k, off in sorted(agree.items(), key=lambda kv: kv[1]):
                print(f"  {off:+#06x}  {k}")
