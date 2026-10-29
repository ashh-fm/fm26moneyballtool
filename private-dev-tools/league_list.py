"""Write every league that has players in the game, with its nation and player count,
to league_list.json (used to build the name aliases for the ranking table)."""
import json
from collections import Counter

from fm26 import P_CONTRACT, P_LOANS, TEAM_COMP, COMP_NAME, NATION_NAME, Game

COMP_NATION = 0x60

if __name__ == "__main__":
    g = Game()
    p, today = g.p, g.today()
    count, nation = Counter(), {}
    for a in g.players():
        t = g.current_team(p.ptr(a + P_CONTRACT), p.ptr(a + P_LOANS), today)
        comp = p.ptr(t + TEAM_COMP) if t else None
        name = g.lstr(p.ptr(comp + COMP_NAME)) if comp else None
        if not name:
            continue
        count[name] += 1
        if name not in nation:
            n = p.ptr(comp + COMP_NATION)
            nation[name] = g.lstr(p.ptr(n + NATION_NAME)) if n else None
    out = [{"league": k, "nation": nation[k], "players": v} for k, v in count.most_common()]
    with open("league_list.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=0)
    print(len(out), "leagues")
