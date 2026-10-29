"""FM26 live reader: find every player in the running game and read their data.

Read-only. All structure knowledge lives in the constants below, so a game patch means
updating one place. The player class is located by its RTTI name, not a fixed address.

Offsets were mapped by matching memory against known player stats; percentages quoted
are match rates over thousands of players on build 6A229F1E-1D8D3000.
"""
import datetime as dt
import struct
import time

from game import engine_build
from rtti import vtables_for
from winproc import Process

PLAYER_CLASS = ".?AVACTUAL_PLAYER@db@@"
PLAYER_SUBOBJECT = 0x288  # all player offsets are relative to this sub-object's vtable
LOAN_CLASS = ".?AVLOAN_CONTRACT@db@@"
HUMAN_CLASS = ".?AVHUMAN_NON_PLAYER@db@@"   # a human manager (you)
HUMAN_SUBOBJECT, HUMAN_CONTRACT = 0x478, 0x80

# --- player sub-object (P = address of the sub-object) ---------------------------
P_BEFORE, P_AFTER = 0x140, 0x2A0         # one read covers [P - BEFORE, P + AFTER)
P_ID, P_UID, P_UID2 = 0x08, 0x0C, 0x10
P_FULL_NAME, P_FIRST, P_LAST, P_COMMON = 0x40, 0x50, 0x58, 0x60
P_NATION, P_DOB, P_CONTRACT, P_LOANS = 0x68, 0x88, 0xA8, 0xB0
P_UPDATED = 0x11C                        # a per-player date; its max across players = today
P_STATS = 0x248                          # -> stats object + 0x88
P_POS = -0x138                           # 15 x u8 (1-20): GK SW DL DC DR DM ML MC MR AML AMC AMR ST WBL WBR
P_LEFT, P_RIGHT = -0x111, -0x110         # u8, 1-100 (x5 of the 1-20 shown in game)
P_HEIGHT, P_VALUE, P_CA, P_PA = -0x5A, -0x54, -0x24, -0x22
P_PERSONALITY = 0x70                     # 8 x u8: adaptability ambition loyalty pressure professionalism sportsmanship temperament controversy

CONTRACT_TEAM, CONTRACT_WAGE, CONTRACT_START, CONTRACT_END = 0x10, 0x20, 0x44, 0x48
CLUB_UID = 0x0C
TEAM_CLUB, TEAM_COMP = 0x30, 0x50
CLUB_LONG, CLUB_SHORT = 0xC0, 0xC8
COMP_NAME = 0x40
NATION_CODE, NATION_NAME = 0x28, 0x18

# --- season stats -----------------------------------------------------------------
STATS_TO_START = -0x88
SCOPES = {"competitive": 0x28, "league": 0x08, "all": 0x30, "cups": 0x10, "continental": 0x18}

# season entry (0x20 bytes): +0 -> record
ENTRY = {"rating_sum": (0x08, "H"), "minutes": (0x0A, "H"), "starts": (0x0C, "B"), "subs": (0x0D, "B"),
         "rated": (0x0E, "B"),  # appearances that received a rating; avg = rating_sum / (10 * rated)
         "goals": (0x0F, "B"), "assists": (0x10, "B"), "conceded": (0x11, "B"), "pens_taken": (0x12, "B"),
         "pens_scored": (0x13, "B"), "motm": (0x14, "B"), "red": (0x15, "B"), "yellow": (0x16, "B"),
         "clean_sheets": (0x17, "B")}

# stats record (0x78 bytes of u16; "h" = signed). Slots marked * hold goalkeeper stats for keepers.
RECORD = {"pas_att": 0x08, "pas_cmp": 0x0A, "tck_att": 0x0C, "tck_won": 0x0E,      # * pens faced / saved
          "hdr_att": 0x10, "hdr_won": 0x12,                                         # * saves held / parried
          "drb": 0x14, "fouls": 0x16, "fouls_won": 0x18, "shots": 0x1A, "sot": 0x1C,
          "distance10": 0x2E, "offsides": 0x30, "saves_tipped": 0x32, "op_crs_cmp": 0x34,
          "kp": 0x36, "tck_key": 0x38, "hdr_key": 0x3A, "int": 0x3C, "ccc": 0x3E, "blocks": 0x40,
          "poss_lost": 0x44, "poss_won": 0x46, "xg100": 0x48, "xa100": 0x4A, "clr": 0x4C,
          "fk": 0x50, "goals_out": 0x52, "op_crs_att": 0x5A, "shots_out": 0x5C, "xgp100": (0x5E, "h"),
          "sprints": 0x60, "pr_passes": 0x64, "pres_att": 0x66, "pres_cmp": 0x68, "op_kp": 0x6A,
          "npxg100": 0x6C, "crs_att": 0x70, "crs_cmp": 0x72, "shots_blk": 0x74, "hdr_lost": 0x76}

POS_NAMES = ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "AML", "AMC", "AMR", "ST", "WBL", "WBR"]
ACCOMPLISHED = 15  # FM lists natural (20) and accomplished (15+) positions


def unpack_date(raw: int):
    doy, year = raw & 0xFFFF, raw >> 16
    if not (1 <= doy <= 366 and 1850 < year < 2200):
        return None
    return dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)


def position_string(r: list[int]) -> str:
    """FM-style position text, e.g. 'D (RC), DM, M (C)'."""
    ok = {n for n, v in zip(POS_NAMES, r) if v >= ACCOMPLISHED}
    if not ok and r:
        ok = {POS_NAMES[max(range(len(r)), key=r.__getitem__)]}
    parts = []
    if "GK" in ok:
        parts.append("GK")
    for grp, pre in (("D", "D"), ("WB", "WB")):
        sides = "".join(s for s in "RLC" if f"{pre}{s}" in ok)
        if sides:
            parts.append(f"{grp} ({sides})")
    if "DM" in ok:
        parts.append("DM")
    for grp in ("M", "AM"):
        sides = "".join(s for s in "RLC" if f"{grp}{s}" in ok)
        if sides:
            parts.append(f"{grp} ({sides})")
    if "ST" in ok:
        parts.append("ST (C)")
    return ", ".join(parts)


class Game:
    def __init__(self):
        self.p = Process.attach()
        self.build = engine_build(self.p)
        m = self.build.module
        self.lo, self.hi = m.base, m.base + m.size
        vts = [v for v, off in vtables_for(self.p, m, PLAYER_CLASS).items() if off == PLAYER_SUBOBJECT]
        if not vts:
            raise RuntimeError("ACTUAL_PLAYER class not found - unsupported game build")
        self.player_vt = vts[0]
        self.loan_vt = next(iter(vtables_for(self.p, m, LOAN_CLASS)), None)
        self.human_vt = next((v for v, off in vtables_for(self.p, m, HUMAN_CLASS).items() if off == HUMAN_SUBOBJECT), None)
        self._players: list[int] | None = None
        self._humans: list[int] | None = None
        self._str: dict[int, str | None] = {}

    def close(self):
        self.p.close()

    # ---- discovery ----------------------------------------------------------
    def players(self, refresh: bool = False) -> list[int]:
        """Addresses of every ACTUAL_PLAYER sub-object (one pass over the heap)."""
        if self._players is not None and not refresh:
            return self._players
        self._humans = None
        pat = struct.pack("<Q", self.player_vt)
        out = []
        for base, buf in self.p.chunks(self.p.regions(private_only=True), overlap=0):
            i = buf.find(pat)
            while i != -1:
                if i % 8 == 0:
                    out.append(base + i)
                i = buf.find(pat, i + 8)
        live = []
        for a in sorted(set(out)):
            b = self.p.read(a + P_ID, 12)
            if b:
                _id, uid, uid2 = struct.unpack("<III", b)
                if uid and uid == uid2:
                    live.append(a)
        self._players = live
        return live

    def today(self) -> dt.date | None:
        best = None
        for a in self.players():
            d = unpack_date(self.p.u32(a + P_UPDATED) or 0)
            if d and (best is None or d > best):
                best = d
        return best

    # ---- strings ------------------------------------------------------------
    def lstr(self, a: int | None) -> str | None:
        """String stored as [u32 length][utf-8 bytes]; cached by address."""
        if not a:
            return None
        if a in self._str:
            return self._str[a]
        s = None
        n = self.p.u32(a)
        if n and n <= 400:
            b = self.p.read(a + 4, n)
            s = b.decode("utf-8", "replace") if b else None
        self._str[a] = s
        return s

    def name_ref(self, a: int | None) -> str | None:
        """Name-table entry: first field points at an lstr."""
        return self.lstr(self.p.ptr(a)) if a else None

    def club_name(self, club: int | None) -> str | None:
        return (self.lstr(self.p.ptr(club + CLUB_SHORT)) or self.lstr(self.p.ptr(club + CLUB_LONG))) if club else None

    # ---- the human manager ----------------------------------------------------
    def my_clubs(self) -> list[dict]:
        """Clubs managed by human players: each HUMAN_NON_PLAYER holds its job contract at
        +HUMAN_CONTRACT (same layout as a player contract: +0x10 is the team)."""
        if self._humans is None:
            pat = struct.pack("<Q", self.human_vt) if self.human_vt else None
            hits = []
            for base, buf in (self.p.chunks(self.p.regions(private_only=True), overlap=0) if pat else ()):
                i = buf.find(pat)
                while i != -1:
                    if i % 8 == 0:
                        hits.append(base + i)
                    i = buf.find(pat, i + 8)
            self._humans = hits
        out = []
        for h in self._humans:
            try:
                c = self.p.ptr(h + HUMAN_CONTRACT)
                team = self.p.ptr(c + CONTRACT_TEAM) if c else None
                club = self.p.ptr(team + TEAM_CLUB) if team else None
                name = self.club_name(club)
            except (OSError, struct.error, TypeError):
                continue
            if name and not any(o["name"] == name for o in out):
                out.append({"name": name, "uid": self.p.u32(club + CLUB_UID)})
        return out

    # ---- raw structures -----------------------------------------------------
    def stats_object(self, player: int) -> int | None:
        q = self.p.ptr(player + P_STATS)
        return q + STATS_TO_START if q else None

    def season_entry(self, player: int, slot: int = SCOPES["competitive"]) -> int | None:
        so = self.stats_object(player)
        return (self.p.ptr(so + slot) or None) if so else None

    def current_team(self, contract: int | None, loans: int | None, today: dt.date | None) -> int | None:
        """The team the player plays for: an active loan's team, else the contract's team.
        `loans` (player+0xB0) points at a node whose first field is the LOAN_CONTRACT."""
        loan = self.p.ptr(loans) if loans else None
        lb = self.p.read(loan, 0x50) if loan else None
        if lb and struct.unpack_from("<Q", lb, 0)[0] == self.loan_vt:
            start = unpack_date(struct.unpack_from("<I", lb, CONTRACT_START)[0])
            stop = unpack_date(struct.unpack_from("<I", lb, CONTRACT_END)[0])
            if not today or not start or not stop or start <= today <= stop:
                t = struct.unpack_from("<Q", lb, CONTRACT_TEAM)[0]
                if t:
                    return t
        return self.p.ptr(contract + CONTRACT_TEAM) if contract else None

    # ---- one player ---------------------------------------------------------
    def read_player(self, a: int, today: dt.date, scope: str = "competitive", require_minutes=True):
        slot = SCOPES[scope]
        entry = self.season_entry(a, slot)
        eb = self.p.read(entry, 0x20) if entry else None
        e = {k: struct.unpack_from("<" + f, eb, o)[0] for k, (o, f) in ENTRY.items()} if eb else None
        if require_minutes and (not e or not e["minutes"]):
            return None
        rec = dict.fromkeys(RECORD, 0)  # some entries have no detailed record: count as zeros
        if eb:
            rp = struct.unpack_from("<Q", eb, 0)[0]
            rb = self.p.read(rp, 0x78) if rp else None
            if rb:
                for k, spec in RECORD.items():
                    off, f = spec if isinstance(spec, tuple) else (spec, "H")
                    rec[k] = struct.unpack_from("<" + f, rb, off)[0]

        b = self.p.read(a - P_BEFORE, P_BEFORE + P_AFTER)
        if not b:
            return None
        u8 = lambda o: b[P_BEFORE + o]
        u32 = lambda o: struct.unpack_from("<I", b, P_BEFORE + o)[0]
        ptr = lambda o: struct.unpack_from("<Q", b, P_BEFORE + o)[0]

        common = self.name_ref(ptr(P_COMMON))
        first, last = self.name_ref(ptr(P_FIRST)), self.name_ref(ptr(P_LAST))
        name = common or " ".join(x for x in (first, last) if x) or self.lstr(ptr(P_FULL_NAME)) or "?"

        nation = ptr(P_NATION)
        contract = ptr(P_CONTRACT)
        team = self.current_team(contract, ptr(P_LOANS), today)
        club = self.p.ptr(team + TEAM_CLUB) if team else None
        home = self.p.ptr(contract + CONTRACT_TEAM) if contract else None   # club holding the contract
        owner = self.p.ptr(home + TEAM_CLUB) if home else None
        comp = self.p.ptr(team + TEAM_COMP) if team else None
        cb = self.p.read(contract, 0x50) if contract else None
        dob = unpack_date(u32(P_DOB))
        age = None
        if dob and today:
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        pos = list(b[P_BEFORE + P_POS: P_BEFORE + P_POS + 15])
        lf, rf = u8(P_LEFT), u8(P_RIGHT)
        foot = "Either" if abs(lf - rf) <= 10 and min(lf, rf) >= 70 else ("Left" if lf > rf else "Right")
        return {
            "uid": u32(P_UID), "name": name, "pos": pos, "position": position_string(pos), "age": age,
            "dob": dob.isoformat() if dob else None,
            "nat": self.lstr(self.p.ptr(nation + NATION_CODE)) if nation else None,
            "nation": self.lstr(self.p.ptr(nation + NATION_NAME)) if nation else None,
            "club": self.club_name(club),
            "club_uid": self.p.u32(club + CLUB_UID) if club else None,
            "owner": self.club_name(owner) if owner != club else None,
            "owner_uid": self.p.u32(owner + CLUB_UID) if owner and owner != club else None,
            "division": self.lstr(self.p.ptr(comp + COMP_NAME)) if comp else None,
            "wage": struct.unpack_from("<I", cb, CONTRACT_WAGE)[0] if cb else None,
            "contract_end": (lambda d: d.isoformat() if d else None)(unpack_date(struct.unpack_from("<I", cb, CONTRACT_END)[0])) if cb else None,
            "value": u32(P_VALUE), "height": u8(P_HEIGHT), "foot": foot,
            "ca": u8(P_CA), "pa": u8(P_PA),
            "personality": list(b[P_BEFORE + P_PERSONALITY: P_BEFORE + P_PERSONALITY + 8]),
            "season": e, "record": rec,
        }

    def read_all(self, scope: str = "competitive", require_minutes=True, progress=None):
        today = self.today()
        out = []
        ps = self.players()
        for i, a in enumerate(ps):
            try:
                r = self.read_player(a, today, scope, require_minutes)
            except (struct.error, TypeError, IndexError):
                r = None
            if r:
                out.append(r)
            if progress and i % 2000 == 0:
                progress(i, len(ps))
        return today, out


if __name__ == "__main__":
    import json
    import sys
    t = time.time()
    g = Game()
    n = len(g.players())
    print(f"build {g.build.id}: {n} players in {time.time() - t:.1f}s")
    t = time.time()
    today, rows = g.read_all(sys.argv[1] if len(sys.argv) > 1 else "competitive")
    print(f"game date {today}; {len(rows)} players with minutes read in {time.time() - t:.1f}s")
    top = sorted(rows, key=lambda r: -(r["wage"] or 0))[:5]
    for r in top:
        print(json.dumps({k: r[k] for k in ("name", "age", "position", "club", "division", "nat", "wage", "value", "contract_end")}, ensure_ascii=False))
