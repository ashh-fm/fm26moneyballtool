"""List the leagues of every player's current team, with how many players have minutes
in each stats scope. python leagues.py [filter text]"""
import sys
from collections import Counter

from fm26 import SCOPES, TEAM_COMP, COMP_NAME, Game

if __name__ == "__main__":
    flt = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    g = Game()
    today = g.today()
    total, played = Counter(), {s: Counter() for s in SCOPES}
    for a in g.players():
        r = g.read_player(a, today, "competitive", require_minutes=False)
        if not r or not r["division"]:
            continue
        d = r["division"]
        if flt and flt not in d.lower():
            continue
        total[d] += 1
        for s, slot in SCOPES.items():
            e = g.season_entry(a, slot)
            if e and (g.p.u16(e + 0x0A) or 0) > 0:
                played[s][d] += 1
    print(f"game date {today}")
    print(f"{'league':45} {'players':>7} " + " ".join(f"{s[:11]:>11}" for s in SCOPES))
    for d, n in total.most_common(60):
        print(f"{d[:45]:45} {n:7} " + " ".join(f"{played[s][d]:11}" for s in SCOPES))
