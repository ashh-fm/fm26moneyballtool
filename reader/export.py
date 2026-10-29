"""Turn reader rows into the column names the Moneyball tool expects (the FM24 FMSS
export headers), so its derive() step works unchanged. Undefined values are None
(the page turns them into NaN, matching how FM printed "-")."""
GK_MIN_RATING = 15  # treat as goalkeeper if GK is an accomplished position


def _per90(v, mins):
    return v * 90 / mins if mins else None


def _pct(a, b):
    return a / b * 100 if b else None


def _ratio(a, b):
    return a / b if b else None


VALUE_UNSET = {0, 300_000_000}  # the game's placeholders when it has no stored valuation


def money(v):
    if v is None or v in VALUE_UNSET:
        return None
    if v >= 1e6:
        return f"£{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"£{v / 1e3:.0f}K"
    return f"£{v:,.0f}"


def identity(r: dict) -> dict:
    """Profile columns only, for players who have no minutes in the chosen scope."""
    return {
        "Name": r["name"], "Position": r["position"], "Nat": r["nat"], "Club": r["club"] or "",
        "Division": r["division"] or "", "Transfer Value": money(r["value"]),
        "Expires": "/".join(reversed(r["contract_end"].split("-"))) if r["contract_end"] else "",
        "Preferred Foot": r["foot"], "Personality": "", "Style": "",
        "UID": r["uid"], "Age": r["age"], "Height": r["height"] or None, "Weight": None,
        "Wage": r["wage"], "CA": r["ca"], "PA": r["pa"], "Apps": 0, "Mins": 0,
    }


def club_ids(r: dict) -> dict:
    """Club ids, plus the parent club of a player who is out on loan."""
    return {"Club ID": r["club_uid"], "Loaned From": r["owner"] or "", "Loaned From ID": r["owner_uid"]}


def to_row(r: dict) -> dict:
    return {**_row(r), **club_ids(r)}


def _row(r: dict) -> dict:
    e, s = r["season"], r["record"]
    if not e or not e["minutes"]:
        return identity(r)
    m = e["minutes"]
    is_gk = r["pos"][0] >= GK_MIN_RATING and max(r["pos"]) == r["pos"][0]
    xg, xa, npxg = s["xg100"] / 100, s["xa100"] / 100, s["npxg100"] / 100
    p90 = lambda v: _per90(v, m)
    apps = e["starts"] + e["subs"]

    row = {
        # identity (TEXT columns in the tool)
        "Name": r["name"], "Position": r["position"], "Nat": r["nat"], "Club": r["club"] or "",
        "Division": r["division"] or "", "Transfer Value": money(r["value"]),
        "Expires": "/".join(reversed(r["contract_end"].split("-"))) if r["contract_end"] else "",
        "Preferred Foot": r["foot"], "Personality": "", "Style": "",
        # numbers
        "UID": r["uid"], "Age": r["age"], "Height": r["height"] or None, "Weight": None,
        "Wage": r["wage"], "CA": r["ca"], "PA": r["pa"],
        "Apps": apps, "Mins": m, "Gls": e["goals"], "Ast": e["assists"],
        "Av Rat": e["rating_sum"] / (10 * e["rated"]) if e["rated"] else None,
        "Pens S": e["pens_scored"], "Pens": e["pens_taken"], "Yel": e["yellow"], "Red": e["red"],
        "PoM": e["motm"], "Mins/Gm": _ratio(m, apps),
        # shooting
        "Shots": s["shots"], "ShT": s["sot"], "Shot/90": p90(s["shots"]), "ShT/90": p90(s["sot"]),
        "Shots Outside Box/90": p90(s["shots_out"]), "Goals Outside Box": s["goals_out"],
        "xG": xg, "NP-xG": npxg, "NP-xG/90": p90(npxg), "xG/shot": _ratio(xg, s["shots"]),
        # creating
        "Drb/90": p90(s["drb"]), "xA": xa, "xA/90": p90(xa), "Asts/90": p90(e["assists"]),
        "K Ps/90": p90(s["kp"]), "OP-KP/90": p90(s["op_kp"]), "CCC": s["ccc"],
        "Ps C/90": p90(s["pas_cmp"]), "Pas %": _pct(s["pas_cmp"], s["pas_att"]),
        "Pr passes/90": p90(s["pr_passes"]),
        "Crs A/90": p90(s["crs_att"]), "Cr C/90": p90(s["crs_cmp"]), "Cr C/A": _pct(s["crs_cmp"], s["crs_att"]),
        "OP-Crs A/90": p90(s["op_crs_att"]), "OP-Crs C/90": p90(s["op_crs_cmp"]),
        "OP-Cr %": _pct(s["op_crs_cmp"], s["op_crs_att"]),
        "Poss Lost/90": p90(s["poss_lost"]), "FA": s["fouls_won"],
        # defending
        "Pres A/90": p90(s["pres_att"]), "Pres C/90": p90(s["pres_cmp"]),
        "Tck/90": p90(s["tck_won"]), "Tck R": _pct(s["tck_won"], s["tck_att"]), "K Tck/90": p90(s["tck_key"]),
        "Int/90": p90(s["int"]), "Clr/90": p90(s["clr"]), "Blk/90": p90(s["blocks"]),
        "Shts Blckd/90": p90(s["shots_blk"]), "Poss Won/90": p90(s["poss_won"]),
        "Hdrs W/90": p90(s["hdr_won"]), "K Hdrs/90": p90(s["hdr_key"]), "Hdr %": _pct(s["hdr_won"], s["hdr_att"]),
        # physical / discipline
        "Dist/90": p90(s["distance10"] / 10), "Sprints/90": p90(s["sprints"]),
        "Fls": s["fouls"], "Off": s["offsides"],
        # goalkeeping (blank for outfielders)
        "Con/90": None, "Cln/90": None, "Saves/90": None, "Sv %": None, "xSv %": None, "xGP/90": None,
        "Pens Saved Ratio": None,
    }
    # only full match data fills these (penalty and team counts appear even without it)
    if not any(s[k] for k in ("pas_att", "distance10", "sprints", "op_crs_cmp", "poss_lost", "xg100")):
        # no detailed record (e.g. imported history with basic stats only): missing, not zero
        basic = {"Name", "Position", "Nat", "Club", "Division", "Transfer Value", "Expires", "Preferred Foot",
                 "Personality", "Style", "UID", "Age", "Height", "Weight", "Wage", "CA", "PA", "Apps", "Mins",
                 "Gls", "Ast", "Av Rat", "Pens S", "Pens", "Yel", "Red", "PoM", "Mins/Gm", "Asts/90"}
        row = {k: (v if k in basic else None) for k, v in row.items()}
        if is_gk:
            row.update({"Con/90": p90(e["conceded"]), "Cln/90": p90(e["clean_sheets"]),
                        "Pens Saved Ratio": _pct(s["tck_won"], s["tck_att"])})
        return row
    if is_gk:
        # keepers reuse outfield slots: +0x34 holds saves, the tackle slots penalties faced/saved
        saves = s["op_crs_cmp"]
        conc, xgp = e["conceded"], s["xgp100"] / 100
        faced = saves + conc
        row.update({
            "Con/90": p90(conc), "Cln/90": p90(e["clean_sheets"]), "Saves/90": p90(saves),
            "Sv %": _pct(saves, faced), "xGP/90": p90(xgp),
            # expected save % = 1 - expected goals on target / shots on target faced
            "xSv %": (1 - (xgp + conc) / faced) * 100 if faced else None,
            "Pens Saved Ratio": _pct(s["tck_won"], s["tck_att"]),
            "OP-Crs C/90": None, "OP-Cr %": None,
            "Hdrs W/90": None, "K Hdrs/90": None, "Hdr %": None, "Tck/90": None, "Tck R": None,
        })
        if not saves and m >= 270:
            # some leagues' imported history has no shot data: unknown, not a 0% save rate
            row.update({"Saves/90": None, "Sv %": None, "xSv %": None, "xGP/90": None})
    return row
