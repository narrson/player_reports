"""
Fantasy Player Reports: website version.

Run on your computer:   streamlit run app.py
Hosted on:              Streamlit Community Cloud (files: app.py, player_report.py, requirements.txt,
                        .streamlit/config.toml)

All the stats come from player_report.py, which must sit in the same folder.
"""

import html
import os
import tempfile
from datetime import datetime
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
VIEWS = ["Home", "Player", "Rankings", "Defense"]
VIEW_ICONS = {"Home": "🏠", "Player": "👤", "Rankings": "📊", "Defense": "🛡️"}
fmt = pr.fmt
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
    out = {"fpoe": [], "trend": [], "week_top": [], "matchups": {}, "next_week": None}
    for pos in pr.FANTASY_POS:
        pool, _ = pr.position_pool(S, pos)
        for pid, m in pool.items():
            t = S.season_tot[pid]
            base = {"pid": pid, "name": t["name"], "pos": pos, "team": t["team"], "ppg": m["ppg"]}
            if m.get("fpoe_pg") is not None and (m.get("xfp_pg") or 0) >= 7 and m.get("xfp_games", 0) >= 3:
                out["fpoe"].append({**base, "val": m["fpoe_pg"], "xfp": m["xfp_pg"]})
            weeks = pr.player_weeks(S, pid)
            if len(weeks) >= 4 and m.get("xfp_pg") is not None:
                l3 = pr.player_metrics(S, pid, pos, weeks[-3:])
                if l3.get("xfp_pg") is not None:
                    out["trend"].append({**base, "val": l3["xfp_pg"] - m["xfp_pg"], "l3": l3["xfp_pg"],
                                         "season": m["xfp_pg"]})
    rows = [r for rs in S.weekly.values() for r in rs if r["week"] == S.last_week]
    out["week_top"] = sorted(rows, key=lambda r: -r["pts"])[:12]
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
    H(f"""
    <div class="fr-hero" style="background: linear-gradient(115deg, {c1} 0%, {c1}cc 38%, {CARD} 100%);
         border-left: 6px solid {c2};">
      <div>
        <div class="nm">{esc(rep['name'])}</div>
        <div>{chip_html}</div>
        <div class="meta">{esc(meta)}</div>
      </div>
      <div class="fr-badge"><div class="big" style="color:{tier_color(rk) if rk else TEXT}">{pos}{rk if rk else "–"}</div>
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
    f = m.get("fpoe_pg")
    f_col = GREEN if (f or 0) >= 1 else RED if (f or 0) <= -1 else TEXT
    f_sub = ("Running hot: sell-high zone" if (f or 0) >= 3 else "Under-producing usage: buy-low"
             if (f or 0) <= -2 else "Production matches usage" if f is not None else "&nbsp;")
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


def tab_overview(rep):
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
            out.append({"Wk": w["week"], "Opp": w["status"]})
            continue
        r = {"Wk": w["week"], "Opp": w.get("opp", ""), "Pts": round(w.get("pts") or 0, 1),
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
    styled_df(df, row_bg=lambda r: "rgba(100,116,139,.12)" if r.get("Opp") in ("BYE", "Did not play") else None,
              cell={"Finish": finish_color, "+/-": num_sign_color})
    st.caption("Finish = positional rank that week. xFP = expected points from usage; +/- = actual minus expected. "
               "Route% = share of team dropbacks he was on the field for. HVT = targets + carries inside the 10.")
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
          <div class="teams"><span class="fr-tm" style="background:{t1};--s:{t1s}">{esc(rep['team'])}</span>
            <span style="color:{MUTED};font-weight:700">{'vs' if nx['home'] else '@'}</span>
            <span class="fr-tm" style="background:{t2};--s:{t2s}">{esc(nx['opp'])}</span>
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
                             f'<div class="o">BYE</div><div class="r">&nbsp;</div></div>')
                continue
            lab, col = matchup_info(u.get("fpa_rank"), u.get("fpa_n"))
            tiles.append(f'<div class="fr-wk" style="--c:{col}"><div class="w">Week {wk}{" ★" if u["playoff"] else ""}</div>'
                         f'<div class="o">{esc(u["label"])}</div>'
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
    hero(rep)
    kpi_grid(rep)
    H('<div style="height:.9rem"></div>')
    tabs = st.tabs(["📈 Overview", "🗓️ Week by week", "🆚 Matchups", "🏅 League ranks", "🧩 Splits", "🎬 Plays"])
    for t, fn in zip(tabs, (tab_overview, tab_weekly, tab_matchups, tab_ranks, tab_splits, tab_plays)):
        with t:
            fn(rep)
    st.divider()
    pdf_button(rep)


# ------------------------------------------------------------------------------------
# Home dashboard
# ------------------------------------------------------------------------------------

def list_card(title, desc, color, items):
    body = "".join(items) if items else '<div class="fr-sub" style="padding:.5rem 0">Not enough data yet.</div>'
    return (f'<div class="fr-card" style="border-top:3px solid {color}"><div class="fr-cardh" style="color:{color}">'
            f'{esc(title)}</div><div class="fr-cardd">{esc(desc)}</div><div class="fr-list">{body}</div></div>')


def list_item(pid, name, sub, num, color):
    return (f'<div class="it"><div>{plink(pid, name)}<div class="sm">{esc(sub)}</div></div>'
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
    fp, tr = d["fpoe"], d["trend"]
    buy = sorted(fp, key=lambda x: x["val"])[:6]
    sell = sorted(fp, key=lambda x: -x["val"])[:6]
    rising = sorted([x for x in tr if x["val"] > 0], key=lambda x: -x["val"])[:6]
    falling = sorted([x for x in tr if x["val"] < 0], key=lambda x: x["val"])[:6]

    def sub_fp(x):
        return f"{x['pos']} · {x['team']} · {x['ppg']:.1f} PPG on {x['xfp']:.1f} expected"

    def sub_tr(x):
        return f"{x['pos']} · {x['team']} · {x['l3']:.1f} xFP last 3 vs {x['season']:.1f}"
    sec("Buy, sell and trends")
    H('<div class="fr-grid g2">' + "".join([
        list_card("Buy low", "Scoring well below what his usage predicts", GREEN,
                  [list_item(x["pid"], x["name"], sub_fp(x), f"{x['val']:+.1f}", GREEN) for x in buy]),
        list_card("Sell high", "Scoring well above what his usage predicts", RED,
                  [list_item(x["pid"], x["name"], sub_fp(x), f"{x['val']:+.1f}", RED) for x in sell]),
        list_card("Usage rising", "Expected points, last 3 games vs season", BLUE,
                  [list_item(x["pid"], x["name"], sub_tr(x), f"▲ {x['val']:.1f}", BLUE) for x in rising]),
        list_card("Usage falling", "Expected points, last 3 games vs season", AMBER,
                  [list_item(x["pid"], x["name"], sub_tr(x), f"▼ {abs(x['val']):.1f}", AMBER) for x in falling]),
    ]) + "</div>")

    sec(f"Week {S.last_week} top scorers")
    items = [list_item(r["pid"], r["name"], f"{r['pos']}{r.get('rank', '')} · {r['team']}"
                                            f"{' vs ' + r['opp'] if r.get('opp') else ''}",
                       f"{r['pts']:.1f}", tier_color(r.get("rank"))) for r in d["week_top"]]
    half = (len(items) + 1) // 2
    H(f'<div class="fr-grid g2"><div class="fr-card"><div class="fr-list">{"".join(items[:half])}</div></div>'
      f'<div class="fr-card"><div class="fr-list">{"".join(items[half:])}</div></div></div>')

    if d["next_week"]:
        sec(f"Best matchups in week {d['next_week']}")
        cards = []
        for pos in pr.FANTASY_POS:
            its = []
            for x in d["matchups"].get(pos, []):
                lab, col = matchup_info(x["rank"], x["n"])
                its.append(f'<div class="it"><div><b style="color:{TEXT}">{esc(x["off"])} {pos}s</b>'
                           f'<div class="sm">vs {esc(x["def"])} · allows {x["avg"]:.1f} / game</div></div>'
                           f'<div class="num" style="color:{col}">{pr.ordinal(x["rank"])}</div></div>')
            cards.append(list_card(f"{pos}s", "Facing the defenses that allow the most", GOLD, its))
        H(f'<div class="fr-grid">{"".join(cards)}</div>')
    H('<div class="fr-foot">Buy/sell lists include players averaging 7+ expected points. Tap any name to open his '
      'report.</div>')


# ------------------------------------------------------------------------------------
# Rankings and defense pages
# ------------------------------------------------------------------------------------

RANK_COLS = {
    "WR": [("Tgt share", "tgt_share", 100), ("Air share", "air_share", 100), ("WOPR", "wopr", 1),
           ("Route %", "route_pct", 100), ("YPRR", "yprr", 1), ("TPRR", "tprr", 100), ("aDOT", "r_adot", 1),
           ("Drop %", "r_drop_rate", 100)],
    "RB": [("Opp / g", "opp_pg", 1), ("Rush share", "rush_share", 100), ("HVT / g", "hvt_pg", 1),
           ("Inside-10 sh", "i10_share", 100), ("Tgt share", "tgt_share", 100), ("YPC", "ru_ypc", 1),
           ("Rush EPA", "ru_epa_per", 1), ("Stuff %", "ru_stuff_rate", 100)],
    "QB": [("Dropbacks / g", "p_dropbacks_pg", 1), ("EPA / DB", "p_epa_per_db", 1), ("CPOE", "p_cpoe", 1),
           ("ANY/A", "p_any_a", 1), ("Rush yds / g", "rush_ypg", 1), ("Scrambles / g", "p_scrambles_pg", 1),
           ("Sack %", "p_sack_rate", 100), ("INT %", "p_int_rate", 100)],
}
RANK_COLS["TE"] = RANK_COLS["WR"]


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
    H('<div class="fr-title">Rankings</div><div class="fr-sub">Sorted by points per game. Tap a column header to '
      'sort, tap a row to open his report. Sort by <b>+/- exp</b> to find buy-low (most negative) and sell-high '
      '(most positive) players.</div>')
    H('<div style="height:.6rem"></div>')
    pos = segmented("Position", list(pr.FANTASY_POS), "rank_pos", "WR")
    with st.spinner("Ranking players..."):
        pool, _ = pr.position_pool(S, pos)
    rows = []
    for pid, m in pool.items():
        t = S.season_tot.get(pid, {})
        r = {"pid": pid, "Player": t.get("name"), "Team": t.get("team"), "G": m["games"], "PPG": m.get("ppg"),
             "xFP/G": m.get("xfp_pg"), "+/- exp": m.get("fpoe_pg"), "Snap %": m.get("snap_pct")}
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
    df = pd.DataFrame(rows).sort_values("PPG", ascending=False).reset_index(drop=True)
    df.insert(1, "Rk", range(1, len(df) + 1))
    if pick:
        df = df[df["Team"].isin(pick)].reset_index(drop=True)
    cfg = {"pid": None, "Rk": st.column_config.NumberColumn(width="small"),
           "PPG": st.column_config.NumberColumn(format="%.1f"), "xFP/G": st.column_config.NumberColumn(format="%.1f"),
           "+/- exp": st.column_config.NumberColumn(format="%+.1f", help="Points over expected per game"),
           "Snap %": st.column_config.NumberColumn(format="%.0f%%")}
    for lab, key, mult in RANK_COLS[pos]:
        cfg[lab] = st.column_config.NumberColumn(format="%.0f%%" if mult == 100 else "%.2f")
    sty = smap(df.style, lambda v: f"color: {tier_color(v)}; font-weight: 800" if pd.notna(v) else "", ["Rk"])
    sty = smap(sty, lambda v: (f"color: {GREEN}" if v >= 1 else f"color: {RED}" if v <= -1 else "")
               if pd.notna(v) else "", ["+/- exp"])
    try:
        ev = st.dataframe(sty, use_container_width=True, hide_index=True, column_config=cfg, height=640,
                          on_select="rerun", selection_mode="single-row", key=f"rank_table_{pos}")
        sel = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
    except TypeError:
        st.dataframe(sty, use_container_width=True, hide_index=True, column_config=cfg, height=640)
        sel = []
    st.caption(f"{len(df)} {pos}s with {S.min_games}+ games and real volume. Rank colour: green top 12, blue 13-24, "
               "gold 25-36.")
    if sel:
        st.session_state.pending = {"player": df.iloc[sel[0]]["pid"], "view": "Player"}
        st.rerun()


def page_defense(S):
    H(f'<div class="fr-title">Defense vs position</div><div class="fr-sub">Fantasy points allowed per game '
      f'({pr.FORMAT_LABEL[S.fmt_name]}). Rank 1 = allows the most = best matchup for your players. '
      f'Green = attack, red = avoid.</div>')
    H('<div style="height:.6rem"></div>')
    teams = sorted({k[0] for k in S.fpa})
    n = len(teams)
    rows = []
    for t in teams:
        r = {"Defense": t}
        for pos in pr.FANTASY_POS:
            f = S.fpa.get((t, pos), {})
            r[pos] = f.get("avg")
            r[f"{pos} rk"] = f.get("rank")
        rows.append(r)
    sort_pos = segmented("Sort by", list(pr.FANTASY_POS), "def_pos", "WR", lambda p: f"Sort by {p}")
    df = pd.DataFrame(rows).sort_values(f"{sort_pos} rk").reset_index(drop=True)

    def heat(v):
        if pd.isna(v):
            return ""
        x = (v - 1) / max(1, n - 1)
        a = abs(0.5 - x) * 0.9
        rgb = "34,197,94" if x <= 0.5 else "239,68,68"
        return f"background-color: rgba({rgb},{a:.2f}); font-weight: 700"
    rk_cols = [c for c in df.columns if c.endswith(" rk")]
    sty = df.style.format(precision=1, na_rep="").format("{:.0f}", subset=rk_cols, na_rep="")
    sty = smap(sty, heat, rk_cols)
    st.dataframe(sty, use_container_width=True, hide_index=True, height=40 + 35 * len(df))


# ------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------

def main():
    H(CSS)
    pend = st.session_state.pop("pending", None)
    if pend:
        st.session_state.player = pend["player"]
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
    {"Home": page_home, "Player": page_player, "Rankings": page_rankings, "Defense": page_defense}[view](S)

    notes = " · ".join(S.notes)
    H(f'<div class="fr-foot">Data: nflverse (play-by-play, FTN charting, Next Gen Stats, ffopportunity) · '
      f'updated {S.loaded_at:%b %d, %I:%M %p} · refreshes every {pr.CACHE_HOURS} hours'
      f'{"<br>" + esc(notes) if notes else ""}</div>')


main()
