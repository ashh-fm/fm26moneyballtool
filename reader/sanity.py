"""Guards against a game patch silently breaking the reader.

The reader finds players by class name, but the field offsets inside a player are
hard-coded. After a patch they may point at the wrong bytes and still return
plausible-looking numbers. Two guards catch that:

1. KNOWN_BUILDS: the engine builds the offsets were solved and checked on.
2. check_rows(): impossible values (a pass rate above 100%, more shots on target than
   shots, a rating outside 1-10 ...). One odd row can be a quirk of the game's own data,
   so a check only warns when it fires on at least MIN_SHARE of the rows with minutes.

After solving the offsets for a new build, add its id (printed by `python game.py`,
shown in the page banner) to KNOWN_BUILDS.
"""

KNOWN_BUILDS = {"6A229F1E-1D8D3000"}  # FM26 26.3.2

MIN_SHARE = 0.02   # warn when a check fires on >= 2% of rows
MIN_ROWS = 20      # below this many rows the shares are too noisy to judge

PCT_COLUMNS = ["Pas %", "Cr C/A", "OP-Cr %", "Tck R", "Hdr %", "Sv %", "xSv %", "Pens Saved Ratio"]


def _num(v):
    return v if isinstance(v, (int, float)) and v == v else None


def _violations(r: dict) -> list[str]:
    """Names of the checks this one row fails (only for rows that have minutes)."""
    bad = []
    for c in PCT_COLUMNS:
        v = _num(r.get(c))
        if v is not None and not (0 <= v <= 100.0001):
            bad.append("percentage outside 0-100")
            break
    shots, sot = _num(r.get("Shots")), _num(r.get("ShT"))
    if shots is not None and sot is not None and sot > shots:
        bad.append("more shots on target than shots")
    rat = _num(r.get("Av Rat"))
    if rat is not None and not (1 <= rat <= 10):
        bad.append("average rating outside 1-10")
    mins, apps = _num(r.get("Mins")), _num(r.get("Apps"))
    if mins is not None and mins > 8000:
        bad.append("over 8000 minutes in a season")
    if mins is not None and apps and mins > apps * 130:
        bad.append("more than 130 minutes per appearance")
    age = _num(r.get("Age"))
    if age is not None and not (14 <= age <= 60):
        bad.append("age outside 14-60")
    dist = _num(r.get("Dist/90"))
    if dist is not None and not (0 <= dist <= 25):
        bad.append("distance per 90 outside 0-25 km")
    for c, hi in (("NP-xG/90", 3), ("xA/90", 3), ("Shot/90", 20), ("Pres A/90", 80), ("Poss Lost/90", 120)):
        v = _num(r.get(c))
        if v is not None and not (0 <= v <= hi):
            bad.append(f"{c} outside 0-{hi}")
    if r.get("Name") in (None, "", "?"):
        bad.append("player with no readable name")
    return bad


def check_rows(rows: list[dict]) -> list[str]:
    full = [r for r in rows if r.get("Mins")]
    if len(full) < MIN_ROWS:
        return []
    counts: dict[str, int] = {}
    for r in full:
        for name in set(_violations(r)):
            counts[name] = counts.get(name, 0) + 1
    out = []
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n / len(full) >= MIN_SHARE:
            out.append(f"{n} of {len(full)} players show {name}.")
    return out


def check(rows: list[dict], build_id: str) -> list[str]:
    """Warnings to show the user; an empty list means nothing looks wrong."""
    warnings = []
    if build_id not in KNOWN_BUILDS:
        known = ", ".join(sorted(KNOWN_BUILDS))
        warnings.append(
            f"This game build ({build_id}) is not one the reader was checked on ({known}). "
            "The game may have been patched: treat the numbers with caution until the offsets are re-checked.")
    bad = check_rows(rows)
    if bad:
        warnings.extend(bad)
        warnings.append("Impossible values like these usually mean a game patch moved some fields.")
    return warnings
