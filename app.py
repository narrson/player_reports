"""
Fantasy Player Reports: website version.

Run on your computer:   streamlit run app.py
Hosted on:              Streamlit Community Cloud (files: app.py, player_report.py, requirements.txt,
                        .streamlit/config.toml)

All the stats come from player_report.py, which must sit in the same folder.
"""

import base64
import difflib
import hashlib
import hmac
import html
import re
import os
import secrets as pysecrets
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import player_report as pr

st.set_page_config(page_title="Fantasy Player Reports", page_icon="🏈", layout="wide",
                   initial_sidebar_state="collapsed")

# ------------------------------------------------------------------------------------
# Design system
# ------------------------------------------------------------------------------------

BG, CARD, CARD2, BORDER = "#0b1220", "#121a2b", "#172238", "#22304a"
TEXT, MUTED, DIM = "#e6edf3", "#8b98ad", "#5d6b82"
GOLD, GREEN, BLUE, AMBER, RED, SLATE = "#f5b301", "#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#64748b"
G_BG, R_BG = "rgba(34,197,94,.16)", "rgba(239,68,68,.16)"

TEAM_COLORS = {
    "ARI": ("#97233F", "#FFB612"), "ATL": ("#A71930", "#A5ACAF"), "BAL": ("#241773", "#9E7C0C"),
    "BUF": ("#00338D", "#C60C30"), "CAR": ("#0085CA", "#BFC0BF"), "CHI": ("#0B162A", "#C83803"),
    "CIN": ("#FB4F14", "#000000"), "CLE": ("#311D00", "#FF3C00"), "DAL": ("#003594", "#869397"),
    "DEN": ("#FB4F14", "#002244"), "DET": ("#0076B6", "#B0B7BC"), "GB": ("#203731", "#FFB612"),
    "HOU": ("#03202F", "#A71930"), "IND": ("#002C5F", "#A2AAAD"), "JAX": ("#006778", "#D7A22A"),
    "KC": ("#E31837", "#FFB81C"), "LA": ("#003594", "#FFA300"), "LAR": ("#003594", "#FFA300"),
    "LAC": ("#0080C6", "#FFC20E"), "LV": ("#000000", "#A5ACAF"), "MIA": ("#008E97", "#FC4C02"),
    "MIN": ("#4F2683", "#FFC62F"), "NE": ("#002244", "#C60C30"), "NO": ("#101820", "#D3BC8D"),
    "NYG": ("#0B2265", "#A71930"), "NYJ": ("#125740", "#FFFFFF"), "PHI": ("#004C54", "#A5ACAF"),
    "PIT": ("#101820", "#FFB612"), "SEA": ("#002244", "#69BE28"), "SF": ("#AA0000", "#B3995D"),
    "TB": ("#D50A0A", "#FF7900"), "TEN": ("#0C2340", "#4B92DB"), "WAS": ("#5A1414", "#FFB612"),
}

FORMATS = {"Half-PPR": "half", "PPR": "ppr", "Standard": "standard"}
SEASONS = [pr.SEASON, pr.SEASON - 1, pr.SEASON - 2]
VIEWS = ["Home", "Player", "Compare", "My Teams", "Rankings", "Defense"]
VIEW_ICONS = {"Home": "🏠", "Player": "👤", "Compare": "⚖️", "My Teams": "🗂️", "Rankings": "📊", "Defense": "🛡️"}
fmt = pr.fmt
mean, div = pr.mean, pr.div
esc = html.escape

CSS = f"""
<style>
.block-container {{padding-top: 3.6rem; padding-bottom: 3rem; max-width: 1280px;}}
header[data-testid="stHeader"] {{background: rgba(11,18,32,.88); backdrop-filter: blur(8px);}}
.stTabs [data-baseweb="tab-list"] {{gap: .25rem; overflow-x: auto;}}
.stTabs [data-baseweb="tab"] {{font-weight: 600; padding: .35rem .8rem;}}
div[data-testid="stDataFrame"] {{border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden;}}
.fr-title {{font-size: 1.9rem; font-weight: 800; color: {TEXT}; margin: 0; line-height: 1.15;}}
.fr-sub {{color: {MUTED}; font-size: .88rem; margin-top: .2rem;}}
.fr-sec {{font-size: .74rem; text-transform: uppercase; letter-spacing: .09em; color: {MUTED};
         font-weight: 700; margin: 1.3rem 0 .55rem;}}
.fr-card {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; padding: .9rem 1rem;}}
.fr-hero {{border-radius: 18px; padding: 1.2rem 1.4rem; border: 1px solid {BORDER}; display: flex;
          justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: .9rem;}}
.fr-hero .nm {{font-size: 2.1rem; font-weight: 800; color: #fff; line-height: 1.05;}}
.fr-hero .meta {{color: rgba(255,255,255,.78); font-size: .86rem; margin-top: .45rem;}}
.fr-chip {{display: inline-block; padding: .18rem .55rem; border-radius: 999px; font-size: .74rem;
          font-weight: 700; margin: .45rem .3rem 0 0; background: rgba(255,255,255,.12); color: #fff;
          border: 1px solid rgba(255,255,255,.16);}}
.fr-badge {{text-align: center; min-width: 110px; background: rgba(0,0,0,.3); border-radius: 14px;
           padding: .6rem .9rem; border: 1px solid rgba(255,255,255,.14);}}
.fr-badge .big {{font-size: 1.9rem; font-weight: 800; line-height: 1;}}
.fr-badge .lab {{font-size: .68rem; text-transform: uppercase; letter-spacing: .08em; color: rgba(255,255,255,.7);
                margin-top: .3rem;}}
.fr-grid {{display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem;}}
.fr-grid.g3 {{grid-template-columns: repeat(3, minmax(0, 1fr));}}
.fr-grid.g2 {{grid-template-columns: repeat(2, minmax(0, 1fr));}}
.fr-grid.g5 {{grid-template-columns: repeat(5, minmax(0, 1fr));}}
@media (max-width: 900px) {{ .fr-grid, .fr-grid.g3, .fr-grid.g5 {{grid-template-columns: repeat(2, minmax(0, 1fr));}} }}
@media (max-width: 560px) {{ .fr-grid.g2 {{grid-template-columns: 1fr;}} .fr-hero .nm {{font-size: 1.6rem;}}
                            .fr-kpi .v {{font-size: 1.35rem !important;}} }}
.fr-kpi {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; padding: .75rem .9rem .75rem 1rem;
         position: relative; overflow: hidden;}}
.fr-kpi:before {{content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--acc);}}
.fr-kpi .l {{font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: {MUTED}; font-weight: 700;}}
.fr-kpi .v {{font-size: 1.65rem; font-weight: 800; line-height: 1.15; margin-top: .2rem;}}
.fr-kpi .s {{font-size: .78rem; color: {MUTED}; margin-top: .2rem;}}
.fr-pill {{display: inline-block; padding: .08rem .48rem; border-radius: 999px; font-size: .72rem; font-weight: 700;}}
.fr-note {{display: flex; gap: .65rem; align-items: flex-start; background: {CARD}; border: 1px solid {BORDER};
          border-left: 4px solid var(--c); border-radius: 12px; padding: .65rem .8rem; font-size: .9rem;
          color: {TEXT}; line-height: 1.4;}}
.fr-note .ic {{color: var(--c); font-weight: 800; font-size: .95rem; line-height: 1.4;}}
.fr-stats {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; padding: .3rem .9rem;}}
.fr-stats .row {{display: flex; justify-content: space-between; gap: 1rem; padding: .5rem 0;
                border-bottom: 1px solid {BORDER}; font-size: .88rem;}}
.fr-stats .row:last-child {{border-bottom: none;}}
.fr-stats .row span:first-child {{color: {MUTED};}}
.fr-stats .row span:last-child {{color: {TEXT}; font-weight: 700; text-align: right;}}
.fr-rank {{display: grid; grid-template-columns: minmax(0, 2.2fr) .8fr .8fr minmax(70px, 1.6fr); gap: .6rem;
          align-items: center; padding: .48rem .9rem; border-bottom: 1px solid {BORDER}; font-size: .86rem; color: {TEXT};}}
.fr-rank.h {{font-size: .68rem; text-transform: uppercase; letter-spacing: .08em; color: {MUTED}; font-weight: 700;}}
.fr-rank:last-child {{border-bottom: none;}}
.fr-rank .val {{font-weight: 700; text-align: right;}}
.fr-rank .rk {{color: {MUTED}; text-align: right;}}
.fr-bar {{height: 8px; background: {BORDER}; border-radius: 6px; overflow: hidden;}}
.fr-bar > span {{display: block; height: 100%; border-radius: 6px;}}
.fr-sched {{display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: .5rem;}}
.fr-wk {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: .55rem .4rem;
        text-align: center; border-top: 4px solid var(--c);}}
.fr-wk .w {{font-size: .66rem; color: {MUTED}; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;}}
.fr-wk .o {{font-size: .98rem; font-weight: 800; color: {TEXT}; margin: .15rem 0;}}
.fr-wk .r {{font-size: .72rem; font-weight: 700; color: var(--c);}}
.fr-game {{border-radius: 16px; padding: 1rem 1.2rem; border: 1px solid {BORDER}; background: {CARD};}}
.fr-game .teams {{display: flex; align-items: center; gap: .7rem; flex-wrap: wrap;}}
.fr-tm {{display: inline-block; padding: .2rem .6rem; border-radius: 9px; color: #fff; font-weight: 800;
        font-size: 1.05rem; border-bottom: 3px solid var(--s);}}
.fr-list .it {{display: flex; justify-content: space-between; align-items: center; gap: .6rem; padding: .48rem 0;
              border-bottom: 1px solid {BORDER}; font-size: .88rem;}}
.fr-list .it:last-child {{border-bottom: none;}}
.fr-list a {{color: {TEXT} !important; text-decoration: none !important; font-weight: 700;}}
.fr-list a:hover {{color: {GOLD} !important;}}
.fr-list .sm {{color: {MUTED}; font-size: .76rem; font-weight: 500;}}
.fr-list .num {{font-weight: 800; white-space: nowrap;}}
.fr-cardh {{font-size: .74rem; text-transform: uppercase; letter-spacing: .09em; font-weight: 800; margin-bottom: .2rem;}}
.fr-cardd {{font-size: .78rem; color: {MUTED}; margin-bottom: .35rem;}}
.fr-glgrid {{display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: .5rem;}}
.fr-gl {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: .55rem .75rem; font-size: .8rem;
        color: {MUTED}; line-height: 1.4;}}
.fr-gl b {{color: {TEXT}; display: block; font-size: .82rem; margin-bottom: .1rem;}}
.fr-wk img {{display: block; margin: .25rem auto .1rem;}}
.fr-foot {{color: {DIM}; font-size: .76rem; margin-top: 2.2rem; text-align: center; line-height: 1.6;}}
</style>
"""


def H(s):
    """Render an HTML snippet. Lines are stripped so Markdown never treats them as a code block."""
    st.markdown("\n".join(line.strip() for line in s.strip().splitlines() if line.strip()), unsafe_allow_html=True)


def sec(title):
    H(f'<div class="fr-sec">{esc(title)}</div>')


def tier_color(rank):
    if not rank:
        return SLATE
    return GREEN if rank <= 12 else BLUE if rank <= 24 else AMBER if rank <= 36 else SLATE


def pct_color(p, higher=True):
    if p is None:
        return SLATE
    if higher is None:
        return BLUE
    return GREEN if p >= 67 else AMBER if p >= 33 else RED


def matchup_info(rank, n):
    if not rank:
        return "–", SLATE
    n = n or 32
    if rank <= 6:
        return "Great", GREEN
    if rank <= 12:
        return "Good", "#86efac"
    if rank >= n - 5:
        return "Tough", RED
    if rank >= n - 11:
        return "Below avg", "#fca5a5"
    return "Neutral", MUTED


def team_cols(team):
    return TEAM_COLORS.get(team or "", ("#1e293b", GOLD))


ESPN_ABBR = {"WAS": "wsh", "LA": "lar", "LAR": "lar"}


def logo_url(team):
    if not team:
        return None
    t = str(team).upper()
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{ESPN_ABBR.get(t, t.lower())}.png"


def logo(team, size=20, style=""):
    u = logo_url(team)
    return (f'<img src="{u}" alt="" style="width:{size}px;height:{size}px;object-fit:contain;'
            f'vertical-align:middle;{style}">') if u else ""


GLOSSARY = {
    "PPG": "Fantasy points per game.",
    "Total pts": "Fantasy points for the whole season.",
    "xFP": "Expected fantasy points: what an average player would score with the same targets, carries, "
           "depth of target and field position. The most stable measure of opportunity.",
    "+/- exp": "Points over expected per game: actual points minus xFP. Positive = scoring more than his usage predicts.",
    "TD luck": "The part of +/- exp that comes from scoring more (or fewer) touchdowns than his usage predicts. "
               "This is the part that tends to even out, so it drives the buy-low / sell-high lists.",
    "Finish": "Where he ranked at his position that week (WR12 = 12th-best WR).",
    "Snap %": "Share of his team's offensive plays he was on the field for.",
    "Route %": "Share of his team's pass plays he was on the field for (how often he runs a route).",
    "Target share": "Share of his team's targets that went to him.",
    "Air yards share": "Share of his team's air yards (how far passes travel past the line) thrown his way.",
    "WOPR": "Weighted opportunity rating: 1.5 × target share + 0.7 × air yards share. "
            "The best single predictor of receiver fantasy output.",
    "YPRR": "Yards per route run. The best efficiency stat for receivers.",
    "TPRR": "Targets per route run: how often he's thrown to when he runs a route.",
    "aDOT": "Average depth of target: how far downfield his targets travel. A style stat, not good or bad.",
    "Drop %": "Charted drops divided by catchable targets.",
    "RZ": "Red zone: inside the opponent's 20-yard line.",
    "EZ tgt": "End-zone targets: passes thrown into the end zone to him.",
    "Opportunities/G": "Carries plus targets per game.",
    "Rush share": "Share of his team's carries.",
    "HVT": "High-value touches: targets plus carries inside the 10. These score the most fantasy points.",
    "Inside-10 share": "Share of his team's carries inside the opponent's 10-yard line (goal-line role).",
    "YPC": "Yards per carry.",
    "EPA": "Expected points added: how much a play changed his team's expected scoring. Above 0 is good.",
    "Stuff %": "Share of carries stopped at or behind the line of scrimmage.",
    "Dropbacks/G": "Pass plays per game, including sacks and scrambles.",
    "EPA/dropback": "Expected points added per pass play. The best single QB efficiency stat.",
    "CPOE": "Completion percentage over expected, based on how difficult each throw was.",
    "ANY/A": "Adjusted net yards per attempt: passing yards with bonuses for TDs and penalties for INTs and sacks.",
    "Sack %": "Share of dropbacks that end in a sack.",
    "INT %": "Share of pass attempts intercepted.",
    "Implied total": "Points Vegas expects his team to score, from the spread and the game total.",
    "Spread": "Vegas point spread for his team. Negative = favored.",
    "Defense rank": "Where a defense ranks in fantasy points allowed to a position. "
                    "1 = allows the most = best matchup for your player.",
    "PROE": "Pass rate over expected: how much more (or less) a team passes than normal in neutral game situations.",
    "Boom / bust": "Boom = a big week (20+ for RB/WR, 25+ QB, 15+ TE). Bust = under 8 (12 QB, 6 TE).",
    "Floor / ceiling": "A bad week and a good week for him (roughly his 20th-25th and 75th-80th percentile scores).",
    "ROS": "Rest of season: projected points from now through the fantasy playoffs, with matchups and byes included.",
    "Projection": "Usage (expected points, weighted toward the last 3 games) plus half of his efficiency edge, "
                  "adjusted for the opponent, the Vegas team total and the injury report.",
}
POS_TERMS = {
    "WR": ["Target share", "Air yards share", "WOPR", "Route %", "YPRR", "TPRR", "aDOT", "Drop %"],
    "TE": ["Target share", "Air yards share", "WOPR", "Route %", "YPRR", "TPRR", "aDOT", "Drop %"],
    "RB": ["Opportunities/G", "Rush share", "HVT", "Inside-10 share", "Target share", "YPC", "EPA", "Stuff %"],
    "QB": ["Dropbacks/G", "EPA/dropback", "CPOE", "ANY/A", "Sack %", "INT %"],
}


def glossary(terms, title="What the abbreviations mean"):
    items = "".join(f'<div class="fr-gl"><b>{esc(t)}</b><span>{esc(GLOSSARY[t])}</span></div>'
                    for t in terms if t in GLOSSARY)
    H(f'<div class="fr-sec" style="margin-top:2rem">{esc(title)}</div><div class="fr-glgrid">{items}</div>')


def plink(pid, text):
    q = {k: v for k, v in st.query_params.items() if k in ("season", "scoring")}
    q["player"] = pid
    return f'<a href="?{urlencode(q)}" target="_self">{esc(text)}</a>'


def smap(sty, fn, subset):
    return sty.map(fn, subset=subset) if hasattr(sty, "map") else sty.applymap(fn, subset=subset)


def styled_df(df, row_bg=None, cell=None, height=None, **kw):
    """Dataframe with optional per-row backgrounds and per-cell text colours."""
    sty = df.style
    if row_bg is not None:
        sty = sty.apply(lambda r: [f"background-color: {row_bg(r)}" if row_bg(r) else "" for _ in r], axis=1)
    for col, fn in (cell or {}).items():
        if col in df.columns:
            sty = smap(sty, (lambda f_: (lambda v: f"color: {f_(v)}; font-weight: 700" if f_(v) else ""))(fn), [col])
    sty = sty.format(precision=1, na_rep="")
    args = dict(use_container_width=True, hide_index=True, **kw)
    if height:
        args["height"] = height
    return st.dataframe(sty, **args)


# ------------------------------------------------------------------------------------
# Data (cached on the server, shared by every visit)
# ------------------------------------------------------------------------------------

@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=2, show_spinner=False)
def get_season(season, scoring):
    sc = dict(pr.SCORING)
    if sc.get("rec") is None:
        sc["rec"] = pr.FORMAT_REC[scoring]
    S = pr.Season(season, sc, scoring)
    pr.load_season(S)
    S.loaded_at = datetime.now()
    return S


def skey(S, *extra):
    return (S.season, S.fmt_name, S.loaded_at) + extra


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=300, show_spinner=False)
def get_report(_S, key):
    return pr.build_report(_S, key[-1])


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def get_player_list(_S, key):
    rows = sorted(_S.season_tot.items(), key=lambda kv: -kv[1]["pts"])
    labels = {pid: f"{t['name']}  ·  {t['pos']}  ·  {t['team']}  ·  {t['ppg']:.1f} PPG" for pid, t in rows}
    return [pid for pid, _ in rows], labels


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def get_home(_S, key):
    S = _S
    out = {"luck": [], "trend": [], "week_top": {}, "season_top": {}, "matchups": {}, "next_week": None}
    for pos in pr.FANTASY_POS:
        pool, _ = pr.position_pool(S, pos)
        for pid, m in pool.items():
            t = S.season_tot[pid]
            base = {"pid": pid, "name": t["name"], "pos": pos, "team": t["team"], "ppg": m["ppg"]}
            if m.get("regress_pg") is not None and (m.get("xfp_pg") or 0) >= 7 and m.get("xfp_games", 0) >= 4:
                out["luck"].append({**base, "val": m["regress_pg"], "td_oe": m["td_oe_pg"], "xfp": m["xfp_pg"],
                                    "act_td": m["act_td_xweeks"] + (m["act_pass_td_xweeks"] if pos == "QB" else 0),
                                    "exp_td": (m["exp_td"] or 0) + ((m["exp_pass_td"] or 0) if pos == "QB" else 0)})
            weeks = pr.player_weeks(S, pid)
            if len(weeks) >= 4 and m.get("xfp_pg") is not None:
                l3 = pr.player_metrics(S, pid, pos, weeks[-3:])
                if l3.get("xfp_pg") is not None:
                    out["trend"].append({**base, "val": l3["xfp_pg"] - m["xfp_pg"], "l3": l3["xfp_pg"],
                                         "season": m["xfp_pg"]})
        out["week_top"][pos] = sorted([r for rs in S.weekly.values() for r in rs
                                       if r["week"] == S.last_week and r["pos"] == pos], key=lambda r: -r["pts"])[:5]
        out["season_top"][pos] = sorted([(pid, t) for pid, t in S.season_tot.items() if t["pos"] == pos],
                                        key=lambda x: -x[1]["pts"])[:5]
    upcoming = sorted({g["week"] for g in S.schedule if g["home_score"] is None})
    if upcoming:
        nw = upcoming[0]
        out["next_week"] = nw
        games = [g for g in S.schedule if g["week"] == nw]
        for pos in pr.FANTASY_POS:
            lst = []
            for gm in games:
                for off, de in ((gm["home"], gm["away"]), (gm["away"], gm["home"])):
                    f = S.fpa.get((de, pos))
                    if f:
                        lst.append({"off": off, "def": de, "rank": f["rank"], "n": f["n"], "avg": f["avg"]})
            out["matchups"][pos] = sorted(lst, key=lambda x: x["rank"])[:5]
    return out


# ------------------------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------------------------

def base_layout(fig, height):
    fig.update_layout(height=height, margin=dict(l=6, r=6, t=40, b=6), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#c9d4e3", size=12),
                      legend=dict(orientation="h", y=1.16, x=0, font=dict(size=11)),
                      hoverlabel=dict(bgcolor=CARD2, bordercolor=BORDER, font=dict(color=TEXT)))
    fig.update_xaxes(showgrid=False, linecolor=BORDER, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="rgba(139,152,173,.14)", zeroline=False, tickfont=dict(color=MUTED))
    return fig


def points_chart(rep):
    wk = rep["weekly"]
    x = [f"W{w['week']}" for w in wk]
    y = [0 if w.get("status") else (w.get("pts") or 0) for w in wk]
    text = [("BYE" if w["status"] == "BYE" else "OUT") if w.get("status") else f"{w.get('pts') or 0:.1f}" for w in wk]
    hover = [w.get("status") or (f"<b>{esc(w.get('opp', ''))}</b><br>{w.get('pts') or 0:.1f} pts"
                                 f"{' · ' + rep['pos'] + str(w['rank']) if w.get('rank') else ''}"
                                 f"{'<br>xFP ' + format(w['xfp'], '.1f') if w.get('xfp') is not None else ''}")
             for w in wk]
    fig = go.Figure()
    fig.add_bar(x=x, y=y, marker=dict(color=[tier_color(w.get("rank")) for w in wk], line=dict(width=0)),
                text=text, textposition="outside", cliponaxis=False, name="Fantasy points",
                textfont=dict(color=TEXT, size=11), hovertext=hover, hoverinfo="text")
    xs = [w.get("xfp") if not w.get("status") else None for w in wk]
    if any(v is not None for v in xs):
        fig.add_scatter(x=x, y=xs, mode="markers", name="Expected (xFP)", hoverinfo="skip",
                        marker=dict(symbol="line-ew", size=26, line=dict(width=3, color="#f8fafc")))
    if rep["prof"]["ppg"]:
        fig.add_hline(y=rep["prof"]["ppg"], line_dash="dot", line_color=GOLD, line_width=1.5,
                      annotation_text=f"avg {rep['prof']['ppg']:.1f}", annotation_position="top left",
                      annotation_font=dict(color=GOLD, size=11))
    base_layout(fig, 340)
    fig.update_layout(bargap=0.38, showlegend=False)
    fig.update_yaxes(rangemode="tozero")
    return fig


def line_chart(x, series, pct=True, height=300):
    fig = go.Figure()
    for name, col, vals in series:
        fig.add_scatter(x=x, y=vals, mode="lines+markers", name=name,
                        line=dict(color=col, width=2.6, shape="spline", smoothing=0.6), marker=dict(size=7),
                        connectgaps=False, hovertemplate=f"{name}: " + ("%{y:.0%}" if pct else "%{y:.1f}") +
                        "<extra></extra>")
    base_layout(fig, height)
    fig.update_yaxes(rangemode="tozero", tickformat=".0%" if pct else None, range=[0, 1.02] if pct else None)
    return fig


def usage_chart(rep):
    played = [w for w in rep["weekly"] if not w.get("status")]
    x = [f"W{w['week']}" for w in played]
    snap = [(w["snap_pct"] / 100) if w.get("snap_pct") is not None else None for w in played]
    if rep["pos"] in ("WR", "TE"):
        return line_chart(x, [("Snap share", "#94a3b8", snap), ("Routes", BLUE, [w.get("route_pct") for w in played]),
                              ("Target share", GOLD, [w.get("tgt_share") for w in played]),
                              ("Air yards share", GREEN, [w.get("air_share") for w in played])])
    if rep["pos"] == "RB":
        return line_chart(x, [("Snap share", "#94a3b8", snap), ("Rush share", GOLD, [w.get("rush_share") for w in played]),
                              ("Target share", BLUE, [w.get("tgt_share") for w in played]),
                              ("Red-zone share", GREEN, [w.get("rz_share") for w in played])])
    return line_chart(x, [("Fantasy points", GOLD, [w.get("pts") for w in played]),
                          ("Expected (xFP)", "#f8fafc", [w.get("xfp") for w in played]),
                          ("Dropbacks", BLUE, [w.get("dropbacks") for w in played])], pct=False)


def plot(fig):
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ------------------------------------------------------------------------------------
# Player page components
# ------------------------------------------------------------------------------------

def hero(rep):
    b, pos, m = rep["bio"], rep["pos"], rep["m"]
    c1, c2 = team_cols(rep["team"])
    chips = [rep["team"], f"{pos} #{rep['jersey']}" if rep.get("jersey") is not None else pos,
             f"Age {b['age']}" if b.get("age") else None, b.get("exp"),
             pr.FORMAT_LABEL[rep["fmt"]].replace(" scoring", "")]
    chip_html = "".join(f'<span class="fr-chip">{esc(str(c))}</span>' for c in chips if c)
    inj = rep["injury"]
    if inj and inj.get("status"):
        chip_html += (f'<span class="fr-chip" style="background:{R_BG};border-color:{RED};color:#fecaca">'
                      f'🩹 {esc(inj["status"])}{" · " + esc(inj["injury"]) if inj.get("injury") else ""}</span>')
    meta = " · ".join(x for x in [b.get("height"), b.get("weight"), b.get("college"),
                                  f"Drafted {b['draft']}" if b.get("draft") else None] if x)
    rk = m.get("rank_ppg")
    big_logo = logo(rep["team"], 76, "filter:drop-shadow(0 2px 6px rgba(0,0,0,.45))")
    rk_txt = rk if rk else "–"
    H(f"""
    <div class="fr-hero" style="background: linear-gradient(115deg, {c1} 0%, {c1}cc 38%, {CARD} 100%);
         border-left: 6px solid {c2};">
      <div style="display:flex;gap:1rem;align-items:center">
      {big_logo}
      <div>
        <div class="nm">{esc(rep['name'])}</div>
        <div>{chip_html}</div>
        <div class="meta">{esc(meta)}</div>
      </div></div>
      <div class="fr-badge"><div class="big" style="color:{tier_color(rk) if rk else TEXT}">{pos}{rk_txt}</div>
        <div class="lab">PPG rank</div></div>
    </div>""")


def kpi(label, value, sub="&nbsp;", acc=BORDER, vcolor=TEXT):
    return (f'<div class="fr-kpi" style="--acc:{acc}"><div class="l">{esc(label)}</div>'
            f'<div class="v" style="color:{vcolor}">{esc(str(value))}</div><div class="s">{sub or "&nbsp;"}</div></div>')


def kpi_grid(rep):
    p, m, pos = rep["prof"], rep["m"], rep["pos"]
    rk = {r["key"]: r for r in rep["ranks"]}

    def rank_txt(key):
        r = rk.get(key)
        return f"{pr.ordinal(r['rank'])} of {r['n']} {pos}s" if r and r["rank"] else "&nbsp;"

    def rank_acc(key):
        r = rk.get(key)
        return pct_color(r["pct"], r["higher"]) if r and r["pct"] is not None else BORDER
    l3 = p.get("last3_ppg")
    trend = "&nbsp;"
    if l3 is not None and p["ppg"] is not None:
        d = l3 - p["ppg"]
        col = GREEN if d >= 1 else RED if d <= -1 else MUTED
        bg = G_BG if d >= 1 else R_BG if d <= -1 else BORDER
        trend = (f'<span class="fr-pill" style="background:{bg};color:{col}">{"▲" if d >= 0 else "▼"} {abs(d):.1f}'
                 f'</span> last 3 games')
    f, tdo = m.get("fpoe_pg"), m.get("td_oe_pg")
    f_col = GREEN if (f or 0) >= 1 else RED if (f or 0) <= -1 else TEXT
    f_sub = f"{tdo:+.1f} from TD luck · {f - tdo:+.1f} efficiency" if (f is not None and tdo is not None) else \
        ("Production matches usage" if f is not None else "&nbsp;")
    key_usage = {"WR": ("tgt_share", "Target share", "pct"), "TE": ("tgt_share", "Target share", "pct"),
                 "RB": ("opp_pg", "Opportunities / game", "dec1"),
                 "QB": ("p_epa_per_db", "EPA / dropback", "dec2s")}[pos]
    g12 = p["games"] and p["top12"] / p["games"] >= .4
    cards = [
        kpi("Points / game", fmt(p["ppg"], "dec1"), trend, tier_color(m.get("rank_ppg"))),
        kpi("Total points", fmt(p["pts"], "dec1"), f"{pos}{m['rank_total']} overall" if m.get("rank_total") else "",
            tier_color(m.get("rank_total"))),
        kpi("Expected pts / game", fmt(m.get("xfp_pg"), "dec1"), rank_txt("xfp_pg"), rank_acc("xfp_pg")),
        kpi("Pts over expected", fmt(f, "dec1s"), f_sub, f_col if f is not None else BORDER, f_col),
        kpi("Top-12 weeks", f"{p['top12']} of {p['games']}", f"Top-24: {p['top24']} · Top-36: {p['top36']}",
            GREEN if g12 else BORDER),
        kpi(f"Boom rate ({p['boom']}+)", fmt(p["boom_rate"], "pct"),
            f"Bust rate (under {p['bust']}): {fmt(p['bust_rate'], 'pct')}",
            GREEN if (p["boom_rate"] or 0) >= .35 else RED if (p["bust_rate"] or 0) >= .4 else BORDER),
        kpi("Snap share", fmt(m.get("snap_pct"), "pct100"), rank_txt("snap_pct"), rank_acc("snap_pct")),
        kpi(key_usage[1], fmt(m.get(key_usage[0]), key_usage[2]), rank_txt(key_usage[0]), rank_acc(key_usage[0])),
    ]
    H(f'<div class="fr-grid">{"".join(cards)}</div>')


def notes_html(insights):
    out = []
    for tone, text in insights:
        c, ic = {"up": (GREEN, "▲"), "down": (RED, "▼")}.get(tone, (BLUE, "●"))
        out.append(f'<div class="fr-note" style="--c:{c}"><span class="ic">{ic}</span><span>{esc(text)}</span></div>')
    return f'<div class="fr-grid g2">{"".join(out)}</div>'


def stats_html(rows):
    return '<div class="fr-stats">' + "".join(
        f'<div class="row"><span>{esc(a)}</span><span>{esc(str(b))}</span></div>' for a, b in rows) + "</div>"


def tab_overview(rep, S=None):
    if S is not None:
        p = pr.project_player(S, rep["pid"])
        if p and p.get("week"):
            if p["bye"]:
                H(f'<div class="fr-card" style="border-left:4px solid {SLATE}"><b style="color:{TEXT}">Week {p["week"]}: '
                  f'on bye.</b></div>')
            else:
                lab, col = matchup_info(p.get("fpa_rank"), p.get("fpa_n"))
                H(f'<div class="fr-card" style="border-left:4px solid {GOLD}"><div style="display:flex;flex-wrap:wrap;'
                  f'gap:1.2rem;align-items:center;justify-content:space-between"><div>'
                  f'<div class="fr-cardh" style="color:{GOLD}">Week {p["week"]} projection · {esc(p["label"])}</div>'
                  f'<div style="font-size:2rem;font-weight:800;color:{TEXT}">{p["proj"]:.1f} '
                  f'<span class="fr-sub">pts · range {p["floor"]:.1f}–{p["ceiling"]:.1f} · '
                  f'<span style="color:{col}">{lab} matchup</span></span></div></div>'
                  f'<div style="max-width:560px">{reasons_html(p["reasons"])}</div></div></div>')
            H('<div style="height:.4rem"></div>')
    plot(points_chart(rep))
    H(f'<div class="fr-sub" style="margin-top:-.4rem">'
      f'<span style="color:{GREEN}">■</span> top-12 week &nbsp; <span style="color:{BLUE}">■</span> 13-24 &nbsp; '
      f'<span style="color:{AMBER}">■</span> 25-36 &nbsp; <span style="color:{SLATE}">■</span> below &nbsp;·&nbsp; '
      f'white tick = expected points from his usage &nbsp;·&nbsp; gold dotted line = season average</div>')
    sec("Edge notes")
    if rep["insights"]:
        H(notes_html(rep["insights"]))
    else:
        st.caption("Edge notes appear after a few games.")
    p, m, pos = rep["prof"], rep["m"], rep["pos"]
    left, right = st.columns(2)
    with left:
        sec("Fantasy profile")
        H(stats_html([
            ("Median game", fmt(p["median"], "dec1")),
            ("Floor / ceiling (25th / 75th pct)", f"{fmt(p['floor'], 'dec1')} / {fmt(p['ceiling'], 'dec1')}"),
            ("Best game", f"{fmt(p['best'], 'dec1')} ({p['best_label']})"),
            ("Worst game", fmt(p["worst"], "dec1")),
            ("Volatility (std dev)", fmt(p["stdev"], "dec1")),
            (f"Top-{pr.STARTER_CUTOFF[pos]} finish rate", fmt(p["starter_rate"], "pct")),
        ]))
    with right:
        sec("Where the points come from")
        rows = [("Last 3 games PPG", fmt(p["last3_ppg"], "dec1")),
                ("Points from touchdowns", fmt(m.get("td_pts_share"), "pct"))]
        if pos != "QB" and rep["fmt"] != "standard":
            rows.append(("Points from receptions", fmt(m.get("rec_pts_share"), "pct")))
        if pos == "QB":
            rows.append(("Points from rushing", fmt(m.get("rush_pts_share"), "pct")))
        if m.get("exp_td") is not None:
            rows.append(("Rush + rec TDs vs expected", f"{int(m['act_td_xweeks'])} vs {m['exp_td']:.1f}"))
        if pos == "QB" and m.get("exp_pass_td") is not None:
            rows.append(("Pass TDs vs expected", f"{int(m['act_pass_td_xweeks'])} vs {m['exp_pass_td']:.1f}"))
        H(stats_html(rows))


def weekly_rows(rep):
    pos = rep["pos"]
    out = []
    for w in rep["weekly"]:
        if w.get("status"):
            out.append({"Week": w["week"], "Logo": None, "Opponent": w["status"]})
            continue
        opp_abbr = (w.get("opp") or "").split()[-1] if w.get("opp") else None
        r = {"Week": w["week"], "Logo": logo_url(opp_abbr), "Opponent": w.get("opp", ""),
             "Pts": round(w.get("pts") or 0, 1),
             "Finish": f"{pos}{w['rank']}" if w.get("rank") else "–",
             "xFP": round(w["xfp"], 1) if w.get("xfp") is not None else None,
             "+/-": round(w["fpoe"], 1) if w.get("fpoe") is not None else None,
             "Snap%": fmt(w.get("snap_pct"), "pct100")}
        if pos in ("WR", "TE"):
            r.update({"Route%": fmt(w.get("route_pct"), "pct"), "Tgt": fmt(w.get("targets"), "int"),
                      "Rec": fmt(w.get("rec"), "int"), "Yds": fmt(w.get("rec_yds"), "int"),
                      "TD": fmt(w.get("rec_td"), "int"), "Tgt sh": fmt(w.get("tgt_share"), "pct"),
                      "Air sh": fmt(w.get("air_share"), "pct"), "RZ tgt": fmt(w.get("rz_tgt"), "int"),
                      "EZ tgt": fmt(w.get("ez_tgt"), "int")})
        elif pos == "RB":
            r.update({"Car": fmt(w.get("carries_official", w.get("carries")), "int"),
                      "Rush yds": fmt(w.get("rush_yds"), "int"), "Rush sh": fmt(w.get("rush_share"), "pct"),
                      "Tgt": fmt(w.get("targets"), "int"), "Rec": fmt(w.get("rec"), "int"),
                      "Rec yds": fmt(w.get("rec_yds"), "int"),
                      "TD": fmt((w.get("rush_td") or 0) + (w.get("rec_td") or 0), "int"),
                      "RZ sh": fmt(w.get("rz_share"), "pct"), "HVT": fmt(w.get("hvt"), "int")})
        else:
            r.update({"Cmp/Att": f"{fmt(w.get('completions'), 'int')}/{fmt(w.get('attempts'), 'int')}",
                      "Pass yds": fmt(w.get("pass_yds"), "int"), "TD": fmt(w.get("pass_td"), "int"),
                      "INT": fmt(w.get("ints"), "int"), "Sk": fmt(w.get("sacks"), "int"),
                      "Car": fmt(w.get("carries_official", w.get("carries")), "int"),
                      "Rush yds": fmt(w.get("rush_yds"), "int"), "Rush TD": fmt(w.get("rush_td"), "int"),
                      "EPA/DB": fmt(w.get("epa_db"), "dec2s")})
        out.append(r)
    return out


def finish_color(v):
    if not isinstance(v, str) or len(v) < 3:
        return None
    try:
        return tier_color(int(v[2:]))
    except ValueError:
        return None


def num_sign_color(v):
    return (GREEN if v >= 0 else RED) if isinstance(v, (int, float)) and pd.notna(v) else None


def tab_weekly(rep):
    df = pd.DataFrame(weekly_rows(rep))
    styled_df(df, row_bg=lambda r: "rgba(100,116,139,.12)" if r.get("Opponent") in ("BYE", "Did not play") else None,
              cell={"Finish": finish_color, "+/-": num_sign_color},
              column_config={"Logo": st.column_config.ImageColumn(" ", width="small")})
    sec("Usage by week")
    plot(usage_chart(rep))
    sec("Trends: last 3 games vs season")
    if rep["trends"]:
        cards = []
        for t in rep["trends"]:
            k = t["kind"]
            d = f"{t['delta'] * 100:+.1f} pts" if k == "pct" else f"{t['delta']:+.1f} pts" if k == "pct100" \
                else fmt(t["delta"], "dec1s")
            big = abs(t["delta"]) >= t["thr"]
            col = (GREEN if t["delta"] > 0 else RED) if big else MUTED
            cards.append(kpi(t["label"], fmt(t["last3"], k),
                             f'<span style="color:{col};font-weight:700">{"▲" if t["delta"] >= 0 else "▼"} {d}</span>'
                             f' vs {fmt(t["season"], k)} season', col if big else BORDER))
        H(f'<div class="fr-grid g3">{"".join(cards)}</div>')
    else:
        st.caption("Trends appear after 4 games.")


def tab_matchups(rep):
    sched, pos, tc = rep["sched"], rep["pos"], rep["team_ctx"] or {}
    nt = rep["n_teams"] or 32
    if sched and sched["next"]:
        nx = sched["next"]
        t1, t1s = team_cols(rep["team"])
        t2, t2s = team_cols(nx["opp"])
        lab, col = matchup_info(nx.get("fpa_rank"), nx.get("fpa_n"))
        when = " ".join(str(x) for x in [nx.get("gameday"), nx.get("gametime")] if x)
        spread = f"{rep['team']} {nx['team_spread']:+.1f}" if nx.get("team_spread") is not None else "–"
        H(f"""
        <div class="fr-game">
          <div class="fr-sub" style="margin:0 0 .5rem">NEXT GAME · WEEK {nx['week']}{' · ' + esc(when) if when else ''}</div>
          <div class="teams">{logo(rep['team'], 40)}<span class="fr-tm" style="background:{t1};--s:{t1s}">{esc(rep['team'])}</span>
            <span style="color:{MUTED};font-weight:700">{'vs' if nx['home'] else '@'}</span>
            {logo(nx['opp'], 40)}<span class="fr-tm" style="background:{t2};--s:{t2s}">{esc(nx['opp'])}</span>
            <span class="fr-pill" style="background:{BORDER};color:{col};margin-left:auto;font-size:.82rem">{lab} matchup</span>
          </div>
        </div>""")
        H('<div style="height:.6rem"></div>')
        H('<div class="fr-grid">' + "".join([
            kpi("Implied team total", fmt(nx.get("implied"), "dec1"), "Vegas points for his team",
                GREEN if (nx.get("implied") or 0) >= 25 else RED if (nx.get("implied") or 99) <= 19 else BORDER),
            kpi("Spread", spread, f"Game total {fmt(nx.get('total'), 'dec1')}"),
            kpi(f"{nx['opp']} vs {pos}s", pr.ordinal(nx["fpa_rank"]) if nx.get("fpa_rank") else "–",
                "most fantasy points allowed", col),
            kpi("Points allowed / game", fmt(nx.get("fpa_avg"), "dec1"),
                f"to {pos}s · league avg {fmt(rep['fpa_avg'], 'dec1')}", col),
        ]) + "</div>")
    elif sched:
        st.info("Regular season complete.")
    if sched and sched["upcoming"]:
        sec("Rest of season")
        tiles = []
        items = [(u["week"], u) for u in sched["upcoming"]] + [(w, None) for w in sched["byes"] if w > rep["last_week"]]
        items.sort(key=lambda x: x[0])
        for wk, u in items:
            if u is None:
                tiles.append(f'<div class="fr-wk" style="--c:{SLATE}"><div class="w">Week {wk}</div>'
                             f'<div style="height:34px"></div><div class="o">BYE</div><div class="r">&nbsp;</div></div>')
                continue
            lab, col = matchup_info(u.get("fpa_rank"), u.get("fpa_n"))
            tiles.append(f'<div class="fr-wk" style="--c:{col}"><div class="w">Week {wk}{" ★" if u["playoff"] else ""}</div>'
                         f'{logo(u["opp"], 30)}<div class="o">{esc(u["label"])}</div>'
                         f'<div class="r">{pr.ordinal(u["fpa_rank"]) if u.get("fpa_rank") else "–"} · {lab}</div></div>')
        H(f'<div class="fr-sched">{"".join(tiles)}</div>')
        bits = []
        if sched["ros_avg_rank"]:
            bits.append(f"rest-of-season opponents average a {sched['ros_avg_rank']:.1f} rank")
        if sched["playoff_avg_rank"]:
            bits.append(f"fantasy playoff (★) opponents average {sched['playoff_avg_rank']:.1f}")
        st.caption(f"Rank = where that defense ranks in fantasy points allowed to {pos}s (1st = most allowed = "
                   f"best matchup). " + ("; ".join(bits).capitalize() + "." if bits else ""))
        with st.expander("Full schedule with Vegas lines"):
            rows = []
            for wk, u in items:
                if u is None:
                    rows.append({"Wk": str(wk), "Opponent": "BYE"})
                    continue
                rows.append({"Wk": f"{wk} ★" if u["playoff"] else str(wk), "Opponent": u["label"],
                             "Date": str(u.get("gameday") or ""),
                             "Spread": f"{u['team_spread']:+.1f}" if u.get("team_spread") is not None else "",
                             "Total": fmt(u.get("total"), "dec1"), "Implied": fmt(u.get("implied"), "dec1"),
                             f"Opp rank vs {pos}": pr.ordinal(u["fpa_rank"]) if u.get("fpa_rank") else "–",
                             "Pts allowed": fmt(u.get("fpa_avg"), "dec1"),
                             "Matchup": matchup_info(u.get("fpa_rank"), u.get("fpa_n"))[0]})
            styled_df(pd.DataFrame(rows).fillna(""),
                      cell={"Matchup": lambda v: {"Great": GREEN, "Good": "#86efac", "Tough": RED,
                                                  "Below avg": "#fca5a5"}.get(v)})
    sec(f"{rep['team']} offense")
    cards = []
    for key, lab, kind in [("ppg", "Points / game", "dec1"), ("plays_pg", "Plays / game (pace)", "dec1"),
                           ("pass_rate", "Dropback rate", "pct"), ("proe", "Pass rate over expected", "pct1s"),
                           ("rz_plays_pg", "Red-zone plays / game", "dec1")]:
        r = tc.get(key + "_rank")
        acc = (GREEN if r <= 10 else RED if r >= nt - 9 else BORDER) if r else BORDER
        cards.append(kpi(lab, fmt(tc.get(key), kind), f"{pr.ordinal(r)} of {nt}" if r else "", acc))
    H(f'<div class="fr-grid g5">{"".join(cards)}</div>')


def rank_rows_html(title, items):
    rows = [f'<div class="fr-rank h"><span>{esc(title)}</span><span style="text-align:right">Value</span>'
            f'<span style="text-align:right">Rank</span><span>Percentile</span></div>']
    for r in items:
        pv = r["pct"]
        col = pct_color(pv, r["higher"])
        bar = (f'<div class="fr-bar"><span style="width:{max(3, pv):.0f}%;background:{col}"></span></div>'
               if pv is not None else '<div class="fr-bar"></div>')
        rows.append(f'<div class="fr-rank"><span>{esc(r["label"])}</span><span class="val">{esc(r["value"])}</span>'
                    f'<span class="rk">{r["rank"] if r["rank"] else "–"}/{r["n"]}</span>{bar}</div>')
    return f'<div class="fr-card" style="padding:0">{"".join(rows)}</div>'


def tab_ranks(rep):
    st.caption(f"Compared with {rep['pool_n']} {rep['pos']}s with {rep['min_games']}+ games and real volume. "
               "Green = top third, gold = middle, red = bottom third, blue = style stat (neither good nor bad). "
               "For drop, stuff, sack and INT rates, lower is better and the bar is already flipped.")
    if rep["ngs"]:
        left, right = st.columns([3, 2])
        with left:
            H(rank_rows_html("Production, usage & efficiency", rep["ranks"]))
        with right:
            H(rank_rows_html("Next Gen Stats tracking", rep["ngs"]))
    else:
        H(rank_rows_html("Production, usage & efficiency", rep["ranks"]))
    st.caption("WOPR = 1.5 × target share + 0.7 × air yards share. Routes are approximated by pass plays he was on "
               "the field for.")


def tab_splits(rep):
    if not rep["splits"]:
        st.info("No splits yet.")
        return
    cols = st.columns(2)
    for i, (title, spec, items) in enumerate(rep["splits"]):
        with cols[i % 2]:
            sec(title)
            rows = []
            for lab, s in items:
                r = {"Split": lab}
                for h_, key, kind in spec:
                    r[h_] = "–" if (key == "drops" and not s.get("charted")) else fmt(s.get(key), kind)
                rows.append(r)
            ecol = next((h_ for h_, k, _ in spec if k.startswith("epa")), None)
            styled_df(pd.DataFrame(rows),
                      cell={ecol: lambda v: (GREEN if v.startswith("+") else RED)
                            if isinstance(v, str) and v[:1] in "+-" else None} if ecol else None)


def tab_plays(rep):
    log = rep["log"]
    if not log:
        st.info("No plays yet.")
        return
    weeks = sorted({l["week"] for l in log})
    c1, c2, c3 = st.columns([2, 2, 1.2])
    pick_weeks = c1.multiselect("Weeks", weeks, default=[], placeholder="All weeks")
    pick_types = c2.multiselect("Play types", sorted({l["type"] for l in log}), default=[],
                                placeholder="All play types")
    c3.markdown('<div style="height:1.9rem"></div>', unsafe_allow_html=True)
    only_bad = c3.toggle("Mistakes only", help="Drops, turnovers, INT-worthy throws and penalties")
    rows, kinds = [], []
    for l in log:
        if (pick_weeks and l["week"] not in pick_weeks) or (pick_types and l["type"] not in pick_types) or \
                (only_bad and not (l["_drop"] or l["_bad"])):
            continue
        rows.append({"Wk": l["week"], "Opp": l["opp"],
                     "Q": ("OT" if (l["qtr"] or 0) >= 5 else f"Q{int(l['qtr'])}") if l["qtr"] else "",
                     "Time": l["time"] or "",
                     "Down": f"{pr.ordinal(l['down'])} & {int(l['ydstogo'])}" if l["down"] else "",
                     "Spot": l["yrdln"] or "", "Type": l["type"], "Result": l["result"],
                     "Air": int(l["air_yards"]) if l["air_yards"] is not None else None,
                     "YAC": int(l["yac"]) if l["yac"] is not None else None,
                     "EPA": round(l["epa"], 2) if l["epa"] is not None else None,
                     "Flags": l["flags"], "Play": l["desc"]})
        kinds.append("td" if l["_td"] else "drop" if l["_drop"] else "bad" if l["_bad"] else "")
    H(f'<div class="fr-sub">{len(rows)} plays &nbsp;·&nbsp; <span style="color:{GOLD}">■</span> touchdown &nbsp; '
      f'<span style="color:#fb923c">■</span> drop &nbsp; <span style="color:{RED}">■</span> turnover, '
      f'INT-worthy throw or penalty</div>')
    if not rows:
        return
    df = pd.DataFrame(rows)
    bg = {"td": "rgba(245,179,1,.16)", "drop": "rgba(251,146,60,.18)", "bad": R_BG}
    styled_df(df, row_bg=lambda r: bg.get(kinds[r.name]),
              cell={"EPA": lambda v: (GREEN if v > 0 else RED) if isinstance(v, (int, float)) and pd.notna(v) else None,
                    "Type": lambda v: GOLD if str(v).startswith("TD") else "#fb923c" if v == "DROP" else None},
              height=min(660, 40 + 35 * len(df)),
              column_config={"Play": st.column_config.TextColumn("Play", width="large")})


def pdf_button(rep):
    key = f"pdf_{rep['pid']}_{rep['season']}_{rep['fmt']}"
    if st.session_state.get(key) is None:
        if st.button("📄 Make a PDF copy", help="Optional. Everything is already on this page."):
            with st.spinner("Building PDF..."):
                fd, path = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                try:
                    pr.build_pdf(rep, path)
                    with open(path, "rb") as f:
                        st.session_state[key] = f.read()
                finally:
                    os.remove(path)
            st.rerun()
    else:
        st.download_button("⬇️ Download PDF", st.session_state[key],
                           file_name=f"{pr.slug(rep['name'])}_{rep['season']}_report.pdf", mime="application/pdf")


def player_search(S, key, placeholder="Search any QB, RB, WR or TE..."):
    pids, labels = get_player_list(S, skey(S))
    if st.session_state.get(key) not in labels:
        st.session_state[key] = None
    return st.selectbox("Player", pids, format_func=lambda p: labels.get(p, p), key=key,
                        placeholder=placeholder, label_visibility="collapsed")


def page_player(S):
    if "player" not in st.session_state:
        st.session_state.player = st.query_params.get("player")
    pid = player_search(S, "player")
    if not pid:
        st.query_params.pop("player", None)
        H(f'<div class="fr-card" style="text-align:center;padding:2.2rem 1rem;margin-top:1rem">'
          f'<div style="font-size:2rem">🔎</div><div style="font-weight:800;color:{TEXT};margin:.3rem 0">'
          f'Search for any player above</div><div class="fr-sub">Or open <b>Rankings</b> and tap a row, or pick one '
          f'from the <b>Home</b> dashboard.</div></div>')
        return
    st.query_params["player"] = pid
    with st.spinner("Building report..."):
        rep = get_report(S, skey(S, pid))
    if st.button("⚖️ Compare him with someone"):
        st.session_state.pending = {"view": "Compare", "compare": [pid]}
        st.rerun()
    hero(rep)
    kpi_grid(rep)
    H('<div style="height:.9rem"></div>')
    tabs = st.tabs(["📈 Overview", "🗓️ Week by week", "🆚 Matchups", "🏅 League ranks", "🧩 Splits", "🎬 Plays"])
    with tabs[0]:
        tab_overview(rep, S)
    for t, fn in zip(tabs[1:], (tab_weekly, tab_matchups, tab_ranks, tab_splits, tab_plays)):
        with t:
            fn(rep)
    glossary(["xFP", "+/- exp", "TD luck", "Finish", "Snap %", "Route %", "Boom / bust", "Floor / ceiling",
              "Implied total", "Spread", "Defense rank", "PROE", "RZ", "EZ tgt", "HVT", "EPA"]
             + POS_TERMS[rep["pos"]])
    st.divider()
    pdf_button(rep)


# ------------------------------------------------------------------------------------
# Home dashboard
# ------------------------------------------------------------------------------------

def list_card(title, desc, color, items):
    body = "".join(items) if items else '<div class="fr-sub" style="padding:.5rem 0">Not enough data yet.</div>'
    head = f'<div class="fr-cardh" style="color:{color}">{esc(title)}</div>'
    if desc:
        head += f'<div class="fr-cardd">{esc(desc)}</div>'
    return f'<div class="fr-card" style="border-top:3px solid {color}">{head}<div class="fr-list">{body}</div></div>'


def list_item(pid, name, sub, num, color, team=None):
    return (f'<div class="it"><div style="display:flex;gap:.55rem;align-items:center">{logo(team, 24)}'
            f'<div>{plink(pid, name)}<div class="sm">{esc(sub)}</div></div></div>'
            f'<div class="num" style="color:{color}">{esc(num)}</div></div>')


def page_home(S):
    H(f'<div class="fr-title">Fantasy Player Reports</div>'
      f'<div class="fr-sub">{S.season} season through week {S.last_week} · {pr.FORMAT_LABEL[S.fmt_name]}</div>')
    H('<div style="height:.7rem"></div>')
    pid = player_search(S, "home_search", "🔎  Search any player to open his full report...")
    if pid:
        st.session_state.pending = {"player": pid, "view": "Player"}
        st.rerun()
    with st.spinner("Crunching the league..."):
        d = get_home(S, skey(S))

    # 1. Last week's leaders
    sec(f"Week {S.last_week} leaders")
    cards = []
    for pos in pr.FANTASY_POS:
        its = [list_item(r["pid"], r["name"], f"{pos}{r.get('rank', '')} · {r['team']}"
                                              f"{' vs ' + r['opp'] if r.get('opp') else ''}",
                         f"{r['pts']:.1f}", tier_color(r.get("rank")), r["team"]) for r in d["week_top"][pos]]
        cards.append(list_card(f"{pos}s", "", GOLD, its))
    H(f'<div class="fr-grid">{"".join(cards)}</div>')

    # 2. Season leaders
    sec("Season leaders (total points)")
    cards = []
    for pos in pr.FANTASY_POS:
        its = [list_item(pid, t["name"], f"{t['team']} · {t['games']} games · {t['ppg']:.1f} PPG",
                         f"{t['pts']:.1f}", tier_color(t.get("rank_total")), t["team"])
               for pid, t in d["season_top"][pos]]
        cards.append(list_card(f"{pos}s", "", BLUE, its))
    H(f'<div class="fr-grid">{"".join(cards)}</div>')

    # 3. Next week's matchups
    if d["next_week"]:
        sec(f"Best matchups in week {d['next_week']}")
        cards = []
        for pos in pr.FANTASY_POS:
            its = []
            for x in d["matchups"].get(pos, []):
                lab, col = matchup_info(x["rank"], x["n"])
                its.append(f'<div class="it"><div style="display:flex;gap:.55rem;align-items:center">{logo(x["off"], 24)}'
                           f'<div><b style="color:{TEXT}">{esc(x["off"])} {pos}s</b>'
                           f'<div class="sm">vs {esc(x["def"])} defense · allows {x["avg"]:.1f} / game</div></div></div>'
                           f'<div class="num" style="color:{col}">{pr.ordinal(x["rank"])}</div></div>')
            cards.append(list_card(f"{pos}s", "", GREEN, its))
        H(f'<div class="fr-grid">{"".join(cards)}</div>')
        H(f'<div class="fr-sub" style="margin-top:.4rem">Number = where that defense ranks in points allowed to the '
          f'position (1st = most allowed).</div>')

    # 4. Usage trends
    tr = d["trend"]
    rising = sorted([x for x in tr if x["val"] > 0], key=lambda x: -x["val"])[:6]
    falling = sorted([x for x in tr if x["val"] < 0], key=lambda x: x["val"])[:6]

    def sub_tr(x):
        return f"{x['pos']} · {x['team']} · {x['l3']:.1f} xFP last 3 vs {x['season']:.1f} season"
    sec("Usage trends (role changes show up here first)")
    H('<div class="fr-grid g2">' + "".join([
        list_card("Usage rising", "Expected points from his usage, last 3 games vs season", BLUE,
                  [list_item(x["pid"], x["name"], sub_tr(x), f"▲ {x['val']:.1f}", BLUE, x["team"]) for x in rising]),
        list_card("Usage falling", "Expected points from his usage, last 3 games vs season", AMBER,
                  [list_item(x["pid"], x["name"], sub_tr(x), f"▼ {abs(x['val']):.1f}", AMBER, x["team"])
                   for x in falling]),
    ]) + "</div>")

    # 5. TD luck: buy low / sell high
    lk = d["luck"]
    buy = sorted([x for x in lk if x["val"] <= -1.0], key=lambda x: x["val"])[:6]
    sell = sorted([x for x in lk if x["val"] >= 1.5], key=lambda x: -x["val"])[:6]

    def sub_lk(x):
        return f"{x['pos']} · {x['team']} · {int(x['act_td'])} TDs on {x['exp_td']:.1f} expected"
    sec("Buy low / sell high (touchdown luck)")
    H('<div class="fr-grid g2">' + "".join([
        list_card("Buy low", "Scoring fewer TDs than his usage predicts. Expect more.", GREEN,
                  [list_item(x["pid"], x["name"], sub_lk(x), f"{x['val']:+.1f}", GREEN, x["team"]) for x in buy]),
        list_card("Sell high", "Scoring more TDs than his usage predicts. Expect fewer.", RED,
                  [list_item(x["pid"], x["name"], sub_lk(x), f"{x['val']:+.1f}", RED, x["team"]) for x in sell]),
    ]) + "</div>")
    H('<div class="fr-sub" style="margin-top:.4rem">Number = points per game likely to come back (buy) or fade (sell): '
      'TD luck plus a small share of efficiency. Players who simply beat their usage through skill (catch rate, '
      'yards after catch) are not listed here. Includes players averaging 7+ expected points over 4+ games.</div>')
    glossary(["xFP", "TD luck", "+/- exp", "PPG", "Defense rank"])


# ------------------------------------------------------------------------------------
# Rankings and defense pages
# ------------------------------------------------------------------------------------

RANK_COLS = {
    "WR": [("Target share", "tgt_share", 100), ("Air yards share", "air_share", 100), ("WOPR", "wopr", 1),
           ("Route %", "route_pct", 100), ("YPRR", "yprr", 1), ("TPRR", "tprr", 100), ("aDOT", "r_adot", 1),
           ("Drop %", "r_drop_rate", 100)],
    "RB": [("Opportunities/G", "opp_pg", 1), ("Rush share", "rush_share", 100), ("HVT/G", "hvt_pg", 1),
           ("Inside-10 share", "i10_share", 100), ("Target share", "tgt_share", 100), ("YPC", "ru_ypc", 1),
           ("EPA/rush", "ru_epa_per", 1), ("Stuff %", "ru_stuff_rate", 100)],
    "QB": [("Dropbacks/G", "p_dropbacks_pg", 1), ("EPA/dropback", "p_epa_per_db", 1), ("CPOE", "p_cpoe", 1),
           ("ANY/A", "p_any_a", 1), ("Rush yds/G", "rush_ypg", 1), ("Scrambles/G", "p_scrambles_pg", 1),
           ("Sack %", "p_sack_rate", 100), ("INT %", "p_int_rate", 100)],
}
RANK_COLS["TE"] = RANK_COLS["WR"]
RANK_BY = {"Total points": "Total pts", "Points per game": "PPG", "Expected points": "xFP/G"}


def segmented(label, options, key, default, fmt_fn=None):
    last = f"_{key}_last"
    if st.session_state.get(key) not in options:
        st.session_state[key] = st.session_state.get(last, default)
    ff = fmt_fn or (lambda o: o)
    if hasattr(st, "segmented_control"):
        v = st.segmented_control(label, options, key=key, label_visibility="collapsed", format_func=ff)
    else:
        v = st.radio(label, options, key=key, horizontal=True, label_visibility="collapsed", format_func=ff)
    v = v or st.session_state.get(last, default)
    st.session_state[last] = v
    return v


def page_rankings(S):
    H('<div class="fr-title">Rankings</div><div class="fr-sub">Tap a column header to re-sort, tap a row to open '
      'his report.</div>')
    H('<div style="height:.6rem"></div>')
    c1, c2 = st.columns([1, 1.4])
    with c1:
        pos = segmented("Position", list(pr.FANTASY_POS), "rank_pos", "WR")
    with c2:
        by = segmented("Rank by", list(RANK_BY), "rank_by", "Total points", lambda o: f"Rank by {o.lower()}")
    with st.spinner("Ranking players..."):
        pool, _ = pr.position_pool(S, pos)
    rows = []
    for pid, m in pool.items():
        t = S.season_tot.get(pid, {})
        r = {"pid": pid, "Logo": logo_url(t.get("team")), "Player": t.get("name"), "Team": t.get("team"),
             "Games": m["games"], "Total pts": t.get("pts"), "PPG": m.get("ppg"), "xFP/G": m.get("xfp_pg"),
             "+/- exp": m.get("fpoe_pg"), "TD luck/G": m.get("td_oe_pg"), "Snap %": m.get("snap_pct")}
        for lab, key, mult in RANK_COLS[pos]:
            v = m.get(key)
            r[lab] = v * mult if v is not None else None
        rows.append(r)
    if not rows:
        st.info("Not enough games played yet.")
        return
    teams = sorted({r["Team"] for r in rows if r["Team"]})
    pick = st.multiselect("Teams", teams, default=[], placeholder="Filter by team (optional)",
                          label_visibility="collapsed")
    sort_col = RANK_BY[by]
    df = pd.DataFrame(rows).sort_values(sort_col, ascending=False, na_position="last").reset_index(drop=True)
    df.insert(1, "Rank", range(1, len(df) + 1))
    if pick:
        df = df[df["Team"].isin(pick)].reset_index(drop=True)
    cfg = {"pid": None, "Rank": st.column_config.NumberColumn("Rank", width="small"),
           "Logo": st.column_config.ImageColumn(" ", width="small"),
           "Total pts": st.column_config.NumberColumn(format="%.1f"),
           "PPG": st.column_config.NumberColumn(format="%.1f"), "xFP/G": st.column_config.NumberColumn(format="%.1f"),
           "+/- exp": st.column_config.NumberColumn(format="%+.1f", help="Points over expected per game"),
           "TD luck/G": st.column_config.NumberColumn(format="%+.1f", help="Points per game from TD luck"),
           "Snap %": st.column_config.NumberColumn(format="%.0f%%")}
    for lab, key, mult in RANK_COLS[pos]:
        cfg[lab] = st.column_config.NumberColumn(format="%.0f%%" if mult == 100 else "%.2f")
    sty = smap(df.style, lambda v: f"color: {tier_color(v)}; font-weight: 800" if pd.notna(v) else "", ["Rank"])
    sty = smap(sty, lambda v: (f"color: {GREEN}" if v >= 1 else f"color: {RED}" if v <= -1 else "")
               if pd.notna(v) else "", ["+/- exp", "TD luck/G"])
    sty = smap(sty, lambda v: "font-weight: 800", [sort_col])
    try:
        ev = st.dataframe(sty, use_container_width=True, hide_index=True, column_config=cfg, height=640,
                          on_select="rerun", selection_mode="single-row", key=f"rank_table_{pos}_{by}")
        sel = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
    except TypeError:
        st.dataframe(sty, use_container_width=True, hide_index=True, column_config=cfg, height=640)
        sel = []
    note = {"Total points": "Total points rewards availability, like your league's standings.",
            "Points per game": "Points per game ignores missed games, so players with fewer games can rank high.",
            "Expected points": "Expected points ranks by usage alone, the most stable predictor of future scoring."}[by]
    st.caption(f"{len(df)} {pos}s with {S.min_games}+ games and real volume. {note} "
               "Rank colour: green top 12, blue 13-24, gold 25-36.")
    if sel:
        st.session_state.pending = {"player": df.iloc[sel[0]]["pid"], "view": "Player"}
        st.rerun()
    glossary(["Total pts", "PPG", "xFP", "+/- exp", "TD luck", "Snap %"] + POS_TERMS[pos])


def page_defense(S):
    H(f'<div class="fr-title">Defense vs position</div><div class="fr-sub">Average fantasy points allowed per game '
      f'({pr.FORMAT_LABEL[S.fmt_name]}). Rank 1 = allows the most = best matchup for your players. '
      f'Green = attack, red = avoid.</div>')
    H('<div style="height:.6rem"></div>')
    teams = sorted({k[0] for k in S.fpa})
    n = len(teams)
    rows = []
    for t in teams:
        r = {"Logo": logo_url(t), "Defense": t}
        for pos in pr.FANTASY_POS:
            f = S.fpa.get((t, pos), {})
            r[f"{pos} pts"] = f.get("avg")
            r[f"{pos} rank"] = f.get("rank")
        rows.append(r)
    sort_pos = segmented("Sort by", list(pr.FANTASY_POS), "def_pos", "WR", lambda p: f"Sort by {p}")
    df = pd.DataFrame(rows).sort_values(f"{sort_pos} rank").reset_index(drop=True)

    def heat(v):
        if pd.isna(v):
            return ""
        x = (v - 1) / max(1, n - 1)
        a = abs(0.5 - x) * 0.9
        rgb = "34,197,94" if x <= 0.5 else "239,68,68"
        return f"background-color: rgba({rgb},{a:.2f}); font-weight: 700"
    rk_cols = [c for c in df.columns if c.endswith(" rank")]
    pts_cols = [c for c in df.columns if c.endswith(" pts")]
    sty = df.style.format("{:.1f}", subset=pts_cols, na_rep="").format("{:.0f}", subset=rk_cols, na_rep="")
    sty = smap(sty, heat, rk_cols)
    st.dataframe(sty, use_container_width=True, hide_index=True, height=40 + 35 * len(df),
                 column_config={"Logo": st.column_config.ImageColumn(" ", width="small")})
    glossary(["Defense rank"], "How to read this")
    H('<div class="fr-sub">"QB pts" = average fantasy points per game that defense has allowed to quarterbacks; '
      '"QB rank" = where that ranks among all defenses. Same for RB, WR and TE.</div>')


# ------------------------------------------------------------------------------------
# Accounts and team storage
# ------------------------------------------------------------------------------------
# People make an account with a username, password and email. Passwords and recovery keys are
# stored only as scrypt hashes. Sessions are random tokens (only their SHA-256 is stored) kept in a
# browser cookie. Teams, accounts and sessions live in Supabase, reached only from this server.

DEFAULT_SLOTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0}
SLOT_ELIG = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "FLEX": {"RB", "WR", "TE"},
             "SUPERFLEX": {"QB", "RB", "WR", "TE"}}
SLOT_LABEL = {"FLEX": "W/R/T", "SUPERFLEX": "Q/W/R/T"}
MAX_TEAMS, MAX_ROSTER = 12, 30
COOKIE = "fr_session"
SESSION_DAYS, SHORT_SESSION_DAYS = 30, 1
MAX_FAILS, LOCK_MINUTES, CODE_MINUTES, CODE_TRIES = 5, 10, 15, 5
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC_LOGIN_ERROR = "Username or password is incorrect."


def _secrets(section):
    try:
        return dict(st.secrets[section]) if section in st.secrets else None
    except Exception:
        return None


def _now():
    return datetime.now(timezone.utc)


def _parse_ts(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def hash_secret(secret):
    salt = pysecrets.token_bytes(16)
    h = hashlib.scrypt(secret.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_secret(secret, stored):
    try:
        _, n, r, p, salt, h = (stored or "").split("$")
        calc = hashlib.scrypt(secret.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = None


def _dummy_check(pw):
    """Spend the same time on unknown usernames so response timing doesn't reveal which accounts exist."""
    global _DUMMY_HASH
    _DUMMY_HASH = _DUMMY_HASH or hash_secret("not-a-real-password")
    check_secret(pw or "x", _DUMMY_HASH)


def token_hash(t):
    return hashlib.sha256(t.encode()).hexdigest()


def new_recovery_key():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(pysecrets.choice(alphabet) for _ in range(20))
    return "-".join(raw[i:i + 5] for i in range(0, 20, 5))


def norm_key(k):
    return re.sub(r"[^A-Z0-9]", "", (k or "").upper())


def check_new_password(pw, username=""):
    if len(pw or "") < 8:
        return "Password must be at least 8 characters."
    if pw.lower() == (username or "").lower():
        return "Password can't be the same as your username."
    if pw.isdigit() or pw.isalpha():
        return "Use a mix of letters and numbers (or symbols)."
    return None


class Conflict(Exception):
    pass


class Rest:
    """Tiny client for Supabase's REST API, used only from this server with the secret key."""

    def __init__(self, url, key):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):  # legacy service_role keys are JWTs and also go in the Authorization header
            self.headers["Authorization"] = f"Bearer {key}"

    def req(self, method, table, params=None, body=None, prefer=None):
        import requests
        h = dict(self.headers)
        if prefer:
            h["Prefer"] = prefer
        r = requests.request(method, self.base + table, params=params, json=body, headers=h, timeout=15)
        if r.status_code == 409:
            raise Conflict(r.text[:200])
        if r.status_code >= 300:
            raise RuntimeError(f"Database error {r.status_code}: {r.text[:200]}")
        return r.json() if r.text.strip() else None

    @staticmethod
    def _eq(filters):
        return {k: f"eq.{v}" for k, v in filters.items()}

    def get(self, table, select="*", order=None, **filters):
        params = {**self._eq(filters), "select": select}
        if order:
            params["order"] = order
        return self.req("GET", table, params) or []

    def insert(self, table, row):
        return self.req("POST", table, None, row, "return=representation")[0]

    def update(self, table, row, **filters):
        self.req("PATCH", table, self._eq(filters), row, "return=minimal")

    def delete(self, table, **filters):
        if not filters:
            raise ValueError("Refusing to delete without a filter")
        self.req("DELETE", table, self._eq(filters), prefer="return=minimal")


@st.cache_resource(show_spinner=False)
def _rest(url, key):
    return Rest(url, key)


def get_db():
    cfg = _secrets("supabase")
    if cfg and cfg.get("url") and cfg.get("key"):
        return _rest(cfg["url"], cfg["key"])
    return None


def mail_config():
    cfg = _secrets("email")
    return cfg if cfg and cfg.get("username") and cfg.get("password") else None


def send_reset_email(cfg, to, code, name):
    import smtplib
    import ssl
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = f"Your Fantasy Reports reset code: {code}"
    msg["From"] = f"{cfg.get('from_name', 'Fantasy Reports')} <{cfg.get('from_address', cfg['username'])}>"
    msg["To"] = to
    msg.set_content(f"Hi {name},\n\nYour password reset code is {code}\n\nIt expires in {CODE_MINUTES} minutes. "
                    f"If you didn't ask for this, you can ignore this email. Your password hasn't changed.\n\n"
                    f"Fantasy Reports")
    with smtplib.SMTP(cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 587)), timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(cfg["username"], cfg["password"])
        s.send_message(msg)


class Accounts:
    def __init__(self, db):
        self.db = db

    def _find(self, ident):
        ident = (ident or "").strip().lower()
        if not ident:
            return None
        rows = self.db.get("accounts", email=ident) if "@" in ident else self.db.get("accounts", username=ident)
        return rows[0] if rows else None

    def signup(self, username, email, password):
        username, email = (username or "").strip(), (email or "").strip().lower()
        if not USERNAME_RE.match(username):
            raise ValueError("Usernames are 3-20 characters: letters, numbers, dots, dashes or underscores.")
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address. It's only used to recover your account.")
        err = check_new_password(password, username)
        if err:
            raise ValueError(err)
        if self.db.get("accounts", select="id", username=username.lower()):
            raise ValueError("That username is taken.")
        if self.db.get("accounts", select="id", email=email):
            raise ValueError("An account already uses that email. Use 'Forgot password' to get back in.")
        key = new_recovery_key()
        try:
            row = self.db.insert("accounts", {"username": username.lower(), "display_name": username, "email": email,
                                              "pw_hash": hash_secret(password),
                                              "recovery_hash": hash_secret(norm_key(key))})
        except Conflict:
            raise ValueError("That username or email was just taken. Try another.")
        return row, key

    def login(self, ident, password):
        a = self._find(ident)
        if not a:
            _dummy_check(password)
            raise ValueError(GENERIC_LOGIN_ERROR)
        lu = _parse_ts(a.get("locked_until"))
        if lu and lu > _now():
            mins = max(1, int((lu - _now()).total_seconds() // 60) + 1)
            raise ValueError(f"Too many wrong passwords. Try again in {mins} minute{'s' if mins != 1 else ''}, "
                             f"or reset your password.")
        if not check_secret(password or "", a["pw_hash"]):
            fails = (a.get("failed_logins") or 0) + 1
            upd = {"failed_logins": fails}
            if fails >= MAX_FAILS:
                upd = {"failed_logins": 0, "locked_until": (_now() + timedelta(minutes=LOCK_MINUTES)).isoformat()}
            self.db.update("accounts", upd, id=a["id"])
            raise ValueError(GENERIC_LOGIN_ERROR)
        if a.get("failed_logins") or a.get("locked_until"):
            self.db.update("accounts", {"failed_logins": 0, "locked_until": None}, id=a["id"])
        return a

    def create_session(self, account_id, days):
        tok = pysecrets.token_urlsafe(32)
        self.db.insert("sessions", {"token_hash": token_hash(tok), "account_id": account_id,
                                    "expires_at": (_now() + timedelta(days=days)).isoformat()})
        return tok

    def session_account(self, tok):
        rows = self.db.get("sessions", token_hash=token_hash(tok))
        if not rows:
            return None
        exp = _parse_ts(rows[0]["expires_at"])
        if not exp or exp < _now():
            self.db.delete("sessions", token_hash=token_hash(tok))
            return None
        acc = self.db.get("accounts", id=rows[0]["account_id"])
        return acc[0] if acc else None

    def end_session(self, tok):
        if tok:
            self.db.delete("sessions", token_hash=token_hash(tok))

    def send_code(self, ident, cfg):
        """Always looks the same to the user, whether or not the account exists."""
        a = self._find(ident)
        if not a:
            return
        code = f"{pysecrets.randbelow(10 ** 6):06d}"
        self.db.update("accounts", {"reset_code_hash": hash_secret(code), "reset_attempts": 0,
                                    "reset_expires": (_now() + timedelta(minutes=CODE_MINUTES)).isoformat()},
                       id=a["id"])
        send_reset_email(cfg, a["email"], code, a["display_name"])

    def _set_password(self, a, new_pw, extra=None):
        self.db.update("accounts", {"pw_hash": hash_secret(new_pw), "failed_logins": 0, "locked_until": None,
                                    "reset_code_hash": None, "reset_expires": None, **(extra or {})}, id=a["id"])
        self.db.delete("sessions", account_id=a["id"])  # sign out every device

    def reset_with_code(self, ident, code, new_pw):
        bad = ValueError("That code is wrong or has expired. Request a new one.")
        a = self._find(ident)
        if not a or not a.get("reset_code_hash"):
            raise bad
        exp = _parse_ts(a.get("reset_expires"))
        if not exp or exp < _now() or (a.get("reset_attempts") or 0) >= CODE_TRIES:
            raise bad
        if not check_secret(re.sub(r"\D", "", code or ""), a["reset_code_hash"]):
            self.db.update("accounts", {"reset_attempts": (a.get("reset_attempts") or 0) + 1}, id=a["id"])
            raise bad
        err = check_new_password(new_pw, a["username"])
        if err:
            raise ValueError(err)
        self._set_password(a, new_pw)
        return a

    def reset_with_key(self, ident, key, new_pw):
        a = self._find(ident)
        if not a or not check_secret(norm_key(key), a.get("recovery_hash") or ""):
            if not a:
                _dummy_check(key)
            raise ValueError("That username/email and recovery key don't match.")
        err = check_new_password(new_pw, a["username"])
        if err:
            raise ValueError(err)
        new_key = new_recovery_key()
        self._set_password(a, new_pw, {"recovery_hash": hash_secret(norm_key(new_key))})
        return a, new_key

    def _verify(self, a, password):
        fresh = self.db.get("accounts", id=a["id"])
        if not fresh or not check_secret(password or "", fresh[0]["pw_hash"]):
            raise ValueError("Your current password is incorrect.")
        return fresh[0]

    def change_password(self, a, current, new_pw):
        a = self._verify(a, current)
        err = check_new_password(new_pw, a["username"])
        if err:
            raise ValueError(err)
        self.db.update("accounts", {"pw_hash": hash_secret(new_pw)}, id=a["id"])

    def change_email(self, a, password, email):
        a = self._verify(a, password)
        email = (email or "").strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address.")
        other = self.db.get("accounts", select="id", email=email)
        if other and other[0]["id"] != a["id"]:
            raise ValueError("Another account already uses that email.")
        self.db.update("accounts", {"email": email}, id=a["id"])
        return email

    def new_key(self, a, password):
        a = self._verify(a, password)
        key = new_recovery_key()
        self.db.update("accounts", {"recovery_hash": hash_secret(norm_key(key))}, id=a["id"])
        return key

    def delete_account(self, a, password):
        a = self._verify(a, password)
        self.db.delete("teams", owner=a["id"])
        self.db.delete("sessions", account_id=a["id"])
        self.db.delete("accounts", id=a["id"])


def public_account(a):
    return {"id": a["id"], "username": a["username"], "display_name": a.get("display_name") or a["username"],
            "email": a["email"]}


# ----- browser cookie (keeps people signed in on their phone) -----

def write_cookie(value, days):
    import streamlit.components.v1 as components
    age = 0 if value is None else int(days * 86400)
    val = value or ""
    components.html(f"<script>document.cookie='{COOKIE}={val}; path=/; max-age={age}; SameSite=Lax; Secure';"
                    f"</script>", height=0)


def read_cookie():
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


def restore_session():
    """On each visit: apply pending cookie changes, and sign back in from the cookie if possible."""
    op = st.session_state.pop("_cookie_op", None)
    if op:
        write_cookie(*op)
    if st.session_state.get("account") or st.session_state.get("_signed_out"):
        return
    db = get_db()
    tok = read_cookie()
    if not db or not tok or st.session_state.get("_cookie_checked") == tok:
        return
    st.session_state._cookie_checked = tok
    try:
        a = Accounts(db).session_account(tok)
    except Exception:
        return
    if a:
        st.session_state.account = public_account(a)
        st.session_state._token = tok


def start_session(db, a, remember):
    days = SESSION_DAYS if remember else SHORT_SESSION_DAYS
    tok = Accounts(db).create_session(a["id"], days)
    st.session_state.account = public_account(a)
    st.session_state._token = tok
    st.session_state.pop("_signed_out", None)
    st.session_state._cookie_op = (tok, days)


def sign_out():
    db = get_db()
    try:
        if db:
            Accounts(db).end_session(st.session_state.get("_token"))
    except Exception:
        pass
    for k in ("account", "_token", "team_sel", "team_mode", "_teams_nonce"):
        st.session_state.pop(k, None)
    st.session_state._signed_out = True
    st.session_state._cookie_op = (None, 0)


class TeamStore:
    """Teams table. Every query is filtered by the signed-in account's id."""
    persistent = True

    def __init__(self, db):
        self.db = db

    def list(self, owner):
        return self.db.get("teams", select="id,name,data,updated_at", order="updated_at.desc", owner=owner)

    def save(self, owner, team_id, data):
        body = {"owner": owner, "name": data["name"], "data": data, "updated_at": _now().isoformat()}
        if team_id:
            self.db.update("teams", body, id=team_id, owner=owner)
            return team_id
        if len(self.list(owner)) >= MAX_TEAMS:
            raise ValueError(f"You can save up to {MAX_TEAMS} teams.")
        return self.db.insert("teams", body)["id"]

    def delete(self, owner, team_id):
        self.db.delete("teams", id=team_id, owner=owner)


class SessionStore:
    """Fallback when no database is set up: teams live only in this browser tab."""
    persistent = False

    def _all(self):
        return st.session_state.setdefault("_guest_teams", {})

    def list(self, owner):
        return sorted(self._all().values(), key=lambda t: t["updated_at"], reverse=True)

    def save(self, owner, team_id, data):
        team_id = team_id or f"guest-{datetime.now().timestamp():.0f}"
        self._all()[team_id] = {"id": team_id, "name": data["name"], "data": data,
                                "updated_at": datetime.now().isoformat()}
        return team_id

    def delete(self, owner, team_id):
        self._all().pop(team_id, None)


# ------------------------------------------------------------------------------------
# Team analysis (pure Python, no Streamlit calls)
# ------------------------------------------------------------------------------------

def slot_list(slots):
    order = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"]
    return [s for s in order for _ in range(int(slots.get(s, 0) or 0))]


def optimal_lineup(projs, slots):
    """Best lineup by projection. Fixed slots first, then flex slots from what's left."""
    avail = sorted([p for p in projs.values() if p], key=lambda p: -p["proj"])
    used, lineup = set(), []
    for slot in slot_list(slots):
        if slot in ("FLEX", "SUPERFLEX"):
            continue
        pick = next((p for p in avail if p["pid"] not in used and p["pos"] in SLOT_ELIG[slot]), None)
        lineup.append({"slot": slot, "p": pick})
        if pick:
            used.add(pick["pid"])
    for slot in slot_list(slots):
        if slot not in ("FLEX", "SUPERFLEX"):
            continue
        pick = next((p for p in avail if p["pid"] not in used and p["pos"] in SLOT_ELIG[slot]), None)
        lineup.append({"slot": slot, "p": pick})
        if pick:
            used.add(pick["pid"])
    bench = [p for p in avail if p["pid"] not in used]
    return lineup, bench


def grade_for(ratio):
    if ratio is None:
        return "–", SLATE
    for cut, g_, c in [(1.15, "A", GREEN), (1.05, "B", "#86efac"), (0.95, "C", AMBER), (0.85, "D", "#fca5a5")]:
        if ratio >= cut:
            return g_, c
    return "F", RED


def analyze_team(S, team):
    slots = {**DEFAULT_SLOTS, **(team.get("slots") or {})}
    n_teams = int(team.get("teams_in_league") or 12)
    week = pr.next_week(S)
    roster = [pid for pid in dict.fromkeys(team.get("roster", [])) if pr.player_base(S, pid)]
    missing = [pid for pid in team.get("roster", []) if pid not in roster]
    projs = {pid: pr.project_player(S, pid, week) for pid in roster}
    lineup, bench = optimal_lineup(projs, slots)
    starters = [l["p"] for l in lineup if l["p"]]
    out = {"week": week, "slots": slots, "n_teams": n_teams, "projs": projs, "lineup": lineup, "bench": bench,
           "missing": missing, "alerts": [], "close": [], "grades": {}, "trades": [], "byes": [],
           "targets": {}, "sell": [], "surplus": [], "roster_rows": []}
    if not week:
        return out

    # Close calls: a bench player within a point of a starter he could replace
    for l in lineup:
        s_ = l["p"]
        if not s_:
            out["alerts"].append(("down", f"No eligible player for your {SLOT_LABEL.get(l['slot'], l['slot'])} slot "
                                          f"in week {week}. Add one."))
            continue
        for b in bench:
            if b["pos"] in SLOT_ELIG[l["slot"]] and b["proj"] > 0 and s_["proj"] - b["proj"] < 1.0:
                safer = s_ if s_["floor"] >= b["floor"] else b
                upside = s_ if s_["ceiling"] >= b["ceiling"] else b
                out["close"].append({"slot": l["slot"], "start": s_, "bench": b, "safer": safer, "upside": upside})
                break
    for p in starters:
        if p.get("inj_status"):
            out["alerts"].append(("down", f"{p['name']} is listed {p['inj_status']}. Check before kickoff and have "
                                          f"a backup ready."))
    for p in projs.values():
        if p and p["bye"]:
            out["alerts"].append(("info", f"{p['name']} is on bye in week {week}."))
        elif p and p["injf"] == 0:
            out["alerts"].append(("down", f"{p['name']} is {p['inj_status']} and projects for 0."))

    # Position grades vs an average starter in a league this size
    total_mine, total_avg = 0.0, 0.0
    for pos in pr.FANTASY_POS:
        n_slots = slots.get(pos, 0)
        if not n_slots:
            continue
        league = [p for p in pr.position_projections(S, pos, week) if not p["bye"]]
        top = league[: n_teams * n_slots]
        avg = mean([p["proj"] for p in top])
        mine = [l["p"] for l in lineup if l["slot"] == pos and l["p"]]
        my_avg = mean([p["proj"] for p in mine]) if mine else 0.0
        ratio = div(my_avg, avg) if avg else None
        out["grades"][pos] = {"mine": my_avg, "avg": avg, "ratio": ratio, "grade": grade_for(ratio),
                              "players": mine, "baseline_proj": top[-1]["proj"] if top else None}
        total_mine += my_avg * n_slots
        total_avg += (avg or 0) * n_slots
    for slot in ("FLEX", "SUPERFLEX"):
        n = slots.get(slot, 0)
        if n:
            mine = [l["p"]["proj"] for l in lineup if l["slot"] == slot and l["p"]]
            total_mine += sum(mine)
            pool = sorted([p["proj"] for pos in SLOT_ELIG[slot] for p in pr.position_projections(S, pos, week)
                           if not p["bye"]], reverse=True)
            fixed = sum(n_teams * slots.get(pos, 0) for pos in SLOT_ELIG[slot])
            total_avg += (mean(pool[fixed: fixed + n_teams * n]) or 0) * n
    out["lineup_total"], out["league_avg_total"] = sum(p["proj"] for p in starters), total_avg

    # Rest-of-season values for trade logic
    ros = {pid: pr.ros_value(S, pid) for pid in roster}
    starter_ids = {p["pid"] for p in starters}
    for pid in roster:
        b = pr.player_base(S, pid)
        m = b["m"]
        p = projs[pid]
        out["roster_rows"].append({"pid": pid, "p": p, "m": m, "ros": ros[pid], "starter": pid in starter_ids})
        if m.get("regress_pg") is not None and m["regress_pg"] >= 1.5 and m.get("xfp_games", 0) >= 4:
            out["sell"].append({"pid": pid, "p": p, "m": m, "ros": ros[pid], "why": "TD luck"})
    for pid in roster:
        if pid in starter_ids:
            continue
        p = projs[pid]
        g_ = out["grades"].get(p["pos"])
        if g_ and g_["baseline_proj"] and pr.player_base(S, pid)["base"] >= g_["baseline_proj"]:
            out["surplus"].append({"pid": pid, "p": p, "m": pr.player_base(S, pid)["m"], "ros": ros[pid],
                                   "why": "startable depth"})
    needs = sorted([pos for pos, g_ in out["grades"].items() if g_["ratio"] is not None and g_["ratio"] < 1.0],
                   key=lambda pos: out["grades"][pos]["ratio"])
    out["needs"] = needs
    on_roster = set(roster)
    for pos in needs:
        cands = []
        for p in pr.position_projections(S, pos, week):
            if p["pid"] in on_roster:
                continue
            m = pr.player_base(S, p["pid"])["m"]
            worst = min([x["proj"] for x in out["grades"][pos]["players"]] or [0])
            if pr.player_base(S, p["pid"])["base"] <= worst:
                continue
            cands.append({"pid": p["pid"], "p": p, "m": m, "ros": pr.ros_value(S, p["pid"]),
                          "buy_low": (m.get("regress_pg") or 0) <= -1.0})
        cands.sort(key=lambda c: (not c["buy_low"], -c["ros"]))
        out["targets"][pos] = cands[:6]
    chips = {c["pid"]: c for c in out["sell"] + out["surplus"]}.values()
    bench_by_pos = Counter(p["pos"] for p in bench if p["proj"] > 0)
    used_targets = set()
    for chip in sorted(chips, key=lambda c: -c["ros"]):
        cpos = chip["p"]["pos"]
        if cpos in needs:
            continue  # don't weaken a position you already need help at
        if chip["pid"] in starter_ids and bench_by_pos[cpos] == 0:
            continue  # trading him would leave a hole you can't fill
        for pos in needs:
            if cpos == pos:
                continue
            t = next((t for t in out["targets"].get(pos, []) if t["pid"] not in used_targets
                      and chip["ros"] and 0.8 <= t["ros"] / chip["ros"] <= 1.25), None)
            if t:
                out["trades"].append({"give": chip, "get": t, "pos": pos})
                used_targets.add(t["pid"])
                if chip["pid"] in starter_ids:
                    bench_by_pos[cpos] -= 1
                break
    out["trades"] = out["trades"][:6]

    # Bye-week and lineup holes for the rest of the season
    for w in range(week, pr.FANTASY_PLAYOFF_WEEKS[-1] + 1):
        pw = {pid: pr.project_player(S, pid, w, injuries=(w == week)) for pid in roster}
        lu, _ = optimal_lineup(pw, slots)
        holes = [SLOT_LABEL.get(l["slot"], l["slot"]) for l in lu if not l["p"] or l["p"]["proj"] <= 0]
        byes = [p["name"] for p in pw.values() if p and p["bye"]]
        out["byes"].append({"week": w, "holes": holes, "byes": byes,
                            "total": sum(l["p"]["proj"] for l in lu if l["p"]),
                            "playoff": w in pr.FANTASY_PLAYOFF_WEEKS})
    return out


def match_roster_text(S, text):
    """Match pasted lines (e.g. copied from Yahoo) to players."""
    names = {}
    for pid, t in S.season_tot.items():
        names.setdefault(t["name"].lower(), pid)
    for pid, i in S.injuries.items():
        p = S.players.get(pid) or {}
        if p.get("pos") in pr.FANTASY_POS and p.get("name"):
            names.setdefault(p["name"].lower(), pid)
    by_len = sorted(names, key=len, reverse=True)
    found, unmatched = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 4:
            continue
        low = " " + re.sub(r"[^a-z0-9.' -]", " ", line.lower()) + " "
        hit = next((n for n in by_len if f" {n} " in low), None)
        if not hit:
            words = re.sub(r"[^A-Za-z.' -]", " ", line).split()
            guess = " ".join(words[:3]).lower()
            close = difflib.get_close_matches(guess, list(names), n=1, cutoff=0.82) or \
                difflib.get_close_matches(" ".join(words[:2]).lower(), list(names), n=1, cutoff=0.82)
            hit = close[0] if close else None
        if hit:
            found.append(names[hit])
        else:
            unmatched.append(line)
    return list(dict.fromkeys(found)), unmatched


# ------------------------------------------------------------------------------------
# Compare page
# ------------------------------------------------------------------------------------

def range_bar(p, lo, hi):
    span = max(1.0, hi - lo)
    left = (p["floor"] - lo) / span * 100
    width = max(2.0, (p["ceiling"] - p["floor"]) / span * 100)
    mid = (p["proj"] - lo) / span * 100
    return (f'<div style="position:relative;height:14px;background:{BORDER};border-radius:7px;margin:.5rem 0 .2rem">'
            f'<div style="position:absolute;left:{left:.1f}%;width:{width:.1f}%;top:0;bottom:0;'
            f'background:rgba(59,130,246,.45);border-radius:7px"></div>'
            f'<div style="position:absolute;left:calc({mid:.1f}% - 2px);width:4px;top:-3px;bottom:-3px;'
            f'background:{GOLD};border-radius:2px"></div></div>'
            f'<div style="display:flex;justify-content:space-between;font-size:.72rem;color:{MUTED}">'
            f'<span>floor {p["floor"]:.1f}</span><span>ceiling {p["ceiling"]:.1f}</span></div>')


def reasons_html(reasons):
    out = []
    for tone, text in reasons:
        c, ic = {"up": (GREEN, "▲"), "down": (RED, "▼")}.get(tone, (MUTED, "●"))
        out.append(f'<div style="display:flex;gap:.45rem;font-size:.82rem;color:{TEXT};margin:.28rem 0">'
                   f'<span style="color:{c};font-weight:800">{ic}</span><span>{esc(text)}</span></div>')
    return "".join(out)


def verdict(projs):
    ps = sorted([p for p in projs if p], key=lambda p: -p["proj"])
    if len(ps) < 2:
        return None
    a, b = ps[0], ps[1]
    d = a["proj"] - b["proj"]
    if a["proj"] <= 0:
        return ("Neither projects to play this week.", "", RED)
    if d >= 2.5:
        return (f"Start {a['name']}", f"Clear call: {a['proj']:.1f} vs {b['proj']:.1f} projected points.", GREEN)
    if d >= 1.0:
        return (f"Lean {a['name']}", f"{a['proj']:.1f} vs {b['proj']:.1f} projected. Small edge, but an edge.", BLUE)
    safer = max(ps[:2], key=lambda p: p["floor"])
    upside = max(ps[:2], key=lambda p: p["ceiling"])
    if safer["pid"] == upside["pid"]:
        return (f"Slight lean {safer['name']}", f"Nearly even projections, but {safer['name']} has both the higher "
                                                 f"floor and ceiling.", BLUE)
    return ("Toss-up", f"Need a safe week? {safer['name']} has the higher floor. Need a big week to win? "
                       f"{upside['name']} has the higher ceiling.", AMBER)


def page_compare(S):
    H('<div class="fr-title">Compare players</div><div class="fr-sub">Pick 2 to 4 players. <b>This week</b> tells you '
      'who to start; <b>Season</b> compares their production so far.</div>')
    H('<div style="height:.6rem"></div>')
    pids, labels = get_player_list(S, skey(S))
    sel = st.session_state.get("compare_sel") or []
    st.session_state.compare_sel = [p for p in sel if p in labels]
    chosen = st.multiselect("Players", pids, key="compare_sel", format_func=lambda p: labels.get(p, p),
                            max_selections=4, placeholder="Search players to compare...",
                            label_visibility="collapsed")
    if len(chosen) < 2:
        H(f'<div class="fr-card" style="text-align:center;padding:2rem 1rem;margin-top:.8rem">'
          f'<div style="font-size:2rem">⚖️</div><div style="font-weight:800;color:{TEXT};margin:.3rem 0">'
          f'Add at least two players</div><div class="fr-sub">Tip: open any player and tap '
          f'<b>Compare</b> to start from him.</div></div>')
        return
    t1, t2 = st.tabs(["⚡ This week", "📊 Season so far"])
    with t1:
        week = pr.next_week(S)
        projs = [pr.project_player(S, pid, week) for pid in chosen]
        v = verdict(projs)
        if v:
            H(f'<div class="fr-card" style="border-left:5px solid {v[2]};margin-bottom:.8rem">'
              f'<div class="fr-cardh" style="color:{v[2]}">Week {week} verdict</div>'
              f'<div style="font-size:1.45rem;font-weight:800;color:{TEXT}">{esc(v[0])}</div>'
              f'<div class="fr-sub">{esc(v[1])}</div></div>')
        lo = min(p["floor"] for p in projs if p)
        hi = max(p["ceiling"] for p in projs if p)
        cards = []
        best = max(p["proj"] for p in projs if p)
        for p in projs:
            if not p:
                continue
            lab, col = matchup_info(p.get("fpa_rank"), p.get("fpa_n"))
            top = p["proj"] == best and p["proj"] > 0
            info = []
            if p["bye"]:
                info.append(f'<span class="fr-pill" style="background:{R_BG};color:{RED}">BYE</span>')
            else:
                info.append(f'<span class="fr-pill" style="background:{BORDER};color:{col}">{esc(p["label"])} · '
                            f'{lab}</span>')
                if p.get("implied") is not None:
                    info.append(f'<span class="fr-pill" style="background:{BORDER};color:{TEXT}">'
                                f'Team total {p["implied"]:.1f}</span>')
            if p.get("inj_status"):
                info.append(f'<span class="fr-pill" style="background:{R_BG};color:#fecaca">🩹 '
                            f'{esc(p["inj_status"])}</span>')
            cards.append(
                f'<div class="fr-card" style="border-top:3px solid {GOLD if top else BORDER}">'
                f'<div style="display:flex;gap:.6rem;align-items:center">{logo(p["team"], 34)}<div>'
                f'<div style="font-weight:800;color:{TEXT};font-size:1.05rem">{esc(p["name"])}</div>'
                f'<div class="fr-sub" style="margin:0">{p["pos"]} · {esc(p["team"] or "")}</div></div></div>'
                f'<div style="display:flex;align-items:baseline;gap:.4rem;margin-top:.6rem">'
                f'<span style="font-size:2rem;font-weight:800;color:{GOLD if top else TEXT}">{p["proj"]:.1f}</span>'
                f'<span class="fr-sub">projected pts</span></div>'
                f'{range_bar(p, lo, hi) if not p["bye"] else ""}'
                f'<div style="margin:.5rem 0;display:flex;flex-wrap:wrap;gap:.3rem">{"".join(info)}</div>'
                f'<div class="fr-sub" style="margin:.2rem 0 .1rem">Boom chance ({pr.BOOM_BUST[p["pos"]][0]}+): '
                f'<b style="color:{TEXT}">{p["boom_prob"]:.0%}</b></div>'
                f'{reasons_html(p["reasons"])}</div>')
        H(f'<div class="fr-grid {"g2" if len(cards) <= 2 else "g3" if len(cards) == 3 else ""}">{"".join(cards)}</div>')
        st.caption("Projection = his usage (expected points, weighted toward the last 3 games) plus half of his "
                   "efficiency edge, adjusted for the opponent, the Vegas team total and the injury report. "
                   "Floor/ceiling = a bad week and a good week (20th/80th percentile).")
    with t2:
        reps = [get_report(S, skey(S, pid)) for pid in chosen]
        rows = [
            ("Team", [r["team"] for r in reps], None),
            ("Games", [r["prof"]["games"] for r in reps], None),
            ("Total points", [r["prof"]["pts"] for r in reps], True),
            ("Points per game", [r["prof"]["ppg"] for r in reps], True),
            ("Positional rank (PPG)", [f"{r['pos']}{r['m']['rank_ppg']}" if r["m"].get("rank_ppg") else "–"
                                       for r in reps], None),
            ("Expected points / game", [r["m"].get("xfp_pg") for r in reps], True),
            ("Points over expected / game", [r["m"].get("fpoe_pg") for r in reps], True),
            ("TD luck / game", [r["m"].get("td_oe_pg") for r in reps], None),
            ("Last 3 games PPG", [r["prof"]["last3_ppg"] for r in reps], True),
            ("Floor (25th pct)", [r["prof"]["floor"] for r in reps], True),
            ("Ceiling (75th pct)", [r["prof"]["ceiling"] for r in reps], True),
            ("Top-12 weeks", [r["prof"]["top12"] for r in reps], True),
            ("Boom rate", [r["prof"]["boom_rate"] for r in reps], True),
            ("Bust rate", [r["prof"]["bust_rate"] for r in reps], False),
            ("Snap share", [r["m"].get("snap_pct") for r in reps], True),
        ]
        pos_set = {r["pos"] for r in reps}
        if pos_set <= {"WR", "TE"}:
            rows += [("Target share", [r["m"].get("tgt_share") for r in reps], True),
                     ("Air yards share", [r["m"].get("air_share") for r in reps], True),
                     ("Yards per route run", [r["m"].get("yprr") for r in reps], True),
                     ("Red-zone target share", [r["m"].get("rz_tgt_share") for r in reps], True),
                     ("Drop rate", [r["m"].get("r_drop_rate") for r in reps], False)]
        elif pos_set == {"RB"}:
            rows += [("Opportunities / game", [r["m"].get("opp_pg") for r in reps], True),
                     ("Team rush share", [r["m"].get("rush_share") for r in reps], True),
                     ("High-value touches / game", [r["m"].get("hvt_pg") for r in reps], True),
                     ("Target share", [r["m"].get("tgt_share") for r in reps], True),
                     ("Yards per carry", [r["m"].get("ru_ypc") for r in reps], True)]
        elif pos_set == {"QB"}:
            rows += [("EPA / dropback", [r["m"].get("p_epa_per_db") for r in reps], True),
                     ("CPOE", [r["m"].get("p_cpoe") for r in reps], True),
                     ("Rush yards / game", [r["m"].get("rush_ypg") for r in reps], True),
                     ("Points from rushing", [r["m"].get("rush_pts_share") for r in reps], None)]
        pct_rows = {"Boom rate", "Bust rate", "Target share", "Air yards share", "Red-zone target share", "Drop rate",
                    "Team rush share", "Points from rushing"}
        head = "".join(f'<th style="text-align:right;padding:.55rem .7rem">{logo(r["team"], 22)}<br>'
                       f'<span style="color:{TEXT}">{esc(r["name"])}</span></th>' for r in reps)
        body = []
        for lab, vals, higher in rows:
            nums = [v for v in vals if isinstance(v, (int, float))]
            best_v = (max(nums) if higher else min(nums)) if (higher is not None and len(nums) > 1) else None
            cells = []
            for v in vals:
                if isinstance(v, (int, float)):
                    txt = fmt(v, "pct") if lab in pct_rows else fmt(v, "pct100") if lab == "Snap share" else \
                        fmt(v, "dec1s") if "over expected" in lab or "luck" in lab else \
                        fmt(v, "dec2s") if lab == "EPA / dropback" else fmt(v, "dec1") if isinstance(v, float) else str(v)
                else:
                    txt = str(v if v is not None else "–")
                style = f"color:{GREEN};font-weight:800" if best_v is not None and v == best_v else f"color:{TEXT}"
                cells.append(f'<td style="text-align:right;padding:.45rem .7rem;{style}">{esc(txt)}</td>')
            body.append(f'<tr style="border-top:1px solid {BORDER}"><td style="padding:.45rem .7rem;color:{MUTED}">'
                        f'{esc(lab)}</td>{"".join(cells)}</tr>')
        H(f'<div class="fr-card" style="padding:0;overflow-x:auto"><table style="width:100%;border-collapse:collapse;'
          f'font-size:.86rem"><tr><th></th>{head}</tr>{"".join(body)}</table></div>')
        st.caption("Green = best in that row.")
        sec("Weekly fantasy points")
        palette = [GOLD, BLUE, GREEN, "#f472b6"]
        allw = sorted({w["week"] for r in reps for w in r["weekly"]})
        series = []
        for i, r in enumerate(reps):
            byw = {w["week"]: w.get("pts") for w in r["weekly"] if not w.get("status")}
            series.append((r["name"], palette[i], [byw.get(w) for w in allw]))
        plot(line_chart([f"W{w}" for w in allw], series, pct=False, height=320))
        if len(pos_set) == 1:
            pos = next(iter(pos_set))
            keys = [k for k, *_ in pr.RANK_METRICS[pos]][:12]
            labels_r = {k: lab for k, lab, *_ in pr.RANK_METRICS[pos]}
            fig = go.Figure()
            for i, r in enumerate(reps):
                rk = {x["key"]: x for x in r["ranks"]}
                vals = [rk[k]["pct"] if k in rk and rk[k]["pct"] is not None else 0 for k in keys]
                fig.add_scatterpolar(r=vals + vals[:1], theta=[labels_r[k] for k in keys] + [labels_r[keys[0]]],
                                     name=r["name"], line=dict(color=palette[i], width=2), fill="toself",
                                     opacity=0.55)
            fig.update_layout(height=460, margin=dict(l=40, r=40, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#c9d4e3", size=11), legend=dict(orientation="h", y=1.1),
                              polar=dict(bgcolor="rgba(0,0,0,0)",
                                         radialaxis=dict(range=[0, 100], gridcolor=BORDER, showticklabels=False),
                                         angularaxis=dict(gridcolor=BORDER)))
            sec(f"Percentile profile among {pos}s")
            plot(fig)
            st.caption("Each spoke is a league percentile (outer edge = best at his position).")
    glossary(["xFP", "+/- exp", "TD luck", "Floor / ceiling", "Boom / bust", "Implied total", "Defense rank"])


# ------------------------------------------------------------------------------------
# My Teams page
# ------------------------------------------------------------------------------------

def inj_pill(p):
    return (f' <span class="fr-pill" style="background:{R_BG};color:#fecaca">🩹 {esc(p["inj_status"])}</span>'
            if p.get("inj_status") else "")


def player_row_html(p, extra="", right=""):
    return (f'<div class="it"><div style="display:flex;gap:.55rem;align-items:center">{logo(p["team"], 24)}'
            f'<div>{plink(p["pid"], p["name"])}{inj_pill(p)}<div class="sm">{p["pos"]} · {esc(p["team"] or "")} · '
            f'{esc(p["label"] or "")}{extra}</div></div></div><div class="num">{right}</div></div>')


def show_recovery_key():
    key = st.session_state.get("_show_key")
    if not key:
        return
    H(f'<div class="fr-card" style="border-left:5px solid {GOLD};margin-bottom:.8rem">'
      f'<div class="fr-cardh" style="color:{GOLD}">Save your recovery key</div>'
      f'<div style="font-family:ui-monospace,monospace;font-size:1.5rem;font-weight:800;color:{TEXT};'
      f'letter-spacing:.06em;margin:.4rem 0">{esc(key)}</div>'
      f'<div class="fr-sub">If you ever forget your password, this key lets you back in, even without email. '
      f'It is shown only once. Screenshot it or save it in your notes or password manager.</div></div>')
    c1, c2, _ = st.columns([1.2, 1, 3])
    c1.download_button("⬇️ Save as a file", f"Fantasy Reports recovery key\nUsername: "
                       f"{(st.session_state.get('account') or {}).get('display_name', '')}\nKey: {key}\n",
                       file_name="fantasy-reports-recovery-key.txt")
    if c2.button("I've saved it", type="primary"):
        st.session_state.pop("_show_key", None)
        st.rerun()


def auth_panel(db):
    H(f'<div class="fr-card" style="text-align:center;padding:1.6rem 1rem;max-width:620px;margin:.6rem auto 1rem">'
      f'<div style="font-size:2.2rem">🔐</div><div style="font-weight:800;color:{TEXT};font-size:1.25rem;'
      f'margin:.3rem 0">Your teams, private to you</div><div class="fr-sub">Make a free account to save your fantasy '
      f'teams and analyze them anytime. Nobody else can see your teams.</div></div>')
    _, mid, _ = st.columns([1, 2.2, 1])
    acc = Accounts(db)
    with mid:
        t_in, t_up, t_fp = st.tabs(["Sign in", "Create account", "Forgot password"])
        with t_in:
            with st.form("signin"):
                ident = st.text_input("Username or email")
                pw = st.text_input("Password", type="password")
                remember = st.checkbox("Keep me signed in on this device", value=True)
                go_ = st.form_submit_button("Sign in", type="primary", use_container_width=True)
            if go_:
                done = False
                try:
                    a = acc.login(ident, pw)
                    start_session(db, a, remember)
                    done = True
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Couldn't sign in right now: {e}")
                if done:
                    st.rerun()
        with t_up:
            with st.form("signup"):
                un = st.text_input("Username", max_chars=20, help="3-20 letters, numbers, dots, dashes or underscores")
                em = st.text_input("Email", help="Only used to recover your account. Never shown to anyone.")
                p1 = st.text_input("Password", type="password", help="At least 8 characters, mixing letters and numbers")
                p2 = st.text_input("Confirm password", type="password")
                go_ = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if go_:
                if p1 != p2:
                    st.error("The passwords don't match.")
                else:
                    done = False
                    try:
                        a, key = acc.signup(un, em, p1)
                        start_session(db, a, True)
                        st.session_state._show_key = key
                        done = True
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Couldn't create the account right now: {e}")
                    if done:
                        st.rerun()
        with t_fp:
            mc = mail_config()
            options = (["Email me a code", "Use my recovery key"] if mc else ["Use my recovery key"])
            how = st.radio("How do you want to reset it?", options, horizontal=True, key="fp_how")
            if how == "Email me a code":
                with st.form("fp_send"):
                    ident = st.text_input("Username or email", key="fp_ident")
                    send = st.form_submit_button("Send code")
                if send:
                    try:
                        acc.send_code(ident, mc)
                        st.session_state._code_sent = (ident or "").strip()
                    except Exception as e:
                        st.error(f"Couldn't send the email right now: {e}")
                if st.session_state.get("_code_sent"):
                    st.info(f"If an account matches, a 6-digit code is on its way to the email on file. "
                            f"It expires in {CODE_MINUTES} minutes; check spam too.")
                    with st.form("fp_code"):
                        code = st.text_input("6-digit code", max_chars=7)
                        n1 = st.text_input("New password", type="password")
                        n2 = st.text_input("Confirm new password", type="password")
                        ok = st.form_submit_button("Reset password", type="primary")
                    if ok:
                        if n1 != n2:
                            st.error("The passwords don't match.")
                        else:
                            done = False
                            try:
                                a = acc.reset_with_code(st.session_state._code_sent, code, n1)
                                st.session_state.pop("_code_sent", None)
                                start_session(db, a, True)
                                st.session_state._flash = "Password reset. You're signed in."
                                done = True
                            except ValueError as e:
                                st.error(str(e))
                            if done:
                                st.rerun()
            else:
                if not mc:
                    st.caption("Use the recovery key you saved when you made your account.")
                with st.form("fp_key"):
                    ident = st.text_input("Username or email", key="fk_ident")
                    key = st.text_input("Recovery key", placeholder="XXXXX-XXXXX-XXXXX-XXXXX")
                    n1 = st.text_input("New password", type="password", key="fk_n1")
                    n2 = st.text_input("Confirm new password", type="password", key="fk_n2")
                    ok = st.form_submit_button("Reset password", type="primary")
                if ok:
                    if n1 != n2:
                        st.error("The passwords don't match.")
                    else:
                        done = False
                        try:
                            a, new_key = acc.reset_with_key(ident, key, n1)
                            start_session(db, a, True)
                            st.session_state._show_key = new_key
                            st.session_state._flash = "Password reset. Your old recovery key no longer works; " \
                                                      "here's your new one."
                            done = True
                        except ValueError as e:
                            st.error(str(e))
                        if done:
                            st.rerun()
    H(f'<div class="fr-foot">Passwords are stored as one-way hashes; nobody, including the site owner, can read '
      f'them. Your email is only used for password resets.</div>')


def account_settings(db):
    a = st.session_state.get("account")
    if not a:
        return
    acc = Accounts(db)
    with st.expander(f"⚙️ Account settings · signed in as {a['display_name']}"):
        st.caption(f"Email on file: {a['email']}")
        t1, t2, t3, t4 = st.tabs(["Password", "Email", "Recovery key", "Delete account"])
        with t1:
            with st.form("chpw"):
                cur = st.text_input("Current password", type="password")
                n1 = st.text_input("New password", type="password")
                n2 = st.text_input("Confirm new password", type="password")
                ok = st.form_submit_button("Change password")
            if ok:
                try:
                    if n1 != n2:
                        raise ValueError("The new passwords don't match.")
                    acc.change_password(a, cur, n1)
                    st.success("Password changed.")
                except ValueError as e:
                    st.error(str(e))
        with t2:
            with st.form("chem"):
                em = st.text_input("New email", value=a["email"])
                cur = st.text_input("Current password", type="password", key="chem_pw")
                ok = st.form_submit_button("Update email")
            if ok:
                try:
                    st.session_state.account["email"] = acc.change_email(a, cur, em)
                    st.success("Email updated.")
                except ValueError as e:
                    st.error(str(e))
        with t3:
            st.caption("Lost your recovery key? Make a new one. The old key stops working.")
            with st.form("newkey"):
                cur = st.text_input("Current password", type="password", key="nk_pw")
                ok = st.form_submit_button("Create a new recovery key")
            if ok:
                done = False
                try:
                    st.session_state._show_key = acc.new_key(a, cur)
                    done = True
                except ValueError as e:
                    st.error(str(e))
                if done:
                    st.rerun()
        with t4:
            st.caption("Permanently deletes your account and every saved team.")
            with st.form("delacct"):
                confirm = st.text_input(f"Type your username ({a['display_name']}) to confirm")
                cur = st.text_input("Current password", type="password", key="del_pw")
                ok = st.form_submit_button("Delete my account")
            if ok:
                if confirm.strip().lower() != a["username"]:
                    st.error("The username doesn't match.")
                else:
                    done = False
                    try:
                        acc.delete_account(a, cur)
                        sign_out()
                        st.session_state._flash = "Your account and teams were deleted."
                        done = True
                    except ValueError as e:
                        st.error(str(e))
                    if done:
                        st.rerun()
        if st.button("Sign out", key="so_settings"):
            sign_out()
            st.rerun()


def teams_login_gate():
    """Returns (owner, store) or (None, None) if the page should stop."""
    flash = st.session_state.pop("_flash", None)
    if flash:
        st.success(flash)
    db = get_db()
    if db:
        a = st.session_state.get("account")
        if a:
            show_recovery_key()
            return a["id"], TeamStore(db)
        auth_panel(db)
        return None, None
    H(f'<div class="fr-card" style="border-left:4px solid {AMBER};margin-bottom:.8rem"><b style="color:{TEXT}">'
      f'Guest mode.</b> <span class="fr-sub">Accounts aren\'t set up on this site yet, so teams only last until you '
      f'close this tab. Follow the setup guide to turn on accounts and saved teams.</span></div>')
    return "guest", SessionStore()


def team_editor(S, store, owner, existing):
    data = (existing or {}).get("data") or {}
    pids, labels = get_player_list(S, skey(S))
    extra = {pid: f"{(S.players.get(pid) or {}).get('name')}  ·  {(S.players.get(pid) or {}).get('pos')}  ·  "
                  f"{(S.players.get(pid) or {}).get('team')}  ·  (no games yet)"
             for pid, inj in S.injuries.items() if pid not in labels
             and (S.players.get(pid) or {}).get("pos") in pr.FANTASY_POS}
    all_labels = {**labels, **extra}
    options = pids + list(extra)
    if "edit_roster" not in st.session_state:
        st.session_state.edit_roster = [p for p in data.get("roster", []) if p in all_labels]
    add = st.session_state.pop("_roster_add", None)
    if add:
        st.session_state.edit_roster = list(dict.fromkeys(st.session_state.edit_roster + add))[:MAX_ROSTER]

    H(f'<div class="fr-title">{"Edit team" if existing else "New team"}</div>')
    with st.expander("📋 Paste your roster (fastest way)", expanded=not existing):
        st.caption("In Yahoo, open your team page, select the roster and copy it, then paste it here. One player per "
                   "line also works. Extra text on each line is ignored.")
        txt = st.text_area("Roster text", height=160, label_visibility="collapsed", key="roster_paste",
                           placeholder="Josh Allen\nBijan Robinson\nJa'Marr Chase\n...")
        if st.button("Find these players"):
            found, unmatched = match_roster_text(S, txt or "")
            st.session_state._roster_add = found
            st.session_state._roster_msg = (len(found), unmatched[:12])
            st.rerun()
        msg = st.session_state.pop("_roster_msg", None)
        if msg:
            st.success(f"Added {msg[0]} players. Check the roster box below.")
            if msg[1]:
                st.caption("Couldn't match: " + "; ".join(msg[1]) + ". Add those with the search box.")
    c1, c2, c3 = st.columns([2, 1, 1])
    name = c1.text_input("Team name", value=data.get("name", ""), max_chars=60, placeholder="e.g. Sunday Funday")
    scoring = c2.selectbox("Scoring", list(FORMATS), index=list(FORMATS.values()).index(data.get("scoring", S.fmt_name)))
    n_teams = c3.number_input("Teams in league", 6, 20, int(data.get("teams_in_league", 12)))
    st.caption("Starting lineup slots (Yahoo default shown; kickers and defenses aren't analyzed)")
    sl = {**DEFAULT_SLOTS, **(data.get("slots") or {})}
    cols = st.columns(6)
    new_slots = {}
    for c, key in zip(cols, ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"]):
        new_slots[key] = c.number_input(SLOT_LABEL.get(key, key), 0, 4, int(sl.get(key, 0)), key=f"slot_{key}")
    roster = st.multiselect("Roster", options, key="edit_roster", format_func=lambda p: all_labels.get(p, p),
                            max_selections=MAX_ROSTER, placeholder="Search players to add...")
    st.caption(f"{len(roster)} players")
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("💾 Save team", type="primary", use_container_width=True):
        if not name.strip():
            st.error("Give the team a name.")
        elif not roster:
            st.error("Add at least one player.")
        else:
            body = {"name": name.strip(), "scoring": FORMATS[scoring], "teams_in_league": int(n_teams),
                    "slots": new_slots, "roster": roster,
                    "names": {p: (S.players.get(p) or {}).get("name") or all_labels.get(p, p) for p in roster}}
            try:
                tid = store.save(owner, (existing or {}).get("id"), body)
            except Exception as e:
                st.error(f"Couldn't save: {e}")
                return
            st.session_state.team_sel = tid
            st.session_state.team_mode = "view"
            st.session_state.pop("edit_roster", None)
            list_teams.clear()
            st.rerun()
    if b2.button("Cancel", use_container_width=True):
        st.session_state.team_mode = "view"
        st.session_state.pop("edit_roster", None)
        st.rerun()


@st.cache_data(ttl=60, show_spinner=False)
def _list_cached(owner, _store, nonce):
    return _store.list(owner)


def list_teams(owner, store):
    if not store.persistent:
        return store.list(owner)
    return _list_cached(owner, store, st.session_state.get("_teams_nonce", 0))


list_teams.clear = lambda: st.session_state.__setitem__("_teams_nonce", st.session_state.get("_teams_nonce", 0) + 1)


def page_teams(S, season):
    owner, store = teams_login_gate()
    if not owner:
        return
    try:
        teams = list_teams(owner, store)
    except Exception as e:
        st.error(f"Couldn't load your teams: {e}")
        return
    mode = st.session_state.get("team_mode", "view")
    if mode == "new":
        if len(teams) >= MAX_TEAMS:
            st.warning(f"You can save up to {MAX_TEAMS} teams.")
        else:
            team_editor(S, store, owner, None)
            return
    if not teams:
        H(f'<div class="fr-title">My teams</div>')
        H(f'<div class="fr-card" style="text-align:center;padding:2.2rem 1rem;margin-top:.8rem">'
          f'<div style="font-size:2.2rem">🏈</div><div style="font-weight:800;color:{TEXT};font-size:1.15rem;'
          f'margin:.3rem 0">Add your first team</div><div class="fr-sub">Paste your Yahoo roster and get start/sit '
          f'calls, position grades, trade ideas and bye-week warnings.</div></div>')
        c = st.columns([1, 1, 1])
        if c[1].button("➕ Create a team", type="primary", use_container_width=True):
            st.session_state.team_mode = "new"
            st.session_state.pop("edit_roster", None)
            st.rerun()
        return
    by_id = {t["id"]: t for t in teams}
    if st.session_state.get("team_sel") not in by_id:
        st.session_state.team_sel = teams[0]["id"]
    if mode == "edit":
        team_editor(S, store, owner, by_id[st.session_state.team_sel])
        return
    top = st.columns([3, 1, 1, 1])
    tid = top[0].selectbox("Team", list(by_id), key="team_sel", format_func=lambda t: by_id[t]["name"],
                           label_visibility="collapsed")
    if top[1].button("➕ New", use_container_width=True):
        st.session_state.team_mode = "new"
        st.session_state.pop("edit_roster", None)
        st.rerun()
    if top[2].button("✏️ Edit", use_container_width=True):
        st.session_state.team_mode = "edit"
        st.session_state.pop("edit_roster", None)
        st.rerun()
    if top[3].button("🗑️ Delete", use_container_width=True):
        st.session_state._confirm_delete = tid
    if st.session_state.get("_confirm_delete") == tid:
        st.warning(f"Delete **{by_id[tid]['name']}**? This can't be undone.")
        d1, d2, _ = st.columns([1, 1, 3])
        if d1.button("Yes, delete", type="primary"):
            try:
                store.delete(owner, tid)
            except Exception as e:
                st.error(f"Couldn't delete: {e}")
                return
            st.session_state.pop("_confirm_delete", None)
            st.session_state.pop("team_sel", None)
            list_teams.clear()
            st.rerun()
        if d2.button("Keep it"):
            st.session_state.pop("_confirm_delete", None)
            st.rerun()
    team = by_id[tid]["data"]
    TS = get_season(season, team.get("scoring", S.fmt_name)) if team.get("scoring", S.fmt_name) != S.fmt_name else S
    with st.spinner("Analyzing your team..."):
        A = analyze_team(TS, team)
    render_team(TS, team, A)


def render_team(S, team, A):
    week = A["week"]
    lt, la = A.get("lineup_total"), A.get("league_avg_total")
    edge = div(lt - la, la) if (lt is not None and la) else None
    head_col = GREEN if (edge or 0) >= 0.05 else RED if (edge or 0) <= -0.05 else AMBER
    grades = A["grades"]
    H(f'<div class="fr-hero" style="background:linear-gradient(115deg,#1e3a5f 0%,{CARD} 100%);border-left:6px solid {GOLD}">'
      f'<div><div class="nm">{esc(team["name"])}</div>'
      f'<div><span class="fr-chip">{pr.FORMAT_LABEL[team.get("scoring", "half")].replace(" scoring", "")}</span>'
      f'<span class="fr-chip">{A["n_teams"]}-team league</span><span class="fr-chip">{len(team["roster"])} players'
      f'</span></div></div>'
      f'<div class="fr-badge"><div class="big" style="color:{head_col}">{fmt(lt, "dec1")}</div>'
      f'<div class="lab">Week {week} projection</div></div></div>')
    if A["missing"]:
        st.caption(f"{len(A['missing'])} rostered player(s) have no data this season and are skipped.")
    if not week:
        st.info("The regular season is over.")
        return
    cards = [kpi("Lineup vs league average", f"{edge * 100:+.0f}%" if edge is not None else "–",
                 f"Average {A['n_teams']}-team lineup: {fmt(la, 'dec1')}", head_col)]
    for pos, g_ in grades.items():
        gr, col = g_["grade"]
        cards.append(kpi(f"{pos} grade", gr, f"{fmt(g_['mine'], 'dec1')} vs {fmt(g_['avg'], 'dec1')} avg starter", col,
                         col))
    H(f'<div class="fr-grid g5">{"".join(cards)}</div>')
    tabs = st.tabs([f"📋 Week {week} lineup", "🔁 Trade ideas", "🗓️ Byes & schedule", "👥 Roster"])
    with tabs[0]:
        notes = list(A["alerts"])
        for c in A["close"]:
            if c["safer"]["pid"] != c["upside"]["pid"]:
                notes.append(("info", f"Close call at {SLOT_LABEL.get(c['slot'], c['slot'])}: {c['start']['name']} "
                                      f"({c['start']['proj']:.1f}) vs {c['bench']['name']} ({c['bench']['proj']:.1f}). "
                                      f"Safer: {c['safer']['name']}. Higher ceiling: {c['upside']['name']}."))
            else:
                notes.append(("info", f"Close call at {SLOT_LABEL.get(c['slot'], c['slot'])}: {c['start']['name']} "
                                      f"edges {c['bench']['name']} ({c['start']['proj']:.1f} vs "
                                      f"{c['bench']['proj']:.1f})."))
        if notes:
            H(notes_html(notes))
            H('<div style="height:.6rem"></div>')
        left, right = st.columns([3, 2])
        with left:
            sec("Start")
            items = []
            for l in A["lineup"]:
                p = l["p"]
                slot = SLOT_LABEL.get(l["slot"], l["slot"])
                if not p:
                    items.append(f'<div class="it"><div><b style="color:{RED}">{slot}</b> <span class="sm">empty</span>'
                                 f'</div></div>')
                    continue
                lab, col = matchup_info(p.get("fpa_rank"), p.get("fpa_n"))
                items.append(
                    f'<div class="it"><div style="display:flex;gap:.6rem;align-items:center">'
                    f'<span class="fr-pill" style="background:{BORDER};color:{TEXT};min-width:52px;text-align:center">'
                    f'{slot}</span>{logo(p["team"], 24)}<div>{plink(p["pid"], p["name"])}{inj_pill(p)}'
                    f'<div class="sm">{p["pos"]} · {esc(p["label"])} · <span style="color:{col}">{lab}</span> · '
                    f'{p["floor"]:.1f}–{p["ceiling"]:.1f}</div></div></div>'
                    f'<div class="num" style="color:{GOLD}">{p["proj"]:.1f}</div></div>')
            H(f'<div class="fr-card"><div class="fr-list">{"".join(items)}</div></div>')
        with right:
            sec("Bench")
            items = [player_row_html(p, right=f'<span style="color:{MUTED}">{p["proj"]:.1f}</span>')
                     for p in A["bench"]]
            H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class='sm'>Empty</div>"}</div></div>')
        st.caption("Lineup = highest projection at every slot. Range = floor to ceiling. Tap a name for his full report, "
                   "or use Compare for a head-to-head.")
    with tabs[1]:
        needs = A.get("needs", [])
        if needs:
            H(notes_html([("down", f"Weakest spot: {pos} (your starters project "
                                   f"{A['grades'][pos]['mine']:.1f} vs {A['grades'][pos]['avg']:.1f} for an average "
                                   f"{pos} starter).") for pos in needs[:2]]))
        else:
            H(notes_html([("up", "Every starting spot projects at or above an average starter in your league.")]))
        if A["trades"]:
            sec("Trade ideas")
            items = []
            for t in A["trades"]:
                g_, r_ = t["give"], t["get"]
                items.append(
                    f'<div class="fr-card" style="margin-bottom:.5rem"><div style="display:flex;flex-wrap:wrap;gap:.8rem;'
                    f'align-items:center;justify-content:space-between">'
                    f'<div><div class="fr-cardh" style="color:{RED}">Give</div>{logo(g_["p"]["team"], 22)} '
                    f'{plink(g_["pid"], g_["p"]["name"])}<div class="sm" style="color:{MUTED};font-size:.76rem">'
                    f'{g_["p"]["pos"]} · {esc(g_["why"])} · {g_["ros"]:.0f} pts rest of season</div></div>'
                    f'<div style="font-size:1.4rem;color:{MUTED}">⇄</div>'
                    f'<div><div class="fr-cardh" style="color:{GREEN}">Get</div>{logo(r_["p"]["team"], 22)} '
                    f'{plink(r_["pid"], r_["p"]["name"])}<div class="sm" style="color:{MUTED};font-size:.76rem">'
                    f'{r_["p"]["pos"]} · {"buy-low · " if r_["buy_low"] else ""}{r_["ros"]:.0f} pts rest of season</div>'
                    f'</div></div></div>')
            H('<div class="fr-list">' + "".join(items) + "</div>")
            st.caption("Pairs a player you can spare (surplus depth or TD-luck sell-high) with a similar-value upgrade "
                       "at your weakest position. The site can't see other rosters, so check who owns the target.")
        c1, c2 = st.columns(2)
        with c1:
            sec("Sell-high candidates on your roster")
            items = [player_row_html(x["p"], f' · {x["m"]["td_oe_pg"]:+.1f} pts/g from TD luck',
                                     f'<span style="color:{RED}">{x["m"]["regress_pg"]:+.1f}</span>') for x in A["sell"]]
            H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class='sm'>None. Nobody is running hot on touchdowns.</div>"}</div></div>')
            sec("Surplus depth (startable on most teams)")
            items = [player_row_html(x["p"], "", f'<span style="color:{BLUE}">{x["ros"]:.0f} ROS</span>')
                     for x in A["surplus"]]
            H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class='sm'>No spare starters on the bench.</div>"}</div></div>')
        with c2:
            for pos in needs[:2]:
                sec(f"{pos} upgrade targets")
                items = [player_row_html(x["p"], " · buy-low" if x["buy_low"] else "",
                                         f'<span style="color:{GREEN}">{x["ros"]:.0f} ROS</span>')
                         for x in A["targets"].get(pos, [])]
                H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class='sm'>No clear upgrades found.</div>"}</div></div>')
        st.caption("ROS = projected points for the rest of the season through the fantasy playoffs, matchups included.")
    with tabs[2]:
        sec("Projected lineup by week")
        tiles = []
        for b in A["byes"]:
            col = RED if b["holes"] else GREEN
            tiles.append(f'<div class="fr-wk" style="--c:{col}"><div class="w">Week {b["week"]}{" ★" if b["playoff"] else ""}'
                         f'</div><div class="o">{b["total"]:.0f}</div><div class="r">'
                         f'{"Hole: " + ", ".join(b["holes"]) if b["holes"] else "Full lineup"}</div></div>')
        H(f'<div class="fr-sched">{"".join(tiles)}</div>')
        warn = [("down", f"Week {b['week']}: no healthy option at {', '.join(b['holes'])}"
                         f"{' (' + ', '.join(b['byes']) + ' on bye)' if b['byes'] else ''}. Plan a pickup.")
                for b in A["byes"] if b["holes"]]
        byes_only = [("info", f"Week {b['week']} byes: {', '.join(b['byes'])}.") for b in A["byes"]
                     if b["byes"] and not b["holes"]]
        H('<div style="height:.6rem"></div>')
        H(notes_html(warn + byes_only) if (warn or byes_only) else
          notes_html([("up", "No bye-week holes the rest of the way.")]))
        st.caption("Number = projected lineup total that week. ★ = fantasy playoffs.")
    with tabs[3]:
        rows = []
        for r in sorted(A["roster_rows"], key=lambda r: (-r["starter"], -r["p"]["proj"])):
            p, m = r["p"], r["m"]
            tot = S.season_tot.get(r["pid"], {})
            rows.append({"Logo": logo_url(p["team"]), "Player": p["name"], "Pos": p["pos"],
                         "Status": "Starter" if r["starter"] else "Bench",
                         f"Wk {A['week']} proj": round(p["proj"], 1), "Opponent": p["label"],
                         "PPG": m.get("ppg"), "Pos rank": f"{p['pos']}{tot['rank_ppg']}" if tot.get("rank_ppg") else "–",
                         "xFP/G": m.get("xfp_pg"), "TD luck/G": m.get("td_oe_pg"), "ROS pts": round(r["ros"]),
                         "Injury": p.get("inj_status") or ""})
        styled_df(pd.DataFrame(rows), cell={"TD luck/G": lambda v: (RED if v >= 1.5 else GREEN if v <= -1 else None)
                                            if isinstance(v, (int, float)) and pd.notna(v) else None},
                  column_config={"Logo": st.column_config.ImageColumn(" ", width="small")})
    glossary(["ROS", "xFP", "TD luck", "PPG", "Floor / ceiling", "Defense rank", "Implied total"])


# ------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------

def main():
    H(CSS)
    restore_session()
    pend = st.session_state.pop("pending", None)
    if pend:
        if pend.get("player"):
            st.session_state.player = pend["player"]
        if pend.get("compare") is not None:
            st.session_state.compare_sel = pend["compare"]
        st.session_state.view = pend["view"]
        for k in [k for k in st.session_state if k == "home_search" or str(k).startswith("rank_table_")]:
            del st.session_state[k]  # clear the search box and table selection that triggered the jump
    if "view" not in st.session_state:
        st.session_state.view = "Player" if st.query_params.get("player") else "Home"

    qp = st.query_params
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        try:
            s_default = SEASONS.index(int(qp.get("season", pr.SEASON)))
        except ValueError:
            s_default = 0
        season = st.selectbox("Season", SEASONS, index=s_default)
        f_default = next((i for i, v in enumerate(FORMATS.values()) if v == qp.get("scoring", pr.SCORING_FORMAT)), 0)
        scoring = FORMATS[st.radio("Scoring", list(FORMATS), index=f_default)]
        st.caption("Point values come from the SETTINGS block in player_report.py.")
        if get_db():
            st.markdown("### 👤 Account")
            acct = st.session_state.get("account")
            if acct:
                st.caption(f"Signed in as **{acct['display_name']}**")
                if st.button("Sign out", use_container_width=True):
                    sign_out()
                    st.rerun()
            else:
                st.caption("Sign in on the **My Teams** page to save teams.")
        if st.button("🔄 Refresh data now", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()
    if season != pr.SEASON:
        qp["season"] = str(season)
    else:
        qp.pop("season", None)
    if scoring != pr.SCORING_FORMAT:
        qp["scoring"] = scoring
    else:
        qp.pop("scoring", None)

    try:
        with st.spinner("Loading league data... the first visit after the site wakes up takes about a minute."):
            S = get_season(season, scoring)
    except Exception as e:
        st.error(f"Couldn't load {season} data: {type(e).__name__}: {e}")
        st.caption("Open the sidebar (top-left arrow) and tap **Refresh data now** in a few minutes.")
        st.stop()

    view = segmented("View", VIEWS, "view", "Home", lambda v: f"{VIEW_ICONS[v]} {v}")
    if view != "Player":
        qp.pop("player", None)
    H('<div style="height:.4rem"></div>')
    if view == "My Teams":
        page_teams(S, season)
        if get_db() and st.session_state.get("account"):
            H('<div style="height:1rem"></div>')
            account_settings(get_db())
    else:
        {"Home": page_home, "Player": page_player, "Compare": page_compare, "Rankings": page_rankings,
         "Defense": page_defense}[view](S)

    notes = " · ".join(S.notes)
    H(f'<div class="fr-foot">Data: nflverse (play-by-play, FTN charting, Next Gen Stats, ffopportunity) · '
      f'updated {S.loaded_at:%b %d, %I:%M %p} · refreshes every {pr.CACHE_HOURS} hours'
      f'{"<br>" + esc(notes) if notes else ""}</div>')


main()
