"""
Fantasy Player Report
=====================
Deep, fantasy-focused NFL player reports built from nflverse data.

Setup (Python 3.10+, one time):
    pip install nflreadpy polars reportlab

Run (console):
    python player_report.py                         # type players one after another; each PDF saves and opens
    python player_report.py --name "Matthew Golden"
    python player_report.py --scoring ppr           # standard | half | ppr
    python player_report.py --name "Bijan Robinson" --no-open

Website: this file is also the engine behind app.py (streamlit run app.py).

League data loads once per session, so every player after the first takes about a second.
Downloads are cached on disk for a few hours, so restarting is fast too.

Each player gets a folder next to this script:
    Player Reports/<Player Name>/
        <player>_<season>_report.pdf
        <player>_<season>_weekly.csv     week-by-week fantasy points, finishes, usage
        <player>_<season>_metrics.csv    every metric with league rank and percentile
        <player>_<season>_plays.csv      every play he's involved in

What's inside (QB, RB, WR and TE each get position-specific analysis):
  Fantasy      points, PPG, positional rank, weekly finishes (top 12/24/36), boom/bust rates,
               floor/median/ceiling, consistency, TD dependency
  Expected     expected fantasy points (xFP) from usage, points over expected,
               expected vs actual touchdowns  -> regression (buy-low / sell-high) signals
  Usage        snap share, route participation, target share, air yards share, WOPR,
               targets & yards per route run, red-zone / end-zone / goal-line share,
               rush share, high-value touches, last-3-games trends
  Efficiency   EPA, success rate, catch rate over expected, YAC, drops, explosive runs,
               stuff rate, ANY/A, CPOE, sack/INT rates, scrambles, Next Gen Stats tracking
  Context      league ranks and percentiles at his position, team pace and pass-rate-over-
               expected, next matchup with Vegas implied team total, opponent fantasy points
               allowed rank, rest-of-season and fantasy-playoff schedule strength, injury status
  Splits       depth, direction, down, red zone, play action, screens, blitz, box count, ...
  Edge notes   automatically flagged trends, regression signals and matchup notes
"""

import argparse
import csv
import difflib
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

# ================================ SETTINGS ==========================================
# Edit these to match your league. Command-line flags override the first two.
SEASON = 2026
SCORING_FORMAT = "half"            # "standard", "half" (Yahoo default) or "ppr"
SCORING = {
    "pass_yd": 0.04,               # 1 point per 25 passing yards
    "pass_td": 4,
    "int": -1,
    "rush_yd": 0.1,
    "rush_td": 6,
    "rec": None,                   # None = follow SCORING_FORMAT (0 / 0.5 / 1)
    "rec_yd": 0.1,
    "rec_td": 6,
    "two_pt": 2,
    "fum_lost": -2,
    "st_td": 6,                    # return touchdowns
}
FANTASY_PLAYOFF_WEEKS = (15, 16, 17)
BOOM_BUST = {"QB": (25, 12), "RB": (20, 8), "WR": (20, 8), "TE": (15, 6)}  # (boom at or above, bust below)
CACHE_HOURS = 6
# ====================================================================================

FORMAT_REC = {"standard": 0.0, "half": 0.5, "ppr": 1.0}
FORMAT_LABEL = {"standard": "Standard scoring", "half": "Half-PPR scoring", "ppr": "PPR scoring"}
FANTASY_POS = ("QB", "RB", "WR", "TE")
STARTER_CUTOFF = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}

ROLE_COLS = [
    ("receiver_player_id", "target"),
    ("rusher_player_id", "rush"),
    ("passer_player_id", "pass"),
    ("kickoff_returner_player_id", "kick return"),
    ("punt_returner_player_id", "punt return"),
    ("lateral_receiver_player_id", "lateral"),
    ("fumbled_1_player_id", "fumble"),
    ("penalty_player_id", "penalty"),
    ("solo_tackle_1_player_id", "tackle"),
    ("assist_tackle_1_player_id", "tackle"),
    ("fumble_recovery_1_player_id", "fumble recovery"),
]

PBP_COLS = [
    "game_id", "play_id", "week", "season_type", "posteam", "defteam", "qtr", "time", "down",
    "ydstogo", "yrdln", "yardline_100", "play_type", "desc", "yards_gained", "air_yards",
    "yards_after_catch", "complete_pass", "interception", "touchdown", "pass_touchdown",
    "rush_touchdown", "epa", "success", "first_down_pass", "first_down_rush", "cp", "cpoe",
    "pass_location", "run_location", "run_gap", "two_point_attempt", "two_point_conv_result",
    "fumble_lost", "return_yards", "receiver_player_name", "rusher_player_name",
    "passer_player_name", "qb_dropback", "qb_scramble", "sack", "pass_attempt", "pass",
    "rush", "xpass", "wp", "score_differential", "half_seconds_remaining", "shotgun",
    "no_huddle", "goal_to_go",
] + [c for c, _ in ROLE_COLS]

FTN_FLAGS = [
    "is_drop", "is_catchable_ball", "is_contested_ball", "is_created_reception",
    "is_play_action", "is_screen_pass", "is_rpo", "is_motion", "is_qb_out_of_pocket",
    "is_throw_away", "is_interception_worthy", "n_blitzers", "n_pass_rushers", "n_defense_box",
]


# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------

def g(r, k, default=None):
    if not r:
        return default
    v = r.get(k)
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return default
    return v


def num(r, *keys):
    for k in keys:
        v = g(r, k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return 0.0


def first(r, *keys):
    for k in keys:
        v = g(r, k)
        if v not in (None, ""):
            return v
    return None


def ftn(r, k):
    f = r.get("_ftn")
    return None if not f else f.get(k)


def div(a, b):
    return a / b if (a is not None and b) else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def quantile(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def norm_pos(p):
    if not p:
        return None
    p = str(p).upper()
    return "RB" if p in ("FB", "HB") else p


def fmt(v, kind):
    if v is None:
        return "–"
    try:
        if kind == "int":
            return f"{int(round(v))}"
        if kind == "pct":
            return f"{v * 100:.0f}%"
        if kind == "pct1":
            return f"{v * 100:.1f}%"
        if kind == "pct1s":
            return f"{v * 100:+.1f}%"
        if kind == "pct100":
            return f"{v:.0f}%"
        if kind == "dec1":
            return f"{v:.1f}"
        if kind == "dec1s":
            return f"{v:+.1f}"
        if kind == "dec2":
            return f"{v:.2f}"
        if kind == "dec2s":
            return f"{v:+.2f}"
    except (TypeError, ValueError):
        return "–"
    return str(v)


def fantasy_points(r, sc):
    return (sc["pass_yd"] * r["pass_yds"] + sc["pass_td"] * r["pass_td"] + sc["int"] * r["ints"]
            + sc["rush_yd"] * r["rush_yds"] + sc["rush_td"] * r["rush_td"]
            + sc["rec"] * r["rec"] + sc["rec_yd"] * r["rec_yds"] + sc["rec_td"] * r["rec_td"]
            + sc["two_pt"] * r["two_pt"] + sc["fum_lost"] * r["fum_lost"] + sc["st_td"] * r["st_td"])


def opp_label(game_id, team):
    parts = (game_id or "").split("_")
    if len(parts) < 4:
        return game_id or ""
    away, home = parts[2], parts[3]
    return f"@ {home}" if team == away else f"vs {away}"


def configure_cache():
    """Cache nflverse downloads on disk so restarts are fast. Harmless if unsupported."""
    try:
        from nflreadpy.config import update_config
        update_config(cache_mode="filesystem", cache_duration=int(CACHE_HOURS * 3600))
    except Exception:
        pass


# ------------------------------------------------------------------------------------
# Season data: loaded once per session
# ------------------------------------------------------------------------------------

class Season:
    def __init__(self, season, scoring, fmt_name):
        self.season = season
        self.scoring = scoring
        self.fmt_name = fmt_name
        self.notes = []
        self.players = {}
        self.pbp = []
        self.ftn = {}
        self.weekly_raw = []
        self.snaps = {}
        self.routes = {}
        self.team_db = {}
        self.ngs = {}
        self.ngs_pool = {}
        self.xfp = {}
        self.xfp_basis = None
        self.schedule = []
        self.injuries = {}
        self._pool = {}


def load_season(S):
    import nflreadpy as nfl
    import polars as pl

    configure_cache()
    print(f"\nLoading {S.season} league data (first run of the day takes longest)...")

    def step(label, fn, required=False):
        t0 = time.time()
        print(f"  {label:<34}", end="", flush=True)
        try:
            out = fn()
            print(f"done ({time.time() - t0:.1f}s)")
            return out
        except Exception as e:
            print("not available")
            if required:
                raise
            S.notes.append(f"{label}: not available yet ({type(e).__name__}).")
            return None

    def _players():
        for r in nfl.load_players().to_dicts():
            pid = r.get("gsis_id")
            if not pid:
                continue
            S.players[pid] = {
                "pid": pid, "name": first(r, "display_name", "full_name") or pid,
                "pos": norm_pos(first(r, "position", "position_group")), "team": first(r, "latest_team", "team_abbr"),
                "jersey": g(r, "jersey_number"), "birth_date": g(r, "birth_date"), "height": g(r, "height"),
                "weight": g(r, "weight"), "college": first(r, "college_name", "college"),
                "rookie_season": g(r, "rookie_season"), "draft_round": g(r, "draft_round"),
                "draft_pick": g(r, "draft_pick"), "exp": first(r, "years_of_experience", "years_exp"),
                "pfr_id": g(r, "pfr_id"),
            }

    def _pbp():
        df = nfl.load_pbp(S.season)
        if "season_type" in df.columns:
            df = df.filter(pl.col("season_type") == "REG")
        df = df.select([c for c in PBP_COLS if c in df.columns]).with_columns(pl.col("play_id").cast(pl.Int64))
        S.pbp = df.to_dicts()
        if not S.pbp:
            raise ValueError("no plays")
        return df

    def _weekly():
        df = nfl.load_player_stats(S.season, summary_level="week")
        if "season_type" in df.columns:
            df = df.filter(pl.col("season_type") == "REG")
        for r in df.to_dicts():
            S.weekly_raw.append({
                "pid": r.get("player_id"), "name": first(r, "player_display_name", "player_name"),
                "pos": norm_pos(first(r, "position", "position_group")),
                "team": first(r, "team", "recent_team"), "opp": first(r, "opponent_team", "opponent"),
                "week": r.get("week"),
                "attempts": num(r, "attempts"), "completions": num(r, "completions"),
                "pass_yds": num(r, "passing_yards"), "pass_td": num(r, "passing_tds"),
                "ints": num(r, "passing_interceptions", "interceptions"),
                "sacks": num(r, "sacks_suffered", "sacks"),
                "carries": num(r, "carries"), "rush_yds": num(r, "rushing_yards"), "rush_td": num(r, "rushing_tds"),
                "targets": num(r, "targets"), "rec": num(r, "receptions"), "rec_yds": num(r, "receiving_yards"),
                "rec_td": num(r, "receiving_tds"),
                "two_pt": num(r, "passing_2pt_conversions") + num(r, "rushing_2pt_conversions")
                + num(r, "receiving_2pt_conversions"),
                "fum_lost": num(r, "sack_fumbles_lost") + num(r, "rushing_fumbles_lost")
                + num(r, "receiving_fumbles_lost"),
                "st_td": num(r, "special_teams_tds"),
            })
        if not S.weekly_raw:
            raise ValueError("no rows")

    def _snaps():
        df = nfl.load_snap_counts(S.season)
        if "game_type" in df.columns:
            df = df.filter(pl.col("game_type") == "REG")
        pfr = {p["pfr_id"]: pid for pid, p in S.players.items() if p.get("pfr_id")}
        byname = defaultdict(list)
        for pid, p in S.players.items():
            byname[(p["name"] or "").lower()].append(pid)
        for r in df.to_dicts():
            pid = pfr.get(r.get("pfr_player_id"))
            if not pid:
                cands = byname.get((r.get("player") or "").lower(), [])
                cands = [c for c in cands if S.players[c].get("team") == r.get("team")] or cands
                pid = cands[0] if len(cands) == 1 else None
            if not pid:
                continue
            pct = g(r, "offense_pct")
            if pct is not None and pct <= 1.0:
                pct *= 100
            S.snaps[(pid, r.get("week"))] = (g(r, "offense_snaps"), pct)
        if not S.snaps:
            raise ValueError("no rows")

    def _participation(pbp_df):
        part = nfl.load_participation(S.season)
        gcol = "nflverse_game_id" if "nflverse_game_id" in part.columns else "game_id"
        p = part.select(pl.col(gcol).alias("game_id"), pl.col("play_id").cast(pl.Int64), pl.col("offense_players"))
        db = pbp_df.filter(pl.col("qb_dropback") == 1).select("game_id", "play_id", "posteam", "week")
        j = db.join(p, on=["game_id", "play_id"], how="inner")
        for r in j.group_by(["posteam", "week"]).agg(pl.len().alias("n")).to_dicts():
            S.team_db[(r["posteam"], r["week"])] = r["n"]
        ex = j.with_columns(pl.col("offense_players").str.split(";")).explode("offense_players")
        for r in ex.group_by(["offense_players", "week"]).agg(pl.len().alias("n")).to_dicts():
            if r["offense_players"]:
                S.routes[(r["offense_players"].strip(), r["week"])] = r["n"]
        if not S.routes:
            raise ValueError("no rows")

    def _ftn():
        df = nfl.load_ftn_charting(S.season)
        gcol = next((c for c in ["nflverse_game_id", "game_id"] if c in df.columns), None)
        pcol = next((c for c in ["nflverse_play_id", "play_id"] if c in df.columns), None)
        flags = [c for c in FTN_FLAGS if c in df.columns]
        if not gcol or not pcol or not flags:
            raise ValueError("unexpected format")
        df = df.select(pl.col(gcol).alias("_g"), pl.col(pcol).cast(pl.Int64).alias("_p"), *flags)
        for r in df.to_dicts():
            S.ftn[(r["_g"], r["_p"])] = {k: r[k] for k in flags}

    def _ngs(st):
        rows = nfl.load_nextgen_stats(seasons=S.season, stat_type=st).to_dicts()
        rows = [r for r in rows if g(r, "season_type", "REG") == "REG"]
        season_rows = [r for r in rows if g(r, "week") == 0]
        if not season_rows:  # fall back to averaging weekly rows
            acc = defaultdict(list)
            for r in rows:
                acc[r.get("player_gsis_id")].append(r)
            for pid, rs in acc.items():
                avg = dict(rs[-1])
                for k, v in rs[-1].items():
                    if isinstance(v, (int, float)) and k not in ("season", "week"):
                        avg[k] = mean([g(x, k) for x in rs])
                season_rows.append(avg)
        S.ngs_pool[st] = season_rows
        S.ngs[st] = {r.get("player_gsis_id"): r for r in season_rows if r.get("player_gsis_id")}
        if not season_rows:
            raise ValueError("no rows")

    def _xfp():
        try:
            df = nfl.load_ff_opportunity(seasons=S.season, stat_type="weekly", model_version="latest")
        except TypeError:
            df = nfl.load_ff_opportunity(S.season)
        sc = S.scoring
        comp = ["receptions_exp", "rec_yards_gained_exp", "rec_touchdown_exp", "rush_yards_gained_exp",
                "rush_touchdown_exp", "pass_yards_gained_exp", "pass_touchdown_exp", "pass_interception_exp"]
        has_comp = all(k in df.columns for k in comp)
        S.xfp_basis = "your scoring" if has_comp else "full PPR (nflverse default)"
        for r in df.to_dicts():
            if g(r, "season_type", "REG") != "REG":
                continue
            pid, wk = r.get("player_id"), r.get("week")
            if not pid or wk is None:
                continue
            wk = int(wk)
            if has_comp:
                x = (sc["rec"] * num(r, "receptions_exp") + sc["rec_yd"] * num(r, "rec_yards_gained_exp")
                     + sc["rec_td"] * num(r, "rec_touchdown_exp") + sc["rush_yd"] * num(r, "rush_yards_gained_exp")
                     + sc["rush_td"] * num(r, "rush_touchdown_exp") + sc["pass_yd"] * num(r, "pass_yards_gained_exp")
                     + sc["pass_td"] * num(r, "pass_touchdown_exp") + sc["int"] * num(r, "pass_interception_exp")
                     + sc["two_pt"] * (num(r, "rec_two_point_conv_exp") + num(r, "rush_two_point_conv_exp")
                                       + num(r, "pass_two_point_conv_exp")))
            else:
                x = g(r, "total_fantasy_points_exp")
            if x is None:
                continue
            S.xfp[(pid, wk)] = {"xfp": x, "exp_rec_td": num(r, "rec_touchdown_exp"),
                                "exp_rush_td": num(r, "rush_touchdown_exp"),
                                "exp_pass_td": num(r, "pass_touchdown_exp")}
        if not S.xfp:
            raise ValueError("no rows")

    def _schedule():
        for r in nfl.load_schedules(S.season).to_dicts():
            if g(r, "game_type", "REG") != "REG":
                continue
            S.schedule.append({
                "game_id": r.get("game_id"), "week": r.get("week"), "gameday": g(r, "gameday"),
                "gametime": g(r, "gametime"), "home": r.get("home_team"), "away": r.get("away_team"),
                "home_score": g(r, "home_score"), "away_score": g(r, "away_score"),
                "spread": g(r, "spread_line"), "total": g(r, "total_line"),
            })
        if not S.schedule:
            raise ValueError("no rows")

    def _injuries():
        for r in nfl.load_injuries(S.season).to_dicts():
            pid, wk = r.get("gsis_id"), g(r, "week", 0)
            if g(r, "game_type", "REG") != "REG" or not pid:
                continue
            if pid not in S.injuries or wk >= S.injuries[pid]["week"]:
                S.injuries[pid] = {"week": wk, "status": g(r, "report_status"),
                                   "injury": g(r, "report_primary_injury"), "practice": g(r, "practice_status")}

    step("Players", _players, required=True)
    pbp_df = step("Play-by-play", _pbp, required=True)
    step("Weekly fantasy stats", _weekly, required=True)
    step("Snap counts", _snaps)
    step("Routes (participation)", lambda: _participation(pbp_df))
    step("FTN charting (drops, PA, blitz)", _ftn)
    for st in ("receiving", "rushing", "passing"):
        step(f"Next Gen Stats ({st})", lambda st=st: _ngs(st))
    step("Expected fantasy points", _xfp)
    step("Schedule & Vegas lines", _schedule)
    step("Injury reports", _injuries)
    del pbp_df
    t0 = time.time()
    print(f"  {'Crunching league numbers':<34}", end="", flush=True)
    prepare(S)
    print(f"done ({time.time() - t0:.1f}s)")


# ------------------------------------------------------------------------------------
# League-wide precompute (pure Python from here on)
# ------------------------------------------------------------------------------------

def prepare(S):
    sc = S.scoring
    for r in S.pbp:
        r["_ftn"] = S.ftn.get((r.get("game_id"), r.get("play_id")))
    S.snap_weeks = defaultdict(set)
    for (pid, wk), v in S.snaps.items():
        if (v[0] or 0) > 0:
            S.snap_weeks[pid].add(wk)

    # Weekly fantasy points and weekly positional finishes
    S.weekly = defaultdict(list)
    for r in S.weekly_raw:
        if r["pos"] not in FANTASY_POS or not r["pid"] or r["week"] is None:
            continue
        r["pts"] = fantasy_points(r, sc)
        S.weekly[r["pid"]].append(r)
    for rows in S.weekly.values():
        rows.sort(key=lambda r: r["week"])
    by_wp = defaultdict(list)
    for rows in S.weekly.values():
        for r in rows:
            by_wp[(r["week"], r["pos"])].append(r)
    for rows in by_wp.values():
        rows.sort(key=lambda r: -r["pts"])
        for i, r in enumerate(rows, 1):
            r["rank"] = i
    S.weeks_played = sorted({r["week"] for rows in S.weekly.values() for r in rows})
    S.last_week = S.weeks_played[-1] if S.weeks_played else 0
    S.min_games = max(2, math.ceil(0.4 * len(S.weeks_played)))

    # Season totals and positional ranks
    S.season_tot = {}
    for pid, rows in S.weekly.items():
        pts = [r["pts"] for r in rows]
        S.season_tot[pid] = {"pos": rows[-1]["pos"], "team": rows[-1]["team"], "name": rows[-1]["name"],
                             "games": len(rows), "pts": sum(pts), "ppg": sum(pts) / len(rows)}
    S.pos_counts = {}
    for pos in FANTASY_POS:
        pool = [(pid, t) for pid, t in S.season_tot.items() if t["pos"] == pos]
        for i, (_, t) in enumerate(sorted(pool, key=lambda x: -x[1]["pts"]), 1):
            t["rank_total"] = i
        q = [x for x in pool if x[1]["games"] >= S.min_games]
        for i, (_, t) in enumerate(sorted(q, key=lambda x: -x[1]["ppg"]), 1):
            t["rank_ppg"] = i
        S.pos_counts[pos] = (len(pool), len(q))

    # Fantasy points allowed by each defense to each position (rank 1 = most allowed = best matchup)
    acc = defaultdict(lambda: defaultdict(float))
    for rows in S.weekly.values():
        for r in rows:
            if r.get("opp"):
                acc[(r["opp"], r["pos"])][r["week"]] += r["pts"]
    S.fpa, S.fpa_avg = {}, {}
    for (opp, pos), wk in acc.items():
        S.fpa[(opp, pos)] = {"avg": mean(list(wk.values())), "games": len(wk)}
    for pos in FANTASY_POS:
        items = sorted([(k, v) for k, v in S.fpa.items() if k[1] == pos], key=lambda kv: -kv[1]["avg"])
        for i, (_, v) in enumerate(items, 1):
            v["rank"], v["n"] = i, len(items)
        S.fpa_avg[pos] = mean([v["avg"] for _, v in items])

    # Team-week totals and per-player play lists from play-by-play
    S.team_week = defaultdict(Counter)
    S.tgt_rows, S.rush_rows, S.db_rows = defaultdict(list), defaultdict(list), defaultdict(list)
    S.tgt_pw, S.rush_pw, S.db_pw = defaultdict(list), defaultdict(list), defaultdict(list)
    S.play_team = defaultdict(Counter)
    for r in S.pbp:
        team, wk = g(r, "posteam"), g(r, "week")
        if not team or wk is None or g(r, "two_point_attempt", 0):
            continue
        c = S.team_week[(team, wk)]
        pt = g(r, "play_type")
        y100 = g(r, "yardline_100")
        if pt in ("pass", "run"):
            c["plays"] += 1
        rec = g(r, "receiver_player_id")
        if pt == "pass" and rec:
            air = g(r, "air_yards")
            c["targets"] += 1
            c["air"] += air or 0
            if y100 is not None and y100 <= 20:
                c["rz_tgt"] += 1
            if air is not None and y100 is not None and air >= y100:
                c["ez_tgt"] += 1
            S.tgt_rows[rec].append(r)
            S.tgt_pw[(rec, wk)].append(r)
            S.play_team[(rec, wk)][team] += 1
        rus = g(r, "rusher_player_id")
        if pt == "run" and rus:
            c["carries"] += 1
            if y100 is not None:
                c["rz_car"] += y100 <= 20
                c["i10_car"] += y100 <= 10
                c["i5_car"] += y100 <= 5
            S.rush_rows[rus].append(r)
            S.rush_pw[(rus, wk)].append(r)
            S.play_team[(rus, wk)][team] += 1
        if g(r, "qb_dropback", 0) == 1:
            c["dropbacks"] += 1
            qb = g(r, "passer_player_id") or (rus if g(r, "qb_scramble", 0) == 1 else None)
            if qb:
                S.db_rows[qb].append(r)
                S.db_pw[(qb, wk)].append(r)
                S.play_team[(qb, wk)][team] += 1
        if pt in ("pass", "run") and g(r, "xpass") is not None:
            wp = g(r, "wp")
            if (wp is not None and 0.2 <= wp <= 0.8 and g(r, "down") in (1, 2)
                    and g(r, "half_seconds_remaining", 999) > 120):
                c["neu_n"] += 1
                c["neu_pass"] += g(r, "pass", 1 if pt == "pass" else 0) or 0
                c["neu_xpass"] += g(r, "xpass")

    # Team context
    S.team_ctx = {}
    teams = {t for t, _ in S.team_week}
    pf, pa = defaultdict(list), defaultdict(list)
    for gm in S.schedule:
        if gm["home_score"] is None:
            continue
        pf[gm["home"]].append(gm["home_score"]); pa[gm["home"]].append(gm["away_score"])
        pf[gm["away"]].append(gm["away_score"]); pa[gm["away"]].append(gm["home_score"])
    for t in teams:
        ws = [c for (tt, _), c in S.team_week.items() if tt == t]
        tot = sum(ws, Counter())
        n = len(ws)
        S.team_ctx[t] = {
            "games": n, "plays_pg": div(tot["plays"], n), "dropbacks_pg": div(tot["dropbacks"], n),
            "pass_rate": div(tot["dropbacks"], tot["plays"]),
            "proe": div(tot["neu_pass"] - tot["neu_xpass"], tot["neu_n"]) if tot["neu_n"] else None,
            "ppg": mean(pf.get(t, [])), "papg": mean(pa.get(t, [])),
            "rz_plays_pg": div(tot["rz_tgt"] + tot["rz_car"], n),
        }
    for key in ("plays_pg", "proe", "ppg", "pass_rate", "rz_plays_pg"):
        vals = sorted([(t, c[key]) for t, c in S.team_ctx.items() if c[key] is not None], key=lambda x: -x[1])
        for i, (t, _) in enumerate(vals, 1):
            S.team_ctx[t][key + "_rank"] = i
    S.n_teams = len(S.team_ctx)


def team_of(S, pid, wk):
    for r in S.weekly.get(pid, []):
        if r["week"] == wk and r.get("team"):
            return r["team"]
    c = S.play_team.get((pid, wk))
    if c:
        return c.most_common(1)[0][0]
    return None


def player_team(S, pid):
    rows = S.weekly.get(pid)
    if rows:
        return rows[-1]["team"]
    return (S.players.get(pid) or {}).get("team")


def player_weeks(S, pid):
    w = {r["week"] for r in S.weekly.get(pid, [])}
    w |= S.snap_weeks.get(pid, set())
    return sorted(w)


# ------------------------------------------------------------------------------------
# Stat blocks
# ------------------------------------------------------------------------------------

def recv_stats(tg):
    n = len(tg)
    rec = [r for r in tg if num(r, "complete_pass") == 1]
    air = [g(r, "air_yards") for r in tg if g(r, "air_yards") is not None]
    yds = sum(num(r, "yards_gained") for r in rec)
    yac = sum(num(r, "yards_after_catch") for r in rec)
    charted = [r for r in tg if ftn(r, "is_drop") is not None]
    drops = sum(1 for r in charted if ftn(r, "is_drop"))
    catchable = sum(1 for r in charted if ftn(r, "is_catchable_ball"))
    contested = [r for r in charted if ftn(r, "is_contested_ball")]
    cps = [g(r, "cp") for r in tg if g(r, "cp") is not None]
    cr = div(len(rec), n)
    return {
        "targets": n, "rec": len(rec), "rec_yds": yds,
        "td": sum(1 for r in rec if num(r, "pass_touchdown", "touchdown") == 1),
        "long": int(max(num(r, "yards_gained") for r in rec)) if rec else None,
        "air_yds": sum(air), "yac": yac, "first_downs": sum(1 for r in tg if num(r, "first_down_pass") == 1),
        "ints": sum(1 for r in tg if num(r, "interception") == 1),
        "deep_tgt": sum(1 for a in air if a >= 20),
        "deep_rec": sum(1 for r in rec if num(r, "air_yards") >= 20),
        "rz_tgt": sum(1 for r in tg if g(r, "yardline_100", 99) <= 20),
        "ez_tgt": sum(1 for r in tg if g(r, "air_yards") is not None and g(r, "yardline_100") is not None
                      and g(r, "air_yards") >= g(r, "yardline_100")),
        "charted": len(charted), "drops": drops, "catchable": catchable,
        "contested_tgt": len(contested),
        "contested_rec": sum(1 for r in contested if num(r, "complete_pass") == 1),
        "catch_rate": cr, "yds_per_tgt": div(yds, n), "yds_per_rec": div(yds, len(rec)),
        "adot": div(sum(air), len(air)), "yac_per_rec": div(yac, len(rec)),
        "epa_per_tgt": mean([g(r, "epa") for r in tg]), "success_rate": mean([g(r, "success") for r in tg]),
        "first_down_rate": div(sum(1 for r in tg if num(r, "first_down_pass") == 1), n),
        "cr_oe": (cr - mean(cps)) if (cr is not None and cps) else None,
        "racr": div(yds, sum(air)) if sum(air) > 0 else None,
        "drop_rate": div(drops, catchable) if charted else None,
        "contested_rate": div(sum(1 for r in contested if num(r, "complete_pass") == 1), len(contested)),
    }


def rush_stats(rows):
    n = len(rows)
    yds = [num(r, "yards_gained") for r in rows]
    return {
        "att": n, "yds": sum(yds), "td": sum(1 for r in rows if num(r, "rush_touchdown") == 1),
        "ypc": div(sum(yds), n), "epa_per": mean([g(r, "epa") for r in rows]),
        "success_rate": mean([g(r, "success") for r in rows]),
        "expl_rate": div(sum(1 for y in yds if y >= 10), n), "expl20": sum(1 for y in yds if y >= 20),
        "stuff_rate": div(sum(1 for y in yds if y <= 0), n),
        "first_downs": sum(1 for r in rows if num(r, "first_down_rush") == 1),
        "long": int(max(yds)) if yds else None,
        "rz_att": sum(1 for r in rows if g(r, "yardline_100", 99) <= 20),
        "i10_att": sum(1 for r in rows if g(r, "yardline_100", 99) <= 10),
        "i5_att": sum(1 for r in rows if g(r, "yardline_100", 99) <= 5),
        "scrambles": sum(1 for r in rows if num(r, "qb_scramble") == 1),
    }


def pass_stats(rows, pid):
    att = [r for r in rows if g(r, "passer_player_id") == pid and num(r, "sack") == 0
           and num(r, "qb_scramble") == 0 and g(r, "play_type") == "pass"]
    cmp_ = [r for r in att if num(r, "complete_pass") == 1]
    yds = sum(num(r, "yards_gained") for r in cmp_)
    td = sum(1 for r in att if num(r, "pass_touchdown") == 1)
    ints = sum(1 for r in att if num(r, "interception") == 1)
    sacks = [r for r in rows if num(r, "sack") == 1]
    sack_yds = -sum(num(r, "yards_gained") for r in sacks)
    scr = [r for r in rows if num(r, "qb_scramble") == 1]
    air = [g(r, "air_yards") for r in att if g(r, "air_yards") is not None]
    charted = [r for r in att if r.get("_ftn")]
    return {
        "dropbacks": len(rows), "att": len(att), "cmp": len(cmp_), "yds": yds, "td": td, "ints": ints,
        "sacks": len(sacks), "scrambles": len(scr), "scramble_yds": sum(num(r, "yards_gained") for r in scr),
        "cmp_pct": div(len(cmp_), len(att)), "ypa": div(yds, len(att)),
        "any_a": div(yds + 20 * td - 45 * ints - sack_yds, len(att) + len(sacks)),
        "epa_per_db": mean([g(r, "epa") for r in rows]), "success_rate": mean([g(r, "success") for r in rows]),
        "cpoe": mean([g(r, "cpoe") for r in att]), "adot": div(sum(air), len(air)),
        "deep_rate": div(sum(1 for a in air if a >= 20), len(air)),
        "td_rate": div(td, len(att)), "int_rate": div(ints, len(att)),
        "sack_rate": div(len(sacks), len(att) + len(sacks)),
        "throwaways": sum(1 for r in charted if ftn(r, "is_throw_away")),
        "int_worthy": sum(1 for r in charted if ftn(r, "is_interception_worthy")),
        "pa_rate": div(sum(1 for r in charted if ftn(r, "is_play_action")), len(charted)),
    }


def usage_week(S, pid, wk):
    team = team_of(S, pid, wk)
    c = S.team_week.get((team, wk), Counter())
    tg, ru = S.tgt_pw.get((pid, wk), []), S.rush_pw.get((pid, wk), [])
    sn = S.snaps.get((pid, wk))
    routes, tdb = S.routes.get((pid, wk)), S.team_db.get((team, wk))
    rec_yds = sum(num(r, "yards_gained") for r in tg if num(r, "complete_pass") == 1)

    def y(r):
        return g(r, "yardline_100", 99)
    u = {
        "week": wk, "team": team, "snaps": sn[0] if sn else None, "snap_pct": sn[1] if sn else None,
        "targets": len(tg), "team_targets": c["targets"],
        "air": sum(num(r, "air_yards") for r in tg), "team_air": c["air"],
        "rz_tgt": sum(1 for r in tg if y(r) <= 20), "team_rz_tgt": c["rz_tgt"],
        "ez_tgt": sum(1 for r in tg if g(r, "air_yards") is not None and g(r, "air_yards") >= y(r)),
        "carries": len(ru), "team_carries": c["carries"],
        "rz_car": sum(1 for r in ru if y(r) <= 20), "team_rz_car": c["rz_car"],
        "i10_car": sum(1 for r in ru if y(r) <= 10), "team_i10_car": c["i10_car"],
        "rec_yds": rec_yds, "routes": routes or 0, "team_db": (tdb or 0) if routes else 0,
        "route_tgts": len(tg) if routes else 0, "route_yds": rec_yds if routes else 0,
        "dropbacks": len(S.db_pw.get((pid, wk), [])),
    }
    u["hvt"] = u["targets"] + u["i10_car"]
    u["tgt_share"] = div(u["targets"], u["team_targets"])
    u["air_share"] = div(u["air"], u["team_air"]) if u["team_air"] > 0 else None
    u["rush_share"] = div(u["carries"], u["team_carries"])
    u["route_pct"] = div(routes, tdb) if routes and tdb else None
    u["rz_share"] = div(u["rz_tgt"] + u["rz_car"], u["team_rz_tgt"] + u["team_rz_car"])
    xf = S.xfp.get((pid, wk))
    u["xfp"] = xf["xfp"] if xf else None
    return u


def player_metrics(S, pid, pos, weeks=None):
    sc = S.scoring
    weeks = weeks if weeks is not None else player_weeks(S, pid)
    wk_rows = {r["week"]: r for r in S.weekly.get(pid, [])}
    n = len(weeks)
    pts = [wk_rows[w]["pts"] if w in wk_rows else 0.0 for w in weeks]
    m = {"games": n, "pts": sum(pts), "ppg": mean(pts)}
    pairs = [(wk_rows[w]["pts"], S.xfp[(pid, w)]["xfp"]) for w in weeks if w in wk_rows and (pid, w) in S.xfp]
    m["xfp_pg"] = mean([x for _, x in pairs])
    m["fpoe_pg"] = mean([p - x for p, x in pairs])
    m["xfp_games"] = len(pairs)

    U = [usage_week(S, pid, w) for w in weeks]
    s = Counter()
    for u in U:
        for k in ("targets", "team_targets", "air", "team_air", "rz_tgt", "team_rz_tgt", "ez_tgt", "carries",
                  "team_carries", "rz_car", "team_rz_car", "i10_car", "team_i10_car", "hvt", "routes",
                  "team_db", "route_tgts", "route_yds"):
            s[k] += u.get(k) or 0
    m["snap_pct"] = mean([u["snap_pct"] for u in U])
    m["route_pct"] = div(s["routes"], s["team_db"]) if s["team_db"] else None
    m["tprr"] = div(s["route_tgts"], s["routes"]) if s["routes"] else None
    m["yprr"] = div(s["route_yds"], s["routes"]) if s["routes"] else None
    m["tgt_share"] = div(s["targets"], s["team_targets"])
    m["air_share"] = div(s["air"], s["team_air"]) if s["team_air"] > 0 else None
    m["wopr"] = (1.5 * m["tgt_share"] + 0.7 * m["air_share"]
                 if m["tgt_share"] is not None and m["air_share"] is not None else None)
    m["rz_tgt_share"] = div(s["rz_tgt"], s["team_rz_tgt"])
    m["ez_tgt"] = s["ez_tgt"]
    m["rush_share"] = div(s["carries"], s["team_carries"])
    m["rz_car_share"] = div(s["rz_car"], s["team_rz_car"])
    m["i10_share"] = div(s["i10_car"], s["team_i10_car"])
    m["rz_opp_share"] = div(s["rz_tgt"] + s["rz_car"], s["team_rz_tgt"] + s["team_rz_car"])
    m["targets_pg"] = div(s["targets"], n)
    m["carries_pg"] = div(s["carries"], n)
    m["hvt_pg"] = div(s["hvt"], n)
    m["opp_pg"] = div(s["targets"] + s["carries"], n)

    m.update({"r_" + k: v for k, v in recv_stats([r for r in S.tgt_rows.get(pid, []) if r["week"] in weeks]).items()})
    m.update({"ru_" + k: v for k, v in rush_stats([r for r in S.rush_rows.get(pid, []) if r["week"] in weeks]).items()})
    if pos == "QB":
        m.update({"p_" + k: v for k, v in pass_stats([r for r in S.db_rows.get(pid, []) if r["week"] in weeks],
                                                      pid).items()})
        m["p_dropbacks_pg"] = div(m["p_dropbacks"], n)
        m["p_scrambles_pg"] = div(m["p_scrambles"], n)
        m["designed_rush_pg"] = div(m["ru_att"] - m["ru_scrambles"], n)
    m["rush_ypg"] = div(m["ru_yds"], n)
    m["rec_ypg"] = div(m["r_rec_yds"], n)

    rows = [wk_rows[w] for w in weeks if w in wk_rows]
    rush_pts = sum(sc["rush_yd"] * r["rush_yds"] + sc["rush_td"] * r["rush_td"] for r in rows)
    td_pts = sum(sc["rec_td"] * r["rec_td"] + sc["rush_td"] * r["rush_td"] + sc["pass_td"] * r["pass_td"]
                 for r in rows)
    rec_pts = sum(sc["rec"] * r["rec"] for r in rows)
    m["rush_pts_share"] = div(rush_pts, m["pts"]) if m["pts"] > 0 else None
    m["td_pts_share"] = div(td_pts, m["pts"]) if m["pts"] > 0 else None
    m["rec_pts_share"] = div(rec_pts, m["pts"]) if m["pts"] > 0 else None

    exp = [S.xfp[(pid, w)] for w in weeks if (pid, w) in S.xfp]
    m["exp_td"] = sum(e["exp_rec_td"] + e["exp_rush_td"] for e in exp) if exp else None
    m["exp_pass_td"] = sum(e["exp_pass_td"] for e in exp) if exp else None
    exp_weeks = {w for w in weeks if (pid, w) in S.xfp}
    m["act_td_xweeks"] = sum(wk_rows[w]["rec_td"] + wk_rows[w]["rush_td"] for w in exp_weeks if w in wk_rows)
    m["act_pass_td_xweeks"] = sum(wk_rows[w]["pass_td"] for w in exp_weeks if w in wk_rows)
    return m


# ------------------------------------------------------------------------------------
# League ranks
# ------------------------------------------------------------------------------------

# (key, label, format, higher_is_better; None = context only, no good/bad colour)
RANK_METRICS = {
    "WR": [
        ("ppg", "Fantasy points per game", "dec1", True),
        ("xfp_pg", "Expected fantasy points per game", "dec1", True),
        ("fpoe_pg", "Points over expected per game", "dec1s", True),
        ("snap_pct", "Snap share", "pct100", True),
        ("route_pct", "Route participation", "pct", True),
        ("tgt_share", "Target share", "pct", True),
        ("air_share", "Air yards share", "pct", True),
        ("wopr", "WOPR (weighted opportunity)", "dec2", True),
        ("tprr", "Targets per route run", "pct", True),
        ("yprr", "Yards per route run", "dec2", True),
        ("rz_tgt_share", "Red-zone target share", "pct", True),
        ("ez_tgt", "End-zone targets", "int", True),
        ("r_adot", "Average depth of target", "dec1", None),
        ("r_catch_rate", "Catch rate", "pct", True),
        ("r_cr_oe", "Catch rate over expected", "pct1s", True),
        ("r_yds_per_tgt", "Yards per target", "dec1", True),
        ("r_yac_per_rec", "YAC per reception", "dec1", True),
        ("r_epa_per_tgt", "EPA per target", "dec2s", True),
        ("r_first_down_rate", "First downs per target", "pct", True),
        ("r_racr", "RACR (yards per air yard)", "dec2", True),
        ("r_drop_rate", "Drop rate (of catchable)", "pct", False),
    ],
    "RB": [
        ("ppg", "Fantasy points per game", "dec1", True),
        ("xfp_pg", "Expected fantasy points per game", "dec1", True),
        ("fpoe_pg", "Points over expected per game", "dec1s", True),
        ("snap_pct", "Snap share", "pct100", True),
        ("opp_pg", "Opportunities (carries + targets) per game", "dec1", True),
        ("rush_share", "Team rush share", "pct", True),
        ("rz_car_share", "Red-zone carry share", "pct", True),
        ("i10_share", "Inside-10 carry share", "pct", True),
        ("hvt_pg", "High-value touches per game", "dec1", True),
        ("tgt_share", "Target share", "pct", True),
        ("route_pct", "Route participation", "pct", True),
        ("yprr", "Yards per route run", "dec2", True),
        ("ru_ypc", "Yards per carry", "dec1", True),
        ("ru_epa_per", "EPA per rush", "dec2s", True),
        ("ru_success_rate", "Rush success rate", "pct", True),
        ("ru_expl_rate", "Explosive run rate (10+ yds)", "pct", True),
        ("ru_stuff_rate", "Stuff rate (0 or fewer yds)", "pct", False),
        ("r_yds_per_tgt", "Yards per target", "dec1", True),
    ],
    "QB": [
        ("ppg", "Fantasy points per game", "dec1", True),
        ("xfp_pg", "Expected fantasy points per game", "dec1", True),
        ("fpoe_pg", "Points over expected per game", "dec1s", True),
        ("p_dropbacks_pg", "Dropbacks per game", "dec1", True),
        ("p_epa_per_db", "EPA per dropback", "dec2s", True),
        ("p_success_rate", "Dropback success rate", "pct", True),
        ("p_cpoe", "Completion % over expected", "dec1s", True),
        ("p_any_a", "ANY/A", "dec1", True),
        ("p_ypa", "Yards per attempt", "dec1", True),
        ("p_adot", "Average depth of target", "dec1", None),
        ("p_deep_rate", "Deep attempt rate (20+ air yds)", "pct", None),
        ("p_td_rate", "TD rate", "pct1", True),
        ("p_int_rate", "INT rate", "pct1", False),
        ("p_sack_rate", "Sack rate", "pct1", False),
        ("rush_ypg", "Rushing yards per game", "dec1", True),
        ("designed_rush_pg", "Designed runs per game", "dec1", True),
        ("p_scrambles_pg", "Scrambles per game", "dec1", True),
        ("rush_pts_share", "Share of points from rushing", "pct", None),
    ],
}
RANK_METRICS["TE"] = RANK_METRICS["WR"]

NGS_METRICS = {
    "WR": ("receiving", [
        ("avg_separation", "Separation at catch point (yds)", "dec1", True),
        ("avg_cushion", "Cushion at snap (yds)", "dec1", None),
        ("avg_yac_above_expectation", "YAC above expected per catch", "dec1s", True),
        ("avg_intended_air_yards", "Intended air yards", "dec1", None),
        ("percent_share_of_intended_air_yards", "Share of team intended air yards", "pct100", True),
        ("catch_percentage", "Catch %", "pct100", True),
    ]),
    "RB": ("rushing", [
        ("rush_yards_over_expected_per_att", "Rush yards over expected per carry", "dec2s", True),
        ("rush_pct_over_expected", "Carries beating expected yards", "pct", True),
        ("efficiency", "Efficiency (distance run per yard gained)", "dec2", False),
        ("percent_attempts_gte_eight_defenders", "Carries vs 8+ in the box", "pct100", None),
        ("avg_time_to_los", "Time to line of scrimmage (s)", "dec2", None),
    ]),
    "QB": ("passing", [
        ("completion_percentage_above_expectation", "Completion % above expected", "dec1s", True),
        ("avg_time_to_throw", "Time to throw (s)", "dec2", None),
        ("aggressiveness", "Aggressiveness (tight-window throws %)", "dec1", None),
        ("avg_completed_air_yards", "Completed air yards", "dec1", True),
        ("avg_air_yards_to_sticks", "Air yards past the sticks", "dec1s", None),
    ]),
}
NGS_METRICS["TE"] = NGS_METRICS["WR"]


def position_pool(S, pos):
    if pos in S._pool:
        return S._pool[pos]
    nw = max(1, len(S.weeks_played))
    thr = {"WR": max(10, 2.5 * nw), "TE": max(8, 1.8 * nw), "RB": max(15, 4 * nw), "QB": max(50, 12 * nw)}[pos]
    pool = {}
    for pid, t in S.season_tot.items():
        if t["pos"] != pos or t["games"] < S.min_games:
            continue
        vol = {"WR": len(S.tgt_rows.get(pid, [])), "TE": len(S.tgt_rows.get(pid, [])),
               "RB": len(S.rush_rows.get(pid, [])) + len(S.tgt_rows.get(pid, [])),
               "QB": len(S.db_rows.get(pid, []))}[pos]
        if vol >= thr:
            pool[pid] = player_metrics(S, pid, pos)
    S._pool[pos] = (pool, int(math.ceil(thr)))
    return S._pool[pos]


def rank_list(metrics, mine, pool_vals):
    out = []
    for key, label, kind, higher in metrics:
        v = mine.get(key)
        vals = [p.get(key) for p in pool_vals if p.get(key) is not None]
        row = {"key": key, "label": label, "value": fmt(v, kind), "raw": v, "rank": None, "n": len(vals),
               "pct": None, "higher": higher}
        if v is not None and len(vals) >= 5:
            up = higher is not False
            better = sum(1 for x in vals if (x > v if up else x < v))
            worse = sum(1 for x in vals if (x < v if up else x > v))
            row["rank"] = better + 1
            row["pct"] = 100 * worse / max(1, len(vals) - 1)
        out.append(row)
    return out


def league_ranks(S, pid, pos, mine):
    pool, thr = position_pool(S, pos)
    vals = list(pool.values())
    if pid not in pool:
        vals.append(mine)
    return rank_list(RANK_METRICS[pos], mine, vals), len(vals), thr


def ngs_ranks(S, pid, pos):
    st, metrics = NGS_METRICS[pos]
    me = (S.ngs.get(st) or {}).get(pid)
    if not me:
        return []
    pool = [r for r in S.ngs_pool.get(st, []) if norm_pos(g(r, "player_position")) in (pos, None)]
    if len(pool) < 5:
        pool = S.ngs_pool.get(st, [])
    return [r for r in rank_list(metrics, me, pool) if r["raw"] is not None]


# ------------------------------------------------------------------------------------
# Player report assembly
# ------------------------------------------------------------------------------------

def bio(S, pid):
    p = S.players.get(pid, {})
    out = {}
    bd = p.get("birth_date")
    if bd:
        try:
            bdd = bd if isinstance(bd, date) else datetime.strptime(str(bd)[:10], "%Y-%m-%d").date()
            today = date.today()
            out["age"] = today.year - bdd.year - ((today.month, today.day) < (bdd.month, bdd.day))
        except ValueError:
            pass
    h = p.get("height")
    if h:
        try:
            h = int(float(h))
            out["height"] = f"{h // 12}'{h % 12}\""
        except (TypeError, ValueError):
            out["height"] = str(h)
    if p.get("weight"):
        out["weight"] = f"{int(float(p['weight']))} lbs"
    if p.get("college"):
        out["college"] = p["college"]
    if p.get("draft_round") and p.get("draft_pick"):
        yr = p.get("rookie_season")
        out["draft"] = f"{yr} " if yr else ""
        out["draft"] += f"Rd {int(p['draft_round'])}, pick {int(p['draft_pick'])}"
    elif p.get("rookie_season"):
        out["draft"] = f"{p['rookie_season']} undrafted"
    if p.get("exp") is not None:
        e = int(p["exp"])
        out["exp"] = "Rookie" if e == 0 else f"{e} yr{'s' if e != 1 else ''} exp"
    return out


def schedule_view(S, team, pos):
    games = sorted([gm for gm in S.schedule if team in (gm["home"], gm["away"])], key=lambda x: x["week"])
    if not games:
        return None
    all_weeks = sorted({gm["week"] for gm in S.schedule})
    played_weeks = {gm["week"] for gm in games}
    byes = [w for w in all_weeks if w not in played_weeks]
    upcoming = []
    for gm in games:
        if gm["home_score"] is not None:
            continue
        home = gm["home"] == team
        opp = gm["away"] if home else gm["home"]
        implied = None
        if gm["total"] is not None and gm["spread"] is not None:
            h = (gm["total"] + gm["spread"]) / 2
            implied = h if home else gm["total"] - h
        f = S.fpa.get((opp, pos), {})
        upcoming.append({
            "week": gm["week"], "opp": opp, "home": home, "label": f"{'vs' if home else '@'} {opp}",
            "gameday": gm["gameday"], "gametime": gm["gametime"], "spread": gm["spread"], "total": gm["total"],
            "implied": implied,
            "team_spread": (-gm["spread"] if home else gm["spread"]) if gm["spread"] is not None else None,
            "fpa_rank": f.get("rank"), "fpa_avg": f.get("avg"), "fpa_n": f.get("n"),
            "playoff": gm["week"] in FANTASY_PLAYOFF_WEEKS,
        })
    po = [u["fpa_rank"] for u in upcoming if u["playoff"] and u["fpa_rank"]]
    ros = [u["fpa_rank"] for u in upcoming if u["fpa_rank"]]
    return {"next": upcoming[0] if upcoming else None, "upcoming": upcoming, "byes": byes,
            "playoff_avg_rank": mean(po), "ros_avg_rank": mean(ros), "n_teams": S.n_teams}


def bucket(rows, keyfn, order, statfn):
    groups = defaultdict(list)
    for r in rows:
        k = keyfn(r)
        if k is not None:
            groups[k].append(r)
    keys = order if order else sorted(groups)
    return [(k, statfn(groups[k])) for k in keys if groups.get(k)]


RECV_COLS = [("Tgt", "targets", "int"), ("Rec", "rec", "int"), ("Catch%", "catch_rate", "pct"),
             ("Yds", "rec_yds", "int"), ("Y/Tgt", "yds_per_tgt", "dec1"), ("TD", "td", "int"),
             ("Drops", "drops", "int"), ("EPA/Tgt", "epa_per_tgt", "dec2s")]
RUSH_COLS = [("Att", "att", "int"), ("Yds", "yds", "int"), ("YPC", "ypc", "dec1"), ("TD", "td", "int"),
             ("Success", "success_rate", "pct"), ("10+ %", "expl_rate", "pct"), ("Stuff%", "stuff_rate", "pct"),
             ("EPA/Att", "epa_per", "dec2s")]
PASS_COLS = [("Att", "att", "int"), ("Cmp%", "cmp_pct", "pct"), ("Yds", "yds", "int"), ("Y/A", "ypa", "dec1"),
             ("TD", "td", "int"), ("INT", "ints", "int"), ("Sk", "sacks", "int"), ("EPA/DB", "epa_per_db", "dec2s")]


def depth_bucket(r):
    a = g(r, "air_yards")
    if a is None:
        return None
    return "Behind LOS" if a < 0 else "Short (0-9)" if a < 10 else "Intermediate (10-19)" if a < 20 else "Deep (20+)"


DEPTH_ORDER = ["Behind LOS", "Short (0-9)", "Intermediate (10-19)", "Deep (20+)"]
DOWN_ORDER = ["1st down", "2nd down", "3rd down", "4th down"]


def down_bucket(r):
    d = g(r, "down")
    return f"{ordinal(d)} down" if d else None


def has_ftn(rows):
    return any(r.get("_ftn") for r in rows)


def flag_split(rows, statfn, specs):
    out = []
    for label, fn in specs:
        sub = [r for r in rows if r.get("_ftn") and fn(r)]
        if sub:
            out.append((label, statfn(sub)))
    return out


def build_splits(S, pid, pos, weeks):
    tg = [r for r in S.tgt_rows.get(pid, []) if r["week"] in weeks]
    ru = [r for r in S.rush_rows.get(pid, []) if r["week"] in weeks]
    db = [r for r in S.db_rows.get(pid, []) if r["week"] in weeks]
    rs = recv_stats
    rus = rush_stats
    ps = lambda rows: pass_stats(rows, pid)  # noqa: E731

    def situ(rows, statfn, extra=()):
        specs = [("Red zone (inside 20)", lambda r: g(r, "yardline_100", 99) <= 20),
                 ("Inside the 10", lambda r: g(r, "yardline_100", 99) <= 10),
                 ("3rd / 4th down", lambda r: g(r, "down") in (3, 4)),
                 ("4th quarter / OT", lambda r: g(r, "qtr", 0) >= 4),
                 ("When trailing", lambda r: g(r, "score_differential", 0) < 0),
                 ("Tied or leading", lambda r: g(r, "score_differential", 0) >= 0)] + list(extra)
        return [(lab, statfn(sub)) for lab, fn in specs for sub in [[r for r in rows if fn(r)]] if sub]

    out = []
    if pos in ("WR", "TE"):
        out.append(("Receiving by depth", RECV_COLS, bucket(tg, depth_bucket, DEPTH_ORDER, rs)))
        out.append(("By direction", RECV_COLS, bucket(tg, lambda r: (g(r, "pass_location") or "").title() or None,
                                                      ["Left", "Middle", "Right"], rs)))
        out.append(("By down", RECV_COLS, bucket(tg, down_bucket, DOWN_ORDER, rs)))
        out.append(("Situational", RECV_COLS, situ(tg, rs)))
        if has_ftn(tg):
            out.append(("Play concept (FTN)", RECV_COLS, flag_split(tg, rs, [
                ("Play action", lambda r: ftn(r, "is_play_action")),
                ("No play action", lambda r: ftn(r, "is_play_action") is False),
                ("Screens", lambda r: ftn(r, "is_screen_pass")),
                ("Pre-snap motion", lambda r: ftn(r, "is_motion")),
                ("No motion", lambda r: ftn(r, "is_motion") is False),
                ("Vs blitz", lambda r: (ftn(r, "n_blitzers") or 0) > 0),
                ("No blitz", lambda r: ftn(r, "n_blitzers") == 0),
                ("Contested", lambda r: ftn(r, "is_contested_ball")),
            ])))
    elif pos == "RB":
        out.append(("Rushing by direction", RUSH_COLS, bucket(
            ru, lambda r: (g(r, "run_location") or "").title() or None, ["Left", "Middle", "Right"], rus)))

        def gap(r):
            if g(r, "run_location") == "middle":
                return "Middle"
            gp = g(r, "run_gap")
            return {"end": "Outside (end)", "tackle": "Off tackle", "guard": "Guard"}.get(gp) if gp else None
        out.append(("Rushing by gap", RUSH_COLS, bucket(ru, gap, ["Outside (end)", "Off tackle", "Guard", "Middle"],
                                                       rus)))
        out.append(("Rushing by down", RUSH_COLS, bucket(ru, down_bucket, DOWN_ORDER, rus)))
        out.append(("Rushing situational", RUSH_COLS, situ(ru, rus, [
            ("Inside the 5", lambda r: g(r, "yardline_100", 99) <= 5),
            ("Short yardage (1-2 to go)", lambda r: (g(r, "ydstogo") or 99) <= 2)])))
        if has_ftn(ru):
            def box(r):
                b = ftn(r, "n_defense_box")
                if b is None:
                    return None
                return "Light box (6 or fewer)" if b <= 6 else "Neutral box (7)" if b == 7 else "Stacked box (8+)"
            out.append(("Box count (FTN)", RUSH_COLS, bucket(
                ru, box, ["Light box (6 or fewer)", "Neutral box (7)", "Stacked box (8+)"], rus)))
        out.append(("Receiving", RECV_COLS, bucket(tg, depth_bucket, DEPTH_ORDER, rs) + situ(tg, rs)[:3]))
    elif pos == "QB":
        out.append(("Passing by depth", PASS_COLS, bucket(db, depth_bucket, DEPTH_ORDER, ps)))
        out.append(("Passing by down", PASS_COLS, bucket(db, down_bucket, DOWN_ORDER, ps)))
        out.append(("Situational", PASS_COLS, situ(db, ps, [
            ("Shotgun", lambda r: g(r, "shotgun") == 1), ("Under center", lambda r: g(r, "shotgun") == 0)])))
        if has_ftn(db):
            out.append(("Play concept (FTN)", PASS_COLS, flag_split(db, ps, [
                ("Play action", lambda r: ftn(r, "is_play_action")),
                ("No play action", lambda r: ftn(r, "is_play_action") is False),
                ("Vs blitz", lambda r: (ftn(r, "n_blitzers") or 0) > 0),
                ("No blitz", lambda r: ftn(r, "n_blitzers") == 0),
                ("Out of pocket", lambda r: ftn(r, "is_qb_out_of_pocket")),
                ("In pocket", lambda r: ftn(r, "is_qb_out_of_pocket") is False),
                ("Screens", lambda r: ftn(r, "is_screen_pass")),
                ("RPO", lambda r: ftn(r, "is_rpo")),
            ])))
        out.append(("Rushing", RUSH_COLS, [("All runs", rus(ru)),
                                           ("Designed runs", rus([r for r in ru if not g(r, "qb_scramble")])),
                                           ("Scrambles", rus([r for r in ru if g(r, "qb_scramble")]))]))
    return [s for s in out if s[2]]


def play_type_label(r, pid):
    d = r.get("desc") or ""
    if g(r, "two_point_attempt", 0):
        good = g(r, "two_point_conv_result") == "success" or "SUCCEEDS" in d
        return "2-pt conv", "Good" if good else "Failed"
    yds = int(num(r, "yards_gained"))
    if g(r, "passer_player_id") == pid:
        if num(r, "sack") == 1:
            return "Sacked", f"{yds} yds"
        if num(r, "interception") == 1:
            return "INT thrown", "–"
        if num(r, "complete_pass") == 1:
            return ("TD pass" if num(r, "pass_touchdown") == 1 else "Completion"), f"{yds} yds"
        return "Incomplete", "–"
    if g(r, "receiver_player_id") == pid:
        if num(r, "interception") == 1:
            return "INT", "–"
        if num(r, "complete_pass") == 1:
            return ("TD catch" if num(r, "pass_touchdown", "touchdown") == 1 else "Catch"), f"{yds} yds"
        if ftn(r, "is_drop"):
            return "DROP", "–"
        return "Incomplete", "–"
    if g(r, "rusher_player_id") == pid:
        td = num(r, "rush_touchdown") == 1
        if num(r, "qb_scramble") == 1:
            return ("TD scramble" if td else "Scramble"), f"{yds} yds"
        return ("TD run" if td else "Rush"), f"{yds} yds"
    for col, lab in [("punt_returner_player_id", "Punt return"), ("kickoff_returner_player_id", "Kick return")]:
        if g(r, col) == pid:
            ry = g(r, "return_yards")
            if ry is None:
                m = re.search(r"for (-?\d+) yards?", d)
                ry = int(m.group(1)) if m else 0
            return lab, f"{int(ry)} yds"
    for col, lab in ROLE_COLS:
        if g(r, col) == pid:
            return lab.title(), "–"
    return "Other", "–"


def clean_desc(s):
    s = s or ""
    s = re.sub(r"^\(\s*\d*:\d+\)\s*", "", s)
    s = re.sub(r"\b[A-Z]{2,3}-(?=\d{1,2}-[A-Z])", "", s)
    s = re.sub(r"\b[A-Z]{2,3}-(?=[A-Z]\.[A-Za-z])", "", s)
    s = re.sub(r"\b\d{1,2}-(?=[A-Z]\.?[A-Za-z])", "", s)
    return s


def build_log(S, pid, team):
    roles = [c for c, _ in ROLE_COLS]
    plays = [r for r in S.pbp if any(r.get(c) == pid for c in roles)]
    plays.sort(key=lambda r: (g(r, "week", 0), g(r, "play_id", 0)))
    log = []
    for r in plays:
        typ, res = play_type_label(r, pid)
        flags = []
        is_rec = g(r, "receiver_player_id") == pid
        if is_rec and ftn(r, "is_contested_ball"):
            flags.append("contested")
        if g(r, "passer_player_id") == pid and ftn(r, "is_interception_worthy") and num(r, "interception") == 0:
            flags.append("INT-worthy")
        if g(r, "passer_player_id") == pid and ftn(r, "is_play_action"):
            flags.append("PA")
        if g(r, "penalty_player_id") == pid:
            flags.append("penalty on him")
        if g(r, "fumbled_1_player_id") == pid and num(r, "fumble_lost") == 1:
            flags.append("fumble lost")
        wk = g(r, "week")
        t = team_of(S, pid, wk) or team
        log.append({
            "week": wk, "game_id": g(r, "game_id"), "opp": opp_label(g(r, "game_id"), t),
            "qtr": g(r, "qtr"), "time": g(r, "time"), "down": g(r, "down"), "ydstogo": g(r, "ydstogo"),
            "yrdln": g(r, "yrdln"), "type": typ, "result": res,
            "air_yards": g(r, "air_yards") if (is_rec or g(r, "passer_player_id") == pid) else None,
            "yac": g(r, "yards_after_catch") if typ in ("Catch", "TD catch", "Completion", "TD pass") else None,
            "epa": None if typ in ("Punt return", "Kick return") else g(r, "epa"),
            "flags": ", ".join(flags), "desc": clean_desc(r.get("desc")),
            "_td": typ.startswith("TD"), "_drop": typ == "DROP",
            "_bad": typ in ("INT", "INT thrown") or "fumble lost" in flags or "penalty on him" in flags
                    or "INT-worthy" in flags,
        })
    return log


TRENDS = {
    "WR": [("Snap share", "snap_pct", "pct100", 10), ("Route participation", "route_pct", "pct", .10),
           ("Target share", "tgt_share", "pct", .05), ("Air yards share", "air_share", "pct", .07),
           ("Targets per game", "targets", "dec1", 2), ("Expected fantasy points", "xfp", "dec1", 3)],
    "RB": [("Snap share", "snap_pct", "pct100", 10), ("Team rush share", "rush_share", "pct", .08),
           ("Target share", "tgt_share", "pct", .04), ("Carries per game", "carries", "dec1", 3),
           ("High-value touches", "hvt", "dec1", 1.5), ("Expected fantasy points", "xfp", "dec1", 3)],
    "QB": [("Dropbacks per game", "dropbacks", "dec1", 5), ("Carries per game", "carries", "dec1", 2),
           ("Expected fantasy points", "xfp", "dec1", 3)],
}
TRENDS["TE"] = TRENDS["WR"]


def build_report(S, pid):
    info = S.players.get(pid, {})
    tot = S.season_tot.get(pid, {})
    pos = tot.get("pos") or info.get("pos")
    if pos not in FANTASY_POS:
        pos = "WR"
    team = player_team(S, pid)
    name = info.get("name") or tot.get("name") or pid
    weeks = player_weeks(S, pid)
    sc = S.scoring
    m = player_metrics(S, pid, pos, weeks)
    m["rank_total"], m["rank_ppg"] = tot.get("rank_total"), tot.get("rank_ppg")

    # Week-by-week table, including byes and missed games
    wk_rows = {r["week"]: r for r in S.weekly.get(pid, [])}
    sched = schedule_view(S, team, pos) if team else None
    byes = set(sched["byes"]) if sched else set()
    weekly = []
    for w in range(1, S.last_week + 1):
        r = wk_rows.get(w)
        if r is None and w not in weeks:
            gm = next((x for x in S.schedule if x["week"] == w and team in (x["home"], x["away"])), None)
            if gm and gm["home_score"] is None:
                continue  # his team hasn't played this week yet
            weekly.append({"week": w, "status": "BYE" if w in byes else "Did not play"})
            continue
        u = usage_week(S, pid, w)
        t = (r or {}).get("team") or u["team"] or team
        opp = (r or {}).get("opp")
        lbl = None
        for gm in S.schedule:
            if gm["week"] == w and t in (gm["home"], gm["away"]):
                lbl = f"vs {gm['away']}" if gm["home"] == t else f"@ {gm['home']}"
                break
        row = {"week": w, "status": "", "opp": lbl or (f"vs {opp}" if opp else ""), **u}
        if r:
            row.update({k: r[k] for k in ("pts", "rank", "attempts", "completions", "pass_yds", "pass_td", "ints",
                                          "sacks", "carries", "rush_yds", "rush_td", "targets", "rec", "rec_yds",
                                          "rec_td", "fum_lost")})
            row["carries_official"] = r["carries"]
        else:
            row["pts"] = 0.0  # played snaps but recorded no stats
        row["fpoe"] = (row["pts"] - row["xfp"]) if row.get("pts") is not None and row.get("xfp") is not None else None
        if pos == "QB":
            row["epa_db"] = mean([g(x, "epa") for x in S.db_pw.get((pid, w), [])])
        weekly.append(row)
    played = [w for w in weekly if w.get("pts") is not None]

    # Fantasy profile
    pts = [w["pts"] for w in played]
    boom, bust = BOOM_BUST[pos]
    ranks = [w["rank"] for w in played if w.get("rank")]
    prof = {
        "games": len(pts), "pts": sum(pts), "ppg": mean(pts), "median": statistics.median(pts) if pts else None,
        "floor": quantile(pts, .25), "ceiling": quantile(pts, .75), "best": max(pts) if pts else None,
        "worst": min(pts) if pts else None, "stdev": statistics.pstdev(pts) if len(pts) > 1 else None,
        "boom_rate": div(sum(1 for p in pts if p >= boom), len(pts)),
        "bust_rate": div(sum(1 for p in pts if p < bust), len(pts)),
        "top12": sum(1 for x in ranks if x <= 12), "top24": sum(1 for x in ranks if x <= 24),
        "top36": sum(1 for x in ranks if x <= 36),
        "starter_rate": div(sum(1 for x in ranks if x <= STARTER_CUTOFF[pos]), len(ranks)),
        "last3_ppg": mean(pts[-3:]) if len(pts) >= 3 else None,
        "boom": boom, "bust": bust,
    }
    prof["cv"] = div(prof["stdev"], prof["ppg"]) if prof["ppg"] and prof["ppg"] > 0 else None
    best = max(played, key=lambda w: w["pts"]) if played else None
    prof["best_label"] = f"Wk {best['week']} {best['opp']}" if best else ""

    # Trends: season vs last 3 games played
    trends = []
    if len(played) >= 4:
        last3 = played[-3:]
        for label, key, kind, thr in TRENDS[pos]:
            kk = key
            s_val = mean([w.get(kk) for w in played])
            l_val = mean([w.get(kk) for w in last3])
            if s_val is None or l_val is None:
                continue
            trends.append({"label": label, "season": s_val, "last3": l_val, "delta": l_val - s_val, "kind": kind,
                           "thr": thr})
        trends.insert(0, {"label": "Fantasy points per game", "season": prof["ppg"], "last3": prof["last3_ppg"],
                          "delta": prof["last3_ppg"] - prof["ppg"], "kind": "dec1", "thr": 4})

    ranks_list, pool_n, thr = league_ranks(S, pid, pos, m)
    ngs = ngs_ranks(S, pid, pos)
    splits = build_splits(S, pid, pos, set(weeks))
    log = build_log(S, pid, team)

    inj = S.injuries.get(pid)
    if inj and inj["week"] < S.last_week:
        inj = None

    rep = {
        "pid": pid, "name": name, "pos": pos, "team": team, "season": S.season, "fmt": S.fmt_name,
        "bio": bio(S, pid), "jersey": info.get("jersey"), "m": m, "prof": prof, "weekly": weekly,
        "trends": trends, "ranks": ranks_list, "pool_n": pool_n, "pool_thr": thr, "ngs": ngs,
        "sched": sched, "team_ctx": S.team_ctx.get(team), "n_teams": S.n_teams, "splits": splits, "log": log,
        "injury": inj, "weeks": weeks, "last_week": S.last_week, "short": "", "notes": list(S.notes),
        "pos_counts": S.pos_counts.get(pos, (0, 0)), "min_games": S.min_games, "xfp_basis": S.xfp_basis, "fpa_avg": S.fpa_avg.get(pos),
    }
    shorts = Counter()
    for r in S.tgt_rows.get(pid, [])[:20]:
        shorts[g(r, "receiver_player_name")] += 1
    for r in S.rush_rows.get(pid, [])[:20]:
        shorts[g(r, "rusher_player_name")] += 1
    for r in S.db_rows.get(pid, [])[:20]:
        shorts[g(r, "passer_player_name")] += 1
    shorts.pop(None, None)
    rep["short"] = shorts.most_common(1)[0][0] if shorts else ""
    rep["insights"] = build_insights(rep)
    return rep


# ------------------------------------------------------------------------------------
# Edge notes: plain-language flags for the things that matter in fantasy
# ------------------------------------------------------------------------------------

def lc(label):
    w = label.split()[0]
    return label if (w.isupper() or "/" in w) else label[0].lower() + label[1:]


def build_insights(rep):
    out = []
    m, p, pos = rep["m"], rep["prof"], rep["pos"]
    pc = rep["pos_counts"]

    def add(weight, tone, text):
        out.append((weight, tone, text))

    if m.get("rank_ppg") and p["ppg"] is not None:
        r = m["rank_ppg"]
        tier = f"{pos}{(r - 1) // 12 + 1}" if r <= 48 else "outside the top 48"
        add(10, "info", f"{pos}{r} in points per game ({p['ppg']:.1f} PPG) among {pc[1]} {pos}s with "
                        f"{rep['min_games']}+ games, which is {tier} production.")
    f = m.get("fpoe_pg")
    if f is not None and m.get("xfp_games", 0) >= 3:
        if f <= -2:
            add(9, "up", f"Scoring {abs(f):.1f} fewer points per game than his usage predicts "
                         f"({m['xfp_pg']:.1f} expected vs {p['ppg']:.1f} actual). The opportunity is there; "
                         f"efficiency and TDs tend to catch up. Classic buy-low profile.")
        elif f >= 3:
            add(8, "down", f"Scoring {f:.1f} more points per game than his usage predicts "
                           f"({m['xfp_pg']:.1f} expected). Some of that is likely unsustainable efficiency "
                           f"or TD luck. Sell-high candidate if the price is right.")
        elif abs(f) < 1:
            add(3, "info", f"Production matches his usage almost exactly ({m['xfp_pg']:.1f} expected PPG), "
                           f"so what you see is what you get.")
    if m.get("exp_td") is not None:
        diff = m["act_td_xweeks"] - m["exp_td"]
        if diff <= -1.5:
            add(8, "up", f"{int(m['act_td_xweeks'])} rushing/receiving TDs on {m['exp_td']:.1f} expected. "
                         f"His usage near the goal line says more TDs are coming.")
        elif diff >= 2:
            add(7, "down", f"{int(m['act_td_xweeks'])} rushing/receiving TDs on only {m['exp_td']:.1f} expected. "
                           f"TD rate is running hot and is likely to cool off.")
    if pos == "QB" and m.get("exp_pass_td") is not None:
        diff = m["act_pass_td_xweeks"] - m["exp_pass_td"]
        if abs(diff) >= 3:
            add(7, "up" if diff < 0 else "down",
                f"{int(m['act_pass_td_xweeks'])} passing TDs on {m['exp_pass_td']:.1f} expected, "
                f"{'positive' if diff < 0 else 'negative'} TD regression likely.")
    for t in rep["trends"]:
        if t["label"].startswith("Fantasy points"):
            continue
        if abs(t["delta"]) >= t["thr"]:
            up = t["delta"] > 0
            add(7.5, "up" if up else "down",
                f"{t['label']} {'up' if up else 'down'} over the last 3 games: {fmt(t['last3'], t['kind'])} "
                f"vs {fmt(t['season'], t['kind'])} on the season.")
    if p["games"] >= 3:
        cut = STARTER_CUTOFF[pos]
        add(5, "info", f"Finished as a top-{cut} {pos} in {int(round((p['starter_rate'] or 0) * p['games']))} of "
                       f"{p['games']} games; {p['top12']} top-12 week{'s' if p['top12'] != 1 else ''}.")
        if (p["boom_rate"] or 0) >= 0.35:
            add(6, "up", f"Boom rate of {p['boom_rate']:.0%} ({p['boom']}+ points). He has a real ceiling.")
        if (p["bust_rate"] or 0) >= 0.40:
            add(6, "down", f"Busts (under {p['bust']} points) in {p['bust_rate']:.0%} of games. That's a shaky floor.")
        if p["cv"] is not None and p["cv"] <= 0.35 and (p["ppg"] or 0) >= 10:
            add(5, "up", "One of the steadier weekly scorers: low game-to-game volatility.")
    if (m.get("td_pts_share") or 0) >= 0.40 and p["games"] >= 3:
        add(6, "down", f"{m['td_pts_share']:.0%} of his points come from touchdowns, a TD-dependent profile.")

    sched = rep["sched"]
    if sched and sched["next"]:
        nx = sched["next"]
        if nx["fpa_rank"]:
            n = nx["fpa_n"]
            if nx["fpa_rank"] <= 6:
                add(8, "up", f"Week {nx['week']} {nx['label']}: {nx['opp']} allows the {ordinal(nx['fpa_rank'])}-most "
                             f"fantasy points to {pos}s ({nx['fpa_avg']:.1f} per game). Smash spot.")
            elif nx["fpa_rank"] >= n - 5:
                add(8, "down", f"Week {nx['week']} {nx['label']}: {nx['opp']} allows the {ordinal(n - nx['fpa_rank'] + 1)}"
                               f"-fewest fantasy points to {pos}s ({nx['fpa_avg']:.1f} per game). Tough matchup.")
        if nx["implied"] is not None:
            if nx["implied"] >= 26:
                add(7, "up", f"Vegas implies {nx['implied']:.1f} points for {rep['team']} in week {nx['week']}, "
                             f"a high-scoring environment.")
            elif nx["implied"] <= 18:
                add(7, "down", f"Vegas implies only {nx['implied']:.1f} points for {rep['team']} in week {nx['week']}.")
        if sched["playoff_avg_rank"]:
            r = sched["playoff_avg_rank"]
            n = sched["n_teams"] or 32
            if r <= n * 0.33:
                add(6, "up", f"Fantasy playoff schedule (weeks {FANTASY_PLAYOFF_WEEKS[0]}-{FANTASY_PLAYOFF_WEEKS[-1]}) "
                             f"is favorable: opponents average a {r:.0f} rank in points allowed to {pos}s.")
            elif r >= n * 0.67:
                add(6, "down", f"Fantasy playoff schedule (weeks {FANTASY_PLAYOFF_WEEKS[0]}-{FANTASY_PLAYOFF_WEEKS[-1]}) "
                               f"is tough: opponents average a {r:.0f} rank in points allowed to {pos}s.")
    tc = rep["team_ctx"]
    if tc and tc.get("proe") is not None and pos != "RB":
        if tc["proe"] >= 0.04:
            add(4, "up", f"{rep['team']} passes {tc['proe']:.0%} more than expected in neutral situations "
                         f"({ordinal(tc['proe_rank'])} in the NFL).")
        elif tc["proe"] <= -0.04:
            add(4, "down", f"{rep['team']} is run-heavy: {abs(tc['proe']):.0%} below expected pass rate in neutral "
                           f"situations ({ordinal(tc['proe_rank'])}).")
    for r in rep["ranks"]:
        if r["pct"] is None or r["higher"] is None or r["key"] in ("ppg", "xfp_pg", "fpoe_pg"):
            continue
        if r["pct"] >= 90:
            add(5.5, "up", f"Top 10% at his position in {lc(r['label'])} ({r['value']}, "
                           f"{ordinal(r['rank'])} of {r['n']}).")
        elif r["pct"] <= 10:
            add(5, "down", f"Bottom 10% at his position in {lc(r['label'])} ({r['value']}, "
                           f"{ordinal(r['rank'])} of {r['n']}).")
    if rep["injury"] and rep["injury"].get("status"):
        i = rep["injury"]
        txt = f"Injury report (week {i['week']}): {i['status']}"
        if i.get("injury"):
            txt += f", {i['injury']}"
        if i.get("practice"):
            txt += f" ({i['practice']})"
        add(11, "down", txt + ".")
    out.sort(key=lambda x: -x[0])
    return [(tone, text) for _, tone, text in out[:10]]


# ------------------------------------------------------------------------------------
# Console + CSV output
# ------------------------------------------------------------------------------------

def print_summary(rep):
    p, m = rep["prof"], rep["m"]
    print("\n" + "=" * 78)
    print(f"{rep['name']}  |  {rep['team']} {rep['pos']}  |  {rep['season']}  |  {FORMAT_LABEL[rep['fmt']]}")
    print("=" * 78)
    if p["games"]:
        rk = f"{rep['pos']}{m['rank_ppg']}" if m.get("rank_ppg") else "unranked"
        print(f"{p['ppg']:.1f} PPG ({rk})  |  {p['pts']:.1f} pts in {p['games']} games  |  "
              f"floor {fmt(p['floor'], 'dec1')} / ceiling {fmt(p['ceiling'], 'dec1')}  |  "
              f"top-{STARTER_CUTOFF[rep['pos']]} in {fmt(p['starter_rate'], 'pct')} of games")
    if m.get("xfp_pg") is not None:
        print(f"Expected {m['xfp_pg']:.1f} PPG  |  {fmt(m['fpoe_pg'], 'dec1s')} points over expected per game")
    if rep["insights"]:
        print("\nEdge notes:")
        for tone, text in rep["insights"]:
            mark = {"up": "+", "down": "-", "info": "*"}[tone]
            print(f"  {mark} {text}")
    nx = rep["sched"]["next"] if rep["sched"] else None
    if nx:
        line = f"\nNext: week {nx['week']} {nx['label']}"
        if nx["implied"] is not None:
            line += f"  |  implied team total {nx['implied']:.1f}"
        if nx["fpa_rank"]:
            line += f"  |  opponent ranks {ordinal(nx['fpa_rank'])} in points allowed to {rep['pos']}s"
        print(line)


def write_csvs(rep, base):
    paths = []

    def dump(path, rows, cols):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k in cols})
        paths.append(path)

    dump(f"{base}_weekly.csv", rep["weekly"],
         ["week", "status", "opp", "pts", "rank", "xfp", "fpoe", "snaps", "snap_pct", "routes", "route_pct",
          "targets", "tgt_share", "air", "air_share", "rec", "rec_yds", "rec_td", "rz_tgt", "ez_tgt", "carries",
          "rush_share", "rush_yds", "rush_td", "rz_car", "i10_car", "hvt", "rz_share", "attempts", "completions",
          "pass_yds", "pass_td", "ints", "sacks", "dropbacks", "epa_db", "fum_lost"])
    metric_rows = [{"section": "League rank", "metric": r["label"], "value": r["value"], "rank": r["rank"],
                    "of": r["n"], "percentile": round(r["pct"]) if r["pct"] is not None else None}
                   for r in rep["ranks"] + rep["ngs"]]
    p = rep["prof"]
    for k, lab, kind in [("ppg", "Points per game", "dec1"), ("median", "Median game", "dec1"),
                         ("floor", "Floor (25th pct)", "dec1"), ("ceiling", "Ceiling (75th pct)", "dec1"),
                         ("boom_rate", "Boom rate", "pct"), ("bust_rate", "Bust rate", "pct"),
                         ("starter_rate", "Starter-level finish rate", "pct"), ("stdev", "Std deviation", "dec1")]:
        metric_rows.append({"section": "Fantasy profile", "metric": lab, "value": fmt(p.get(k), kind)})
    for t in rep["trends"]:
        metric_rows.append({"section": "Trend (last 3 vs season)", "metric": t["label"],
                            "value": f"{fmt(t['last3'], t['kind'])} vs {fmt(t['season'], t['kind'])}"})
    for tone, text in rep["insights"]:
        metric_rows.append({"section": "Edge note", "metric": tone, "value": text})
    dump(f"{base}_metrics.csv", metric_rows, ["section", "metric", "value", "rank", "of", "percentile"])
    dump(f"{base}_plays.csv", rep["log"], ["week", "opp", "qtr", "time", "down", "ydstogo", "yrdln", "type",
                                           "result", "air_yards", "yac", "epa", "flags", "desc"])
    return paths


# ------------------------------------------------------------------------------------
# PDF
# ------------------------------------------------------------------------------------

def build_pdf(rep, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether, PageBreak, PageTemplate,
                                    Paragraph, Spacer, Table, TableStyle)

    DARK = colors.HexColor("#1f2a37"); ACCENT = colors.HexColor("#f2a900")
    INK = colors.HexColor("#1f2328"); MUTED = colors.HexColor("#6b7280")
    LINE = colors.HexColor("#e5e7eb"); ZEBRA = colors.HexColor("#f7f8f9"); SOFT = colors.HexColor("#eef1f4")
    TDBG = colors.HexColor("#fff4d6"); DROPBG = colors.HexColor("#ffe8d6"); BADBG = colors.HexColor("#fdecec")
    GOOD = colors.HexColor("#2f855a"); MID = colors.HexColor("#d69e2e"); POOR = colors.HexColor("#c53030")
    BLUE = colors.HexColor("#3b82c4"); GRAY = colors.HexColor("#9ca3af")
    GOODBG = colors.HexColor("#e3f3ea"); POORBG = colors.HexColor("#fbe4e4")

    pos, m, p = rep["pos"], rep["m"], rep["prof"]

    def esc(s):
        return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def tier_color(rank):
        if not rank:
            return GRAY
        return GOOD if rank <= 12 else BLUE if rank <= 24 else MID if rank <= 36 else GRAY

    H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=23, textColor=colors.white, leading=27)
    SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=10, textColor=ACCENT, leading=13)
    SUB2 = ParagraphStyle("sub2", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#cbd5e1"), leading=11)
    H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, textColor=DARK, leading=16, spaceAfter=5)
    H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, textColor=INK, leading=13)
    CELL = ParagraphStyle("c", fontName="Helvetica", fontSize=7.8, textColor=INK, leading=9.6)
    BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=8.6, textColor=INK, leading=11.2)
    NOTE = ParagraphStyle("n", fontName="Helvetica", fontSize=7.6, textColor=MUTED, leading=10)
    KV = ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=16, textColor=DARK, alignment=1, leading=19)
    KS = ParagraphStyle("ks", fontName="Helvetica", fontSize=7, textColor=MUTED, alignment=1, leading=8.5)
    KL = ParagraphStyle("kl", fontName="Helvetica-Bold", fontSize=7, textColor=INK, alignment=1, leading=8.5)

    W, H = landscape(letter)
    M = 0.45 * inch
    CW = W - 2 * M

    class PctBar(Flowable):
        def __init__(self, pct, higher, width):
            super().__init__()
            self.pct, self.higher, self.width, self.height = pct, higher, width, 7

        def draw(self):
            c = self.canv
            c.setFillColor(LINE)
            c.roundRect(0, 0, self.width, self.height, 3, stroke=0, fill=1)
            if self.pct is None:
                return
            col = BLUE if self.higher is None else GOOD if self.pct >= 67 else MID if self.pct >= 33 else POOR
            c.setFillColor(col)
            c.roundRect(0, 0, max(4, self.width * self.pct / 100), self.height, 3, stroke=0, fill=1)

    class PointsChart(Flowable):
        def __init__(self, weeks, width, height):
            super().__init__()
            self.weeks, self.width, self.height = weeks, width, height

        def draw(self):
            c = self.canv
            L, B, T, R = 26, 18, 22, 6
            pw, ph = self.width - L - R, self.height - B - T
            vals = [w.get("pts") or 0 for w in self.weeks] + [w.get("xfp") or 0 for w in self.weeks] + [p["boom"]]
            step = 5 if max(vals) <= 30 else 10
            ymax = max(step, math.ceil(max(vals) * 1.12 / step) * step)
            c.setFont("Helvetica", 6.5)
            for y in range(0, int(ymax) + 1, step):
                yy = B + ph * y / ymax
                c.setStrokeColor(LINE); c.setLineWidth(0.5); c.line(L, yy, L + pw, yy)
                c.setFillColor(MUTED); c.drawRightString(L - 4, yy - 2, str(y))
            n = max(1, len(self.weeks))
            slot = pw / n
            bw = min(26, slot * 0.62)
            if p["ppg"]:
                yy = B + ph * p["ppg"] / ymax
                c.setStrokeColor(ACCENT); c.setDash(3, 2); c.setLineWidth(1); c.line(L, yy, L + pw, yy); c.setDash()
            for i, w in enumerate(self.weeks):
                cx = L + slot * (i + 0.5)
                c.setFillColor(MUTED); c.setFont("Helvetica", 6.5)
                c.drawCentredString(cx, B - 10, f"W{w['week']}")
                if w.get("status"):
                    c.setFont("Helvetica-Oblique", 6)
                    c.drawCentredString(cx, B + 3, "BYE" if w["status"] == "BYE" else "OUT")
                    continue
                pts = w.get("pts") or 0
                h = ph * max(0, pts) / ymax
                c.setFillColor(tier_color(w.get("rank")))
                c.rect(cx - bw / 2, B, bw, h, stroke=0, fill=1)
                top = B + h
                if w.get("xfp") is not None:
                    xy = B + ph * w["xfp"] / ymax
                    c.setStrokeColor(DARK); c.setLineWidth(1.8)
                    c.line(cx - bw / 2 - 2, xy, cx + bw / 2 + 2, xy)
                    if abs(xy - top) < 9:
                        top = max(top, xy)
                c.setFillColor(INK); c.setFont("Helvetica-Bold", 6.3)
                c.drawCentredString(cx, top + 3, f"{pts:.1f}")
            # legend
            lx, ly = L, self.height - 8
            c.setFont("Helvetica", 6.5)
            for col, lab in [(GOOD, f"{pos}1 week"), (BLUE, f"{pos}2"), (MID, f"{pos}3"), (GRAY, "below")]:
                c.setFillColor(col); c.rect(lx, ly - 1, 7, 6, stroke=0, fill=1)
                c.setFillColor(MUTED); c.drawString(lx + 9, ly, lab); lx += 9 + c.stringWidth(lab, "Helvetica", 6.5) + 10
            c.setStrokeColor(DARK); c.setLineWidth(1.8); c.line(lx, ly + 2, lx + 10, ly + 2)
            c.drawString(lx + 13, ly, "expected pts (xFP)"); lx += 13 + c.stringWidth("expected pts (xFP)", "Helvetica", 6.5) + 10
            c.setStrokeColor(ACCENT); c.setDash(3, 2); c.setLineWidth(1); c.line(lx, ly + 2, lx + 12, ly + 2); c.setDash()
            c.drawString(lx + 15, ly, "season average")

    class LineChart(Flowable):
        def __init__(self, labels, series, width, height, pct=True):
            super().__init__()
            self.labels, self.series, self.width, self.height, self.pct = labels, series, width, height, pct

        def draw(self):
            c = self.canv
            L, B, T, R = 26, 18, 16, 6
            pw, ph = self.width - L - R, self.height - B - T
            allv = [v for _, _, vs in self.series for v in vs if v is not None]
            ymax = 1.0 if self.pct else max(20, math.ceil(max(allv or [1]) * 1.12 / 20) * 20)
            ticks = [0, .25, .5, .75, 1] if self.pct else [ymax * i / 4 for i in range(5)]
            c.setFont("Helvetica", 6.5)
            for t in ticks:
                yy = B + ph * t / ymax
                c.setStrokeColor(LINE); c.setLineWidth(0.5); c.line(L, yy, L + pw, yy)
                c.setFillColor(MUTED)
                c.drawRightString(L - 4, yy - 2, f"{t:.0%}" if self.pct else f"{t:.0f}")
            n = max(1, len(self.labels))
            slot = pw / n
            for i, lab in enumerate(self.labels):
                c.setFillColor(MUTED); c.drawCentredString(L + slot * (i + .5), B - 10, lab)
            for name, col, vs in self.series:
                c.setStrokeColor(col); c.setFillColor(col); c.setLineWidth(1.6)
                prev = None
                for i, v in enumerate(vs):
                    if v is None:
                        prev = None
                        continue
                    x, y = L + slot * (i + .5), B + ph * min(v, ymax) / ymax
                    if prev:
                        c.line(prev[0], prev[1], x, y)
                    c.circle(x, y, 1.8, stroke=0, fill=1)
                    prev = (x, y)
            lx, ly = L, self.height - 8
            for name, col, _ in self.series:
                c.setFillColor(col); c.rect(lx, ly - 1, 7, 6, stroke=0, fill=1)
                c.setFillColor(MUTED); c.drawString(lx + 9, ly, name)
                lx += 9 + c.stringWidth(name, "Helvetica", 6.5) + 12

    def on_page(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7.2); c.setFillColor(MUTED)
        c.drawString(M, 0.27 * inch, f"{rep['name']} · {rep['season']} fantasy report · {FORMAT_LABEL[rep['fmt']]} · "
                                     f"Data: nflverse (play-by-play, FTN charting, Next Gen Stats, ffopportunity) · "
                                     f"{date.today():%b %d, %Y}")
        c.drawRightString(W - M, 0.27 * inch, f"Page {doc.page}")
        c.setStrokeColor(ACCENT); c.setLineWidth(2); c.line(M, H - 0.3 * inch, W - M, H - 0.3 * inch)
        c.restoreState()

    doc = BaseDocTemplate(path, pagesize=landscape(letter), leftMargin=M, rightMargin=M, topMargin=0.45 * inch,
                          bottomMargin=0.45 * inch, title=f"{rep['name']} {rep['season']} Fantasy Report")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(M, 0.45 * inch, CW, H - 0.9 * inch, id="f",
                                                             leftPadding=0, rightPadding=0, topPadding=0,
                                                             bottomPadding=0)], onPage=on_page)])

    def tstyle(rows, font=8, zebra=True, total=False, extra=None, header=True):
        st = [("FONT", (0, 0), (-1, -1), "Helvetica", font), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
              ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE)]
        if header:
            st += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", font - 0.4), ("BACKGROUND", (0, 0), (-1, 0), DARK),
                   ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        if zebra:
            st += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(rows), 2)]
        if total:
            st += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", font), ("LINEABOVE", (0, -1), (-1, -1), 1.2, DARK),
                   ("BACKGROUND", (0, -1), (-1, -1), SOFT)]
        return TableStyle(st + (extra or []))

    def mk(rows, widths, total_w, **kw):
        sc = total_w / sum(widths)
        t = Table(rows, colWidths=[w * sc for w in widths], repeatRows=1 if kw.get("header", True) else 0)
        t.setStyle(tstyle(rows, **kw))
        return t

    def side_by_side(left, right, lw, gap=14):
        t = Table([[left, right]], colWidths=[lw + gap, CW - lw - gap])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (0, -1), gap), ("RIGHTPADDING", (1, 0), (1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return t

    S_ = []

    # ============ Page 1: fantasy dashboard ============
    b = rep["bio"]
    line1 = " · ".join(x for x in [rep["team"], pos, f"#{rep['jersey']}" if rep.get("jersey") is not None else None,
                                   f"Age {b['age']}" if b.get("age") else None, b.get("exp"),
                                   FORMAT_LABEL[rep["fmt"]]] if x)
    line2 = " · ".join(x for x in [b.get("height"), b.get("weight"), b.get("college"),
                                   f"Drafted {b['draft']}" if b.get("draft") else None,
                                   f"{rep['season']} season through week {rep['last_week']}"] if x)
    inj = rep["injury"]
    if inj and inj.get("status"):
        line2 += f" · <font color='#fca5a5'>Injury: {esc(inj['status'])}" \
                 f"{(' (' + esc(inj['injury']) + ')') if inj.get('injury') else ''}</font>"
    banner = Table([[Paragraph(esc(rep["name"]), H1)], [Paragraph(esc(line1), SUB)], [Paragraph(line2, SUB2)]],
                   colWidths=[CW])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), DARK), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                                ("TOPPADDING", (0, 0), (-1, 0), 10), ("TOPPADDING", (0, 1), (-1, -1), 1),
                                ("BOTTOMPADDING", (0, -1), (-1, -1), 10), ("LINEBELOW", (0, -1), (-1, -1), 4, ACCENT)]))
    S_ += [banner, Spacer(1, 9)]

    pc = rep["pos_counts"]
    key_usage = {"WR": ("tgt_share", "Target share", "pct"), "TE": ("tgt_share", "Target share", "pct"),
                 "RB": ("opp_pg", "Opportunities / game", "dec1"), "QB": ("p_epa_per_db", "EPA / dropback", "dec2s")}[pos]
    rank_for = {r["key"]: r for r in rep["ranks"]}

    def rk(key):
        r = rank_for.get(key)
        return f"{ordinal(r['rank'])} of {r['n']}" if r and r["rank"] else ""
    tiles_data = [
        (fmt(p["ppg"], "dec1"), "Points / game", f"{pos}{m['rank_ppg']}" if m.get("rank_ppg") else ""),
        (fmt(p["pts"], "dec1"), "Total points", f"{pos}{m['rank_total']}" if m.get("rank_total") else ""),
        (fmt(m.get("xfp_pg"), "dec1"), "Expected pts / game", rk("xfp_pg")),
        (fmt(m.get("fpoe_pg"), "dec1s"), "Pts over expected / g", "luck/efficiency"),
        (f"{p['top12']}/{p['games']}", "Top-12 weeks", f"top-24: {p['top24']}"),
        (fmt(p["boom_rate"], "pct"), f"Boom rate ({p['boom']}+)", f"bust {fmt(p['bust_rate'], 'pct')}"),
        (fmt(m.get("snap_pct"), "pct100"), "Snap share", rk("snap_pct")),
        (fmt(m.get(key_usage[0]), key_usage[2]), key_usage[1], rk(key_usage[0])),
    ]
    tiles = Table([[Paragraph(v, KV) for v, _, _ in tiles_data], [Paragraph(l, KL) for _, l, _ in tiles_data],
                   [Paragraph(esc(s), KS) for _, _, s in tiles_data]], colWidths=[CW / 8] * 8)
    tiles.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, LINE), ("LINEAFTER", (0, 0), (-2, -1), 0.75, LINE),
                               ("TOPPADDING", (0, 0), (-1, 0), 7), ("TOPPADDING", (0, 1), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, 1), 1), ("BOTTOMPADDING", (0, -1), (-1, -1), 6)]))
    S_ += [tiles, Spacer(1, 9)]

    chart_w = CW * 0.60
    chart = PointsChart(rep["weekly"], chart_w, 150)
    prof_rows = [["Fantasy profile", ""],
                 ["Median game", fmt(p["median"], "dec1")],
                 ["Floor / ceiling (25th / 75th pct)", f"{fmt(p['floor'], 'dec1')} / {fmt(p['ceiling'], 'dec1')}"],
                 ["Best game", f"{fmt(p['best'], 'dec1')}  {p['best_label']}"],
                 ["Worst game", fmt(p["worst"], "dec1")],
                 ["Volatility (std dev)", fmt(p["stdev"], "dec1")],
                 [f"Top-{STARTER_CUTOFF[pos]} finish rate", fmt(p["starter_rate"], "pct")],
                 ["Last 3 games PPG", fmt(p["last3_ppg"], "dec1")],
                 ["Points from TDs", fmt(m.get("td_pts_share"), "pct")]]
    if rep["fmt"] != "standard" and pos != "QB":
        prof_rows.append(["Points from receptions", fmt(m.get("rec_pts_share"), "pct")])
    if pos == "QB":
        prof_rows.append(["Points from rushing", fmt(m.get("rush_pts_share"), "pct")])
    prof_t = mk(prof_rows, [2.2, 1.3], CW - chart_w - 14, font=7.8,
                extra=[("SPAN", (0, 0), (-1, 0)), ("ALIGN", (1, 1), (1, -1), "RIGHT")])
    S_ += [side_by_side(chart, prof_t, chart_w), Spacer(1, 9)]

    S_.append(Paragraph("Edge notes", H2))
    if rep["insights"]:
        rows, ex = [], []
        for i, (tone, text) in enumerate(rep["insights"]):
            col = GOOD if tone == "up" else POOR if tone == "down" else BLUE
            rows.append(["", Paragraph(esc(text), BODY)])
            ex.append(("BACKGROUND", (0, i), (0, i), col))
        half = (len(rows) + 1) // 2
        cols_w = (CW - 14) / 2

        def notes_table(rs, exs):
            t = Table(rs, colWidths=[4, cols_w - 4])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, -1), 7),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                                   ("LINEBELOW", (0, 0), (-1, -1), 2.5, colors.white)] + exs))
            return t
        left = notes_table(rows[:half], ex[:half])
        right = notes_table(rows[half:], [(a, (0, b_[1] - half), (0, c_[1] - half), d)
                                          for a, b_, c_, d in ex[half:]]) if rows[half:] else ""
        S_.append(side_by_side(left, right, cols_w))
        S_.append(Spacer(1, 4))
        S_.append(Paragraph("Green = working in his favor, red = a warning sign, blue = context. Expected points (xFP) "
                            "measure what an average player would score with the same targets, carries, depth and "
                            f"field position (basis: {esc(rep['xfp_basis'] or 'n/a')}).", NOTE))
    else:
        S_.append(Paragraph("Not enough games yet for edge notes.", BODY))
    S_.append(PageBreak())

    # ============ Page 2: week by week + usage trends ============
    S_.append(Paragraph("Week by week", H2))
    if pos in ("WR", "TE"):
        hdr = ["Wk", "Opp", "Pts", "Finish", "xFP", "+/-", "Snap%", "Route%", "Tgt", "Rec", "Yds", "TD",
               "Tgt sh", "Air sh", "RZ tgt", "EZ tgt"]

        def cells(w):
            return [fmt(w.get("snap_pct"), "pct100"), fmt(w.get("route_pct"), "pct"), fmt(w.get("targets"), "int"),
                    fmt(w.get("rec"), "int"), fmt(w.get("rec_yds"), "int"), fmt(w.get("rec_td"), "int"),
                    fmt(w.get("tgt_share"), "pct"), fmt(w.get("air_share"), "pct"), fmt(w.get("rz_tgt"), "int"),
                    fmt(w.get("ez_tgt"), "int")]
        widths = [0.35, 0.6, 0.5, 0.55, 0.5, 0.5, 0.55, 0.6, 0.4, 0.4, 0.45, 0.35, 0.55, 0.55, 0.5, 0.5]
    elif pos == "RB":
        hdr = ["Wk", "Opp", "Pts", "Finish", "xFP", "+/-", "Snap%", "Car", "Rush yds", "Rush sh", "Tgt", "Rec",
               "Rec yds", "TD", "RZ share", "HVT"]

        def cells(w):
            return [fmt(w.get("snap_pct"), "pct100"), fmt(w.get("carries_official", w.get("carries")), "int"),
                    fmt(w.get("rush_yds"), "int"), fmt(w.get("rush_share"), "pct"), fmt(w.get("targets"), "int"),
                    fmt(w.get("rec"), "int"), fmt(w.get("rec_yds"), "int"),
                    fmt((w.get("rush_td") or 0) + (w.get("rec_td") or 0), "int"), fmt(w.get("rz_share"), "pct"),
                    fmt(w.get("hvt"), "int")]
        widths = [0.35, 0.6, 0.5, 0.55, 0.5, 0.5, 0.55, 0.4, 0.6, 0.6, 0.4, 0.4, 0.6, 0.35, 0.65, 0.4]
    else:
        hdr = ["Wk", "Opp", "Pts", "Finish", "xFP", "+/-", "Cmp/Att", "Pass yds", "TD", "INT", "Sk", "Car",
               "Rush yds", "Rush TD", "EPA/DB"]

        def cells(w):
            return [f"{fmt(w.get('completions'), 'int')}/{fmt(w.get('attempts'), 'int')}",
                    fmt(w.get("pass_yds"), "int"), fmt(w.get("pass_td"), "int"), fmt(w.get("ints"), "int"),
                    fmt(w.get("sacks"), "int"), fmt(w.get("carries_official", w.get("carries")), "int"),
                    fmt(w.get("rush_yds"), "int"), fmt(w.get("rush_td"), "int"), fmt(w.get("epa_db"), "dec2s")]
        widths = [0.35, 0.6, 0.5, 0.55, 0.5, 0.5, 0.7, 0.65, 0.35, 0.4, 0.35, 0.4, 0.65, 0.6, 0.6]
    rows, ex = [hdr], [("ALIGN", (2, 0), (-1, -1), "CENTER")]
    for w in rep["weekly"]:
        i = len(rows)
        if w.get("status"):
            rows.append([w["week"], w["status"]] + [""] * (len(hdr) - 2))
            ex += [("SPAN", (1, i), (-1, i)), ("TEXTCOLOR", (0, i), (-1, i), MUTED),
                   ("FONT", (1, i), (1, i), "Helvetica-Oblique", 7.8), ("ALIGN", (1, i), (1, i), "LEFT")]
            continue
        fin = f"{pos}{w['rank']}" if w.get("rank") else "–"
        rows.append([w["week"], w.get("opp", ""), fmt(w.get("pts"), "dec1"), fin, fmt(w.get("xfp"), "dec1"),
                     fmt(w.get("fpoe"), "dec1s")] + cells(w))
        ex += [("TEXTCOLOR", (3, i), (3, i), tier_color(w.get("rank"))), ("FONT", (2, i), (3, i), "Helvetica-Bold", 7.8)]
        if w.get("fpoe") is not None:
            ex.append(("TEXTCOLOR", (5, i), (5, i), GOOD if w["fpoe"] >= 0 else POOR))
    S_.append(mk(rows, widths, CW, font=7.8, extra=ex))
    S_.append(Spacer(1, 4))
    S_.append(Paragraph("Finish = positional rank that week (green top 12, blue 13-24, gold 25-36). "
                        "xFP = expected fantasy points from his usage; +/- = actual minus expected. "
                        "Route% = share of team dropbacks he was on the field for. HVT = high-value touches "
                        "(targets + carries inside the 10).", NOTE))
    S_.append(Spacer(1, 10))

    played = [w for w in rep["weekly"] if not w.get("status")]
    labels = [f"W{w['week']}" for w in played]
    if pos in ("WR", "TE"):
        series = [("Snap share", DARK, [(w.get("snap_pct") or 0) / 100 if w.get("snap_pct") is not None else None
                                         for w in played]),
                  ("Route participation", BLUE, [w.get("route_pct") for w in played]),
                  ("Target share", ACCENT, [w.get("tgt_share") for w in played]),
                  ("Air yards share", GOOD, [w.get("air_share") for w in played])]
    elif pos == "RB":
        series = [("Snap share", DARK, [(w.get("snap_pct") or 0) / 100 if w.get("snap_pct") is not None else None
                                         for w in played]),
                  ("Rush share", ACCENT, [w.get("rush_share") for w in played]),
                  ("Target share", BLUE, [w.get("tgt_share") for w in played]),
                  ("Red-zone share", GOOD, [w.get("rz_share") for w in played])]
    else:
        series = None
    usage_chart = (LineChart(labels, series, CW * 0.55, 150) if series and played else
                   LineChart(labels, [("Fantasy points", ACCENT, [w.get("pts") for w in played]),
                                      ("Expected", DARK, [w.get("xfp") for w in played])], CW * 0.55, 150, pct=False))
    trows = [["Trend", "Season", "Last 3", "Change"]]
    tex = [("ALIGN", (1, 0), (-1, -1), "CENTER")]
    for i, t in enumerate(rep["trends"], 1):
        kind = t["kind"]
        if kind == "pct":
            d = f"{t['delta'] * 100:+.1f} pts"
        elif kind == "pct100":
            d = f"{t['delta']:+.1f} pts"
        else:
            d = fmt(t["delta"], "dec1s")
        trows.append([t["label"], fmt(t["season"], kind), fmt(t["last3"], kind), d])
        if abs(t["delta"]) >= t["thr"]:
            tex.append(("TEXTCOLOR", (3, i), (3, i), GOOD if t["delta"] > 0 else POOR))
            tex.append(("FONT", (3, i), (3, i), "Helvetica-Bold", 8))
    trend_t = mk(trows, [2.0, 0.8, 0.8, 0.9], CW - CW * 0.55 - 14, font=8, extra=tex) if len(trows) > 1 else \
        Paragraph("Trends appear after 4 games.", NOTE)
    S_.append(KeepTogether([Paragraph("Usage trends", H2), side_by_side(usage_chart, trend_t, CW * 0.55)]))
    S_.append(PageBreak())

    # ============ Page 3: matchup, schedule, team context ============
    S_.append(Paragraph("Matchups and schedule", H2))
    sched = rep["sched"]
    tc = rep["team_ctx"] or {}
    n_t = rep["n_teams"] or 32
    left_parts = []
    if sched and sched["next"]:
        nx = sched["next"]
        when = " ".join(str(x) for x in [nx.get("gameday"), nx.get("gametime")] if x)
        line = (f"{rep['team']} {nx['team_spread']:+.1f}" if nx.get("team_spread") is not None else "–")
        rows = [[f"Next game: week {nx['week']} {nx['label']}", ""],
                ["Kickoff", when or "–"],
                ["Point spread", line],
                ["Game total", fmt(nx.get("total"), "dec1")],
                ["Implied team total", fmt(nx.get("implied"), "dec1")],
                [f"{nx['opp']} vs {pos}s (points allowed / game)",
                 f"{fmt(nx.get('fpa_avg'), 'dec1')}  (league avg {fmt(rep['fpa_avg'], 'dec1')})"],
                [f"{nx['opp']} rank vs {pos}s", f"{ordinal(nx['fpa_rank'])} most allowed of {nx['fpa_n']}"
                 if nx.get("fpa_rank") else "–"]]
        ex = [("SPAN", (0, 0), (-1, 0)), ("ALIGN", (1, 1), (1, -1), "RIGHT")]
        if nx.get("fpa_rank"):
            col = GOODBG if nx["fpa_rank"] <= 8 else POORBG if nx["fpa_rank"] >= nx["fpa_n"] - 7 else None
            if col:
                ex.append(("BACKGROUND", (0, 6), (-1, 6), col))
        left_parts.append(mk(rows, [2.2, 1.6], CW * 0.42, font=8.2, extra=ex))
    else:
        left_parts.append(Paragraph("No upcoming games on the schedule.", BODY))
    left_parts.append(Spacer(1, 10))
    ctx_rows = [[f"{rep['team']} offense", "Value", "NFL rank"]]
    for key, lab, kind in [("ppg", "Points per game", "dec1"), ("plays_pg", "Plays per game (pace)", "dec1"),
                           ("pass_rate", "Dropback rate", "pct"), ("proe", "Pass rate over expected (neutral)", "pct1s"),
                           ("rz_plays_pg", "Red-zone plays per game", "dec1")]:
        r = tc.get(key + "_rank")
        ctx_rows.append([lab, fmt(tc.get(key), kind), f"{ordinal(r)} of {n_t}" if r else "–"])
    left_parts.append(mk(ctx_rows, [2.2, 0.8, 0.8], CW * 0.42, font=8.2, extra=[("ALIGN", (1, 0), (-1, -1), "CENTER")]))
    if sched:
        up = sched["upcoming"]
        srows = [["Wk", "Opponent", "Date", "Line", "Implied", f"Opp rank vs {pos}", "Pts allowed", "Matchup"]]
        sex = [("ALIGN", (2, 0), (-1, -1), "CENTER")]
        items = [("game", u["week"], u) for u in up] + [("bye", w, None) for w in sched["byes"] if w > rep["last_week"]]
        for kind_, wk_, u in sorted(items, key=lambda x: x[1]):
            if kind_ == "bye":
                srows.append([str(wk_), "BYE", "", "", "", "", "", ""])
                sex.append(("TEXTCOLOR", (0, len(srows) - 1), (-1, len(srows) - 1), MUTED))
                continue
            i = len(srows)
            r = u.get("fpa_rank")
            n = u.get("fpa_n") or n_t
            if r:
                lab = "Great" if r <= 6 else "Good" if r <= 12 else "Tough" if r >= n - 5 else "Below avg" \
                    if r >= n - 11 else "Neutral"
            else:
                lab = "–"
            srows.append([f"{u['week']}{' *' if u['playoff'] else ''}", u["label"], str(u.get("gameday") or "–"),
                          f"{u['team_spread']:+.1f}" if u.get("team_spread") is not None else "–",
                          fmt(u.get("implied"), "dec1"), ordinal(r) if r else "–", fmt(u.get("fpa_avg"), "dec1"), lab])
            if r and (r <= 12 or r >= n - 11):
                sex.append(("BACKGROUND", (5, i), (7, i), GOODBG if r <= 12 else POORBG))
            if u["playoff"]:
                sex.append(("FONT", (0, i), (1, i), "Helvetica-Bold", 8))
        right = [Paragraph(f"Rest of season <font size=8 color='#6b7280'>· * = fantasy playoffs "
                           f"(weeks {FANTASY_PLAYOFF_WEEKS[0]}-{FANTASY_PLAYOFF_WEEKS[-1]})</font>", H3), Spacer(1, 4)]
        right.append(mk(srows, [0.4, 0.8, 0.85, 0.55, 0.6, 1.0, 0.75, 0.75], CW - CW * 0.42 - 16, font=8, extra=sex)
                     if len(srows) > 1 else Paragraph("Regular season complete.", BODY))
        right.append(Spacer(1, 4))
        avg_bits = []
        if sched["ros_avg_rank"]:
            avg_bits.append(f"rest-of-season opponents average a {sched['ros_avg_rank']:.1f} rank")
        if sched["playoff_avg_rank"]:
            avg_bits.append(f"fantasy playoff opponents average {sched['playoff_avg_rank']:.1f}")
        right.append(Paragraph("Opponent rank = where that defense ranks in fantasy points allowed to "
                               f"{pos}s (1st = most allowed = best matchup). " +
                               ("; ".join(avg_bits).capitalize() + "." if avg_bits else ""), NOTE))
        t = Table([[left_parts, right]], colWidths=[CW * 0.42 + 16, CW - CW * 0.42 - 16])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (0, -1), 16), ("RIGHTPADDING", (1, 0), (1, -1), 0)]))
        S_.append(t)
    else:
        S_ += left_parts
    S_.append(PageBreak())

    # ============ Page 4: league context ============
    S_.append(Paragraph(f"League context <font size=8.5 color='#6b7280'>· vs {rep['pool_n']} {pos}s with "
                        f"{rep['min_games']}+ games and real volume</font>", H2))

    def rank_table(title, items, width):
        rr = [[title, "Value", "Rank", "Percentile"]]
        for r in items:
            rr.append([Paragraph(esc(r["label"]), CELL), r["value"],
                       f"{r['rank']} / {r['n']}" if r["rank"] else "–", PctBar(r["pct"], r["higher"], width * 0.25)])
        return mk(rr, [0.47, 0.14, 0.13, 0.26], width, font=7.9)
    lw = (CW - 16) * 0.58
    left = rank_table("Production, usage & efficiency", rep["ranks"], lw)
    right = rank_table("Next Gen Stats (player tracking)", rep["ngs"], CW - 16 - lw) if rep["ngs"] else \
        Paragraph("Next Gen Stats not available for him yet (the NFL publishes them for qualified players).", NOTE)
    S_.append(side_by_side(left, right, lw, 16))
    S_.append(Spacer(1, 6))
    S_.append(Paragraph("Percentile bars: green = top third, gold = middle, red = bottom third, blue = style metric "
                        "(neither good nor bad). For drop, stuff, sack and INT rates, lower ranks better. "
                        "WOPR = 1.5 x target share + 0.7 x air yards share, the best single predictor of WR/TE "
                        "fantasy output. Yards per route run and targets per route run use participation data "
                        "(routes approximated by pass plays he was on the field for).", NOTE))
    if rep["notes"]:
        S_.append(Spacer(1, 4))
        S_.append(Paragraph("Data notes: " + " ".join(esc(n) for n in rep["notes"]), NOTE))
    S_.append(PageBreak())

    # ============ Page 5: splits + mistakes ============
    S_.append(Paragraph("Splits", H2))

    def split_table(title, cols, items, width):
        rr = [[title] + [c[0] for c in cols]]
        for lab, st in items:
            row = [lab]
            for _, key, kind in cols:
                if key == "drops" and not st.get("charted"):
                    row.append("–")
                else:
                    row.append(fmt(st.get(key), kind))
            rr.append(row)
        return mk(rr, [1.6] + [0.55] * len(cols), width, font=7.6, extra=[("ALIGN", (1, 0), (-1, -1), "CENTER")])
    half = (CW - 14) / 2
    tabs = [split_table(t, c, it, half) for t, c, it in rep["splits"]]
    for i in range(0, len(tabs), 2):
        S_.append(side_by_side(tabs[i], tabs[i + 1] if i + 1 < len(tabs) else "", half))
        S_.append(Spacer(1, 9))

    mistakes = [l for l in rep["log"] if l["_drop"] or l["_bad"]]
    if mistakes:
        block = [Paragraph("Drops, turnovers and penalties", H2)]
        rr = [["Wk", "Opp", "Q", "Time", "Down", "Spot", "Type", "Air", "EPA", "Play"]]
        ex = [("VALIGN", (0, 0), (-1, -1), "TOP")]
        for i, l in enumerate(mistakes, 1):
            dd = f"{ordinal(l['down'])} & {int(l['ydstogo'])}" if l["down"] else "–"
            typ = "DROP" if l["_drop"] else ("INT-worthy" if "INT-worthy" in l["flags"] else
                                             "Penalty" if "penalty" in l["flags"] and not l["type"].startswith("INT")
                                             else "Fumble lost" if "fumble lost" in l["flags"] else l["type"])
            desc = esc(l["desc"])
            if rep["short"]:
                desc = desc.replace(esc(rep["short"]), f"<b>{esc(rep['short'])}</b>")
            rr.append([l["week"], l["opp"], f"Q{int(l['qtr'])}" if l["qtr"] else "", l["time"] or "", dd,
                       l["yrdln"] or "", typ, "" if l["air_yards"] is None else int(l["air_yards"]),
                       "" if l["epa"] is None else f"{l['epa']:+.2f}", Paragraph(desc, CELL)])
            ex.append(("BACKGROUND", (0, i), (-1, i), DROPBG if l["_drop"] else BADBG))
        block.append(mk(rr, [0.35, 0.5, 0.35, 0.5, 0.7, 0.6, 0.75, 0.35, 0.5, 5.0], CW, font=7.8, zebra=False,
                        extra=ex))
        S_.append(KeepTogether(block) if len(mistakes) <= 12 else block[0])
        if len(mistakes) > 12:
            S_.append(block[1])
    S_.append(PageBreak())

    # ============ Play log ============
    S_.append(Paragraph("Play log", H2))
    S_.append(Paragraph("Shading: <font color='#b7791f'><b>gold</b></font> = touchdown, "
                        "<font color='#c05621'><b>orange</b></font> = charted drop, <font color='#c53030'><b>red</b>"
                        "</font> = interception, INT-worthy throw, fumble lost or penalty on him.", NOTE))
    S_.append(Spacer(1, 6))
    pcw = [0.35, 0.5, 0.75, 0.6, 0.8, 0.55, 0.4, 0.4, 0.5, 4.9]
    by_week = defaultdict(list)
    for l in rep["log"]:
        by_week[l["week"]].append(l)
    wk_info = {w["week"]: w for w in rep["weekly"]}
    for wk in sorted(by_week):
        logs = by_week[wk]
        w = wk_info.get(wk, {})
        bits = []
        if w.get("pts") is not None:
            bits.append(f"{w['pts']:.1f} pts")
        if w.get("rank"):
            bits.append(f"{pos}{w['rank']}")
        if w.get("snap_pct") is not None:
            bits.append(f"{w['snap_pct']:.0f}% snaps")
        head = Paragraph(f"Week {wk} &nbsp;{esc(logs[0]['opp'])} &nbsp;<font size=8.5 color='#6b7280'>"
                         f"{' · '.join(bits)}</font>", H3)
        rr = [["Q", "Time", "Down & Dist", "Spot", "Type", "Result", "Air", "YAC", "EPA", "Play"]]
        ex = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.3), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
              ("BACKGROUND", (0, 0), (-1, 0), colors.white), ("LINEBELOW", (0, 0), (-1, 0), 1, DARK),
              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (5, 0), (8, -1), "RIGHT")]
        for i, l in enumerate(logs, 1):
            dd = f"{ordinal(l['down'])} & {int(l['ydstogo'])}" if l["down"] else "–"
            q = "" if l["qtr"] is None else ("OT" if l["qtr"] >= 5 else f"Q{int(l['qtr'])}")
            desc = esc(l["desc"])
            if rep["short"]:
                desc = desc.replace(esc(rep["short"]), f"<b>{esc(rep['short'])}</b>")
            tags = [t for t in l["flags"].split(", ") if t in ("contested", "PA")]
            if tags:
                desc += f" <font color='#6b7280'>[{', '.join(tags)}]</font>"
            rr.append([q, l["time"] or "", dd, l["yrdln"] or "", l["type"], l["result"],
                       "" if l["air_yards"] is None else int(l["air_yards"]),
                       "" if l["yac"] is None else int(l["yac"]),
                       "" if l["epa"] is None else f"{l['epa']:+.2f}", Paragraph(desc, CELL)])
            if l["_td"]:
                ex.append(("BACKGROUND", (0, i), (-1, i), TDBG))
            elif l["_drop"]:
                ex += [("BACKGROUND", (0, i), (-1, i), DROPBG), ("FONT", (4, i), (4, i), "Helvetica-Bold", 7.6)]
            elif l["_bad"]:
                ex.append(("BACKGROUND", (0, i), (-1, i), BADBG))
            if l["type"] in ("Catch", "TD catch", "Completion", "TD pass", "TD run", "Rush"):
                ex.append(("FONT", (4, i), (5, i), "Helvetica-Bold", 7.6))
        t = mk(rr, pcw, CW, font=7.6, zebra=True, extra=ex)
        S_ += [KeepTogether([head, Spacer(1, 3), t]) if len(logs) <= 16 else head]
        if len(logs) > 16:
            S_.append(t)
        S_.append(Spacer(1, 10))

    doc.build(S_)
    return path


# ------------------------------------------------------------------------------------
# Player lookup, folders, main loop
# ------------------------------------------------------------------------------------

def find_player(S, query):
    """Return a player id, or None. Handles typos and asks when several players match."""
    q = query.strip().lower()
    active = set(S.season_tot) | set(S.tgt_rows) | set(S.rush_rows) | set(S.db_rows)
    cands = {pid: S.players[pid] for pid in active if pid in S.players
             and (S.players[pid].get("pos") in FANTASY_POS or S.season_tot.get(pid, {}).get("pos") in FANTASY_POS)}
    for pid, t in S.season_tot.items():
        if pid not in cands:
            cands[pid] = {"pid": pid, "name": t["name"], "pos": t["pos"], "team": t["team"]}
    exact = [pid for pid, p in cands.items() if (p.get("name") or "").lower() == q]
    if not exact:
        exact = [pid for pid, p in cands.items() if q in (p.get("name") or "").lower()]
    if not exact:
        names = {(p.get("name") or ""): pid for pid, p in cands.items()}
        close = difflib.get_close_matches(query.strip(), list(names), n=5, cutoff=0.6)
        if not close:
            lower = {k.lower(): k for k in names}
            close = [lower[c] for c in difflib.get_close_matches(q, list(lower), n=5, cutoff=0.6)]
        exact = [names[c] for c in close]
    if not exact:
        print(f"No {S.season} QB/RB/WR/TE found matching '{query}'.")
        return None
    if len(exact) == 1:
        return exact[0]
    exact.sort(key=lambda pid: -(S.season_tot.get(pid, {}).get("pts") or 0))
    exact = exact[:8]
    print("Did you mean:")
    for i, pid in enumerate(exact, 1):
        p = cands[pid]
        t = S.season_tot.get(pid, {})
        print(f"  {i}. {p.get('name')} ({p.get('pos') or t.get('pos')}, {t.get('team') or p.get('team')})"
              f"{'  ' + format(t['ppg'], '.1f') + ' PPG' if t.get('ppg') else ''}")
    while True:
        a = ask("Pick a number (or press Enter to search again): ")
        if not a:
            return None
        if a.isdigit() and 1 <= int(a) <= len(exact):
            return exact[int(a) - 1]


def tidy_loose_files(root):
    """Move report files left loose in the script folder into their player's folder."""
    pat = re.compile(r"^([a-z0-9_]+?)_(\d{4})_(plays|games|weekly|metrics|report|drops)\.(csv|pdf)$")
    for f in root.iterdir():
        mm = pat.match(f.name) if f.is_file() else None
        if not mm:
            continue
        folder = root / " ".join(w.capitalize() for w in mm.group(1).split("_"))
        folder.mkdir(exist_ok=True)
        try:
            f.replace(folder / f.name)
            print(f"Moved {f.name} into {folder.name}/")
        except OSError as e:
            print(f"Couldn't move {f.name} ({e}). Is it open in another program?")


def ask(prompt, default=""):
    try:
        v = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return v or default


def run_player(S, pid, root, pdf_choice, open_pdf=False):
    t0 = time.time()
    rep = build_report(S, pid)
    print_summary(rep)
    folder = root / (re.sub(r'[<>:"/\\|?*]', "", rep["name"]).strip() or "Unknown Player")
    folder.mkdir(parents=True, exist_ok=True)
    base = str(folder / f"{slug(rep['name'])}_{S.season}")
    for old in ("games", "drops"):  # files from older versions of this script
        Path(f"{base}_{old}.csv").unlink(missing_ok=True)
    try:
        write_csvs(rep, base)
    except PermissionError:
        print("Couldn't write the CSVs. Close them in Excel and try again.")
        return
    print(f"\nSaved CSVs to {folder}  ({time.time() - t0:.1f}s)")
    if pdf_choice is not False:
        try:
            out = build_pdf(rep, f"{base}_report.pdf")
            print(f"Saved {Path(out).name}")
            if open_pdf and hasattr(os, "startfile"):
                os.startfile(out)  # opens in your default PDF viewer (Windows)
        except PermissionError:
            print("Couldn't save the PDF. Close it if it's open in a PDF viewer and try again.")
        except ImportError:
            print("The PDF needs reportlab. Run:  pip install reportlab")


def main():
    ap = argparse.ArgumentParser(description="Fantasy-focused NFL player reports.")
    ap.add_argument("--name", help='Player name, e.g. "Matthew Golden"')
    ap.add_argument("--season", type=int, default=SEASON)
    ap.add_argument("--scoring", choices=["standard", "half", "ppr"], default=SCORING_FORMAT)
    pdf = ap.add_mutually_exclusive_group()
    pdf.add_argument("--pdf", action="store_true", help="Save the PDF (the default)")
    pdf.add_argument("--no-pdf", action="store_true", help="Skip the PDF")
    ap.add_argument("--no-open", action="store_true", help="Don't open the PDF after saving it")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    tidy_loose_files(root)

    sc = dict(SCORING)
    if sc.get("rec") is None:
        sc["rec"] = FORMAT_REC[args.scoring]
    S = Season(args.season, sc, args.scoring)
    t0 = time.time()
    try:
        load_season(S)
    except ImportError as e:
        sys.exit(f"Missing library ({e.name}). Run:  pip install nflreadpy polars reportlab")
    except Exception as e:
        sys.exit(f"Couldn't load {args.season} data: {e}\nCheck your internet connection and try again.")
    print(f"Ready in {time.time() - t0:.0f}s. {FORMAT_LABEL[args.scoring]}, through week {S.last_week}.")
    pdf_choice = False if args.no_pdf else True

    query = args.name
    while True:
        while not query:
            query = ask("\nEnter player name (or q to quit): ")
            if not query:
                print("Please type a player name.")
        if query.lower() in ("q", "quit", "exit"):
            break
        pid = find_player(S, query)
        query = None
        if pid:
            try:
                run_player(S, pid, root, pdf_choice, open_pdf=not args.no_open)
            except Exception as e:
                print(f"Something went wrong building that report: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                print("Paste the error above to Claude and it can fix it.")
        if args.name:
            break


if __name__ == "__main__":
    main()
