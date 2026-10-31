"""
Fantasy Player Reports: website version.

Run on your computer:   streamlit run app.py
Host it for free:       Streamlit Community Cloud (see the setup steps Claude gave you)

All the stats come from player_report.py, which must sit in the same folder.
"""

import os
import tempfile
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import player_report as pr

st.set_page_config(page_title="Fantasy Player Reports", page_icon="🏈", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1250px;}
div[data-testid="stMetricValue"] {font-size: 1.55rem;}
div[data-testid="stMetricLabel"] p {font-size: 0.8rem;}
</style>
""", unsafe_allow_html=True)

GREEN, BLUE, GOLD, GRAY = "#2f855a", "#3b82c4", "#d69e2e", "#9ca3af"
DARK, ACCENT, RED = "#1f2a37", "#f2a900", "#c53030"
GOOD_BG, BAD_BG, TD_BG, DROP_BG = "#e3f3ea", "#fbe4e4", "#fff4d6", "#ffe8d6"
FORMATS = {"Half-PPR": "half", "PPR": "ppr", "Standard": "standard"}
SEASONS = [pr.SEASON, pr.SEASON - 1, pr.SEASON - 2]
VIEWS = ["Player report", "Rankings", "Defense vs position"]
fmt = pr.fmt


# ------------------------------------------------------------------------------------
# Data (cached on the server and shared by every visit)
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


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=300, show_spinner=False)
def get_report(_S, key):
    return pr.build_report(_S, key[2])


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def get_player_list(_S, key):
    rows = sorted(_S.season_tot.items(), key=lambda kv: -kv[1]["pts"])
    labels = {pid: f"{t['name']}  ·  {t['pos']}  ·  {t['team']}  ·  {t['ppg']:.1f} PPG" for pid, t in rows}
    return [pid for pid, _ in rows], labels


def tier_color(rank):
    if not rank:
        return GRAY
    return GREEN if rank <= 12 else BLUE if rank <= 24 else GOLD if rank <= 36 else GRAY


def table(rows, **kw):
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, **kw)


# ------------------------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------------------------

def points_chart(rep):
    wk = rep["weekly"]
    x = [f"W{w['week']}" for w in wk]
    y = [0 if w.get("status") else (w.get("pts") or 0) for w in wk]
    text = [("BYE" if w["status"] == "BYE" else "OUT") if w.get("status") else f"{w.get('pts') or 0:.1f}"
            for w in wk]
    hover = [w.get("status") or f"{w.get('opp', '')}<br>{w.get('pts') or 0:.1f} pts"
                                 f"{' · ' + rep['pos'] + str(w['rank']) if w.get('rank') else ''}" for w in wk]
    fig = go.Figure()
    fig.add_bar(x=x, y=y, marker_color=[tier_color(w.get("rank")) for w in wk], text=text,
                textposition="outside", cliponaxis=False, name="Fantasy points", hovertext=hover,
                hoverinfo="text")
    xs = [w.get("xfp") if not w.get("status") else None for w in wk]
    if any(v is not None for v in xs):
        fig.add_scatter(x=x, y=xs, mode="markers", name="Expected (xFP)",
                        marker=dict(symbol="line-ew", size=24, line=dict(width=3, color=DARK)),
                        hovertemplate="xFP %{y:.1f}<extra></extra>")
    if rep["prof"]["ppg"]:
        fig.add_hline(y=rep["prof"]["ppg"], line_dash="dash", line_color=ACCENT,
                      annotation_text=f"avg {rep['prof']['ppg']:.1f}", annotation_position="top left")
    fig.update_layout(height=330, margin=dict(l=8, r=8, t=36, b=8), bargap=0.35, yaxis_title="Points",
                      legend=dict(orientation="h", y=1.15, x=0), plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", rangemode="tozero")
    return fig


def usage_chart(rep):
    played = [w for w in rep["weekly"] if not w.get("status")]
    x = [f"W{w['week']}" for w in played]
    pos = rep["pos"]
    if pos in ("WR", "TE"):
        series = [("Snap share", DARK, [(w["snap_pct"] / 100) if w.get("snap_pct") is not None else None
                                        for w in played]),
                  ("Route participation", BLUE, [w.get("route_pct") for w in played]),
                  ("Target share", ACCENT, [w.get("tgt_share") for w in played]),
                  ("Air yards share", GREEN, [w.get("air_share") for w in played])]
        pct = True
    elif pos == "RB":
        series = [("Snap share", DARK, [(w["snap_pct"] / 100) if w.get("snap_pct") is not None else None
                                        for w in played]),
                  ("Rush share", ACCENT, [w.get("rush_share") for w in played]),
                  ("Target share", BLUE, [w.get("tgt_share") for w in played]),
                  ("Red-zone share", GREEN, [w.get("rz_share") for w in played])]
        pct = True
    else:
        series = [("Fantasy points", ACCENT, [w.get("pts") for w in played]),
                  ("Expected (xFP)", DARK, [w.get("xfp") for w in played])]
        pct = False
    fig = go.Figure()
    for name, col, vals in series:
        fig.add_scatter(x=x, y=vals, mode="lines+markers", name=name, line=dict(color=col, width=2.5),
                        connectgaps=False)
    fig.update_layout(height=300, margin=dict(l=8, r=8, t=36, b=8), legend=dict(orientation="h", y=1.18, x=0),
                      plot_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", rangemode="tozero",
                     tickformat=".0%" if pct else None, range=[0, 1] if pct else None)
    return fig


def plot(fig):
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ------------------------------------------------------------------------------------
# Player report page
# ------------------------------------------------------------------------------------

def header(rep):
    b, pos = rep["bio"], rep["pos"]
    st.markdown(f"## {rep['name']}")
    line1 = " · ".join(x for x in [rep["team"], pos, f"#{rep['jersey']}" if rep.get("jersey") is not None else None,
                                   f"Age {b['age']}" if b.get("age") else None, b.get("exp"),
                                   pr.FORMAT_LABEL[rep["fmt"]]] if x)
    line2 = " · ".join(x for x in [b.get("height"), b.get("weight"), b.get("college"),
                                   f"Drafted {b['draft']}" if b.get("draft") else None] if x)
    st.caption(line1 + ("  \n" + line2 if line2 else ""))
    inj = rep["injury"]
    if inj and inj.get("status"):
        st.warning(f"**Injury report, week {inj['week']}: {inj['status']}**"
                   f"{' (' + inj['injury'] + ')' if inj.get('injury') else ''}"
                   f"{' · ' + inj['practice'] if inj.get('practice') else ''}")


def metric_row(rep):
    p, m, pos = rep["prof"], rep["m"], rep["pos"]
    rk = {r["key"]: r for r in rep["ranks"]}

    def rank_txt(key):
        r = rk.get(key)
        return f"{pr.ordinal(r['rank'])} of {r['n']} {pos}s" if r and r["rank"] else None
    key_usage = {"WR": ("tgt_share", "Target share", "pct"), "TE": ("tgt_share", "Target share", "pct"),
                 "RB": ("opp_pg", "Opportunities / game", "dec1"),
                 "QB": ("p_epa_per_db", "EPA / dropback", "dec2s")}[pos]
    l3 = p.get("last3_ppg")
    items = [
        ("Points / game", fmt(p["ppg"], "dec1"),
         f"{l3 - p['ppg']:+.1f} last 3 games" if l3 is not None and p["ppg"] is not None else None,
         f"{pos}{m['rank_ppg']} in PPG" if m.get("rank_ppg") else None),
        ("Total points", fmt(p["pts"], "dec1"), None, f"{pos}{m['rank_total']} overall" if m.get("rank_total") else None),
        ("Expected pts / game", fmt(m.get("xfp_pg"), "dec1"), None,
         "What an average player would score with his exact usage. " + (rank_txt("xfp_pg") or "")),
        ("Pts over expected / game", fmt(m.get("fpoe_pg"), "dec1s"), None,
         "Well below zero = buy-low signal. Well above zero = likely running hot."),
        ("Top-12 weeks", f"{p['top12']} of {p['games']}", None, f"Top-24 weeks: {p['top24']}"),
        (f"Boom rate ({p['boom']}+)", fmt(p["boom_rate"], "pct"), None,
         f"Bust rate (under {p['bust']}): {fmt(p['bust_rate'], 'pct')}"),
        ("Snap share", fmt(m.get("snap_pct"), "pct100"), None, rank_txt("snap_pct")),
        (key_usage[1], fmt(m.get(key_usage[0]), key_usage[2]), None, rank_txt(key_usage[0])),
    ]
    for row in (items[:4], items[4:]):
        cols = st.columns(4)
        for c, (label, value, delta, help_) in zip(cols, row):
            c.metric(label, value, delta=delta, help=help_ or None)


def tab_overview(rep):
    plot(points_chart(rep))
    st.caption("Bar colour = weekly finish (green top 12, blue 13-24, gold 25-36). "
               "Dark tick = expected points from his usage. Dashed line = season average.")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Edge notes")
        if not rep["insights"]:
            st.info("Not enough games yet for edge notes.")
        for tone, text in rep["insights"]:
            if tone == "up":
                st.success(text, icon="📈")
            elif tone == "down":
                st.error(text, icon="⚠️")
            else:
                st.info(text, icon="ℹ️")
    with right:
        st.subheader("Fantasy profile")
        p, m, pos = rep["prof"], rep["m"], rep["pos"]
        rows = [("Median game", fmt(p["median"], "dec1")),
                ("Floor / ceiling (25th / 75th pct)", f"{fmt(p['floor'], 'dec1')} / {fmt(p['ceiling'], 'dec1')}"),
                ("Best game", f"{fmt(p['best'], 'dec1')}  ({p['best_label']})"),
                ("Worst game", fmt(p["worst"], "dec1")),
                ("Volatility (std dev)", fmt(p["stdev"], "dec1")),
                (f"Top-{pr.STARTER_CUTOFF[pos]} finish rate", fmt(p["starter_rate"], "pct")),
                ("Last 3 games PPG", fmt(p["last3_ppg"], "dec1")),
                ("Points from TDs", fmt(m.get("td_pts_share"), "pct"))]
        if pos != "QB" and rep["fmt"] != "standard":
            rows.append(("Points from receptions", fmt(m.get("rec_pts_share"), "pct")))
        if pos == "QB":
            rows.append(("Points from rushing", fmt(m.get("rush_pts_share"), "pct")))
        exp_td = m.get("exp_td")
        if exp_td is not None:
            rows.append(("Rush + rec TDs vs expected", f"{int(m['act_td_xweeks'])} vs {exp_td:.1f}"))
        if pos == "QB" and m.get("exp_pass_td") is not None:
            rows.append(("Pass TDs vs expected", f"{int(m['act_pass_td_xweeks'])} vs {m['exp_pass_td']:.1f}"))
        table([{"Stat": a, "Value": b} for a, b in rows])


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
                      "TD": fmt(w.get("rec_td"), "int"), "Tgt share": fmt(w.get("tgt_share"), "pct"),
                      "Air share": fmt(w.get("air_share"), "pct"), "RZ tgt": fmt(w.get("rz_tgt"), "int"),
                      "EZ tgt": fmt(w.get("ez_tgt"), "int")})
        elif pos == "RB":
            r.update({"Car": fmt(w.get("carries_official", w.get("carries")), "int"),
                      "Rush yds": fmt(w.get("rush_yds"), "int"), "Rush share": fmt(w.get("rush_share"), "pct"),
                      "Tgt": fmt(w.get("targets"), "int"), "Rec": fmt(w.get("rec"), "int"),
                      "Rec yds": fmt(w.get("rec_yds"), "int"),
                      "TD": fmt((w.get("rush_td") or 0) + (w.get("rec_td") or 0), "int"),
                      "RZ share": fmt(w.get("rz_share"), "pct"), "HVT": fmt(w.get("hvt"), "int")})
        else:
            r.update({"Cmp/Att": f"{fmt(w.get('completions'), 'int')}/{fmt(w.get('attempts'), 'int')}",
                      "Pass yds": fmt(w.get("pass_yds"), "int"), "TD": fmt(w.get("pass_td"), "int"),
                      "INT": fmt(w.get("ints"), "int"), "Sk": fmt(w.get("sacks"), "int"),
                      "Car": fmt(w.get("carries_official", w.get("carries")), "int"),
                      "Rush yds": fmt(w.get("rush_yds"), "int"), "Rush TD": fmt(w.get("rush_td"), "int"),
                      "EPA/DB": fmt(w.get("epa_db"), "dec2s")})
        out.append(r)
    return out


def tab_weekly(rep):
    df = pd.DataFrame(weekly_rows(rep))

    def color(row):
        styles = [""] * len(row)
        if "Finish" in row.index and isinstance(row["Finish"], str) and row["Finish"] not in ("–", ""):
            try:
                rk = int(row["Finish"][2:])
                i = list(row.index).index("Finish")
                styles[i] = f"color: {tier_color(rk)}; font-weight: 600"
            except ValueError:
                pass
        if "+/-" in row.index and pd.notna(row["+/-"]):
            i = list(row.index).index("+/-")
            styles[i] = f"color: {GREEN if row['+/-'] >= 0 else RED}"
        return styles
    st.dataframe(df.style.apply(color, axis=1).format(precision=1, na_rep=""), use_container_width=True,
                 hide_index=True)
    st.caption("Finish = positional rank that week. xFP = expected points from usage; +/- = actual minus expected. "
               "Route% = share of team dropbacks he was on the field for. HVT = targets + carries inside the 10.")
    st.subheader("Usage trends")
    plot(usage_chart(rep))
    if rep["trends"]:
        rows = []
        for t in rep["trends"]:
            k = t["kind"]
            d = f"{t['delta'] * 100:+.1f} pts" if k == "pct" else f"{t['delta']:+.1f} pts" if k == "pct100" \
                else fmt(t["delta"], "dec1s")
            flag = ("▲ " if t["delta"] > 0 else "▼ ") if abs(t["delta"]) >= t["thr"] else ""
            rows.append({"Trend": t["label"], "Season": fmt(t["season"], k), "Last 3": fmt(t["last3"], k),
                         "Change": flag + d})
        table(rows)
    else:
        st.caption("Trends appear after 4 games.")


def tab_matchups(rep):
    sched, pos, tc = rep["sched"], rep["pos"], rep["team_ctx"] or {}
    nt = rep["n_teams"] or 32
    if sched and sched["next"]:
        nx = sched["next"]
        st.subheader(f"Next: week {nx['week']} {nx['label']}")
        when = " ".join(str(x) for x in [nx.get("gameday"), nx.get("gametime")] if x)
        if when:
            st.caption(f"Kickoff {when}")
        c = st.columns(4)
        c[0].metric("Implied team total", fmt(nx.get("implied"), "dec1"), help="Vegas total and spread combined")
        c[1].metric("Spread", f"{rep['team']} {nx['team_spread']:+.1f}" if nx.get("team_spread") is not None else "–")
        c[2].metric("Game total", fmt(nx.get("total"), "dec1"))
        c[3].metric(f"{nx['opp']} vs {pos}s", f"{pr.ordinal(nx['fpa_rank'])} most" if nx.get("fpa_rank") else "–",
                    help=f"{nx['opp']} allows {fmt(nx.get('fpa_avg'), 'dec1')} fantasy points per game to {pos}s "
                         f"(league average {fmt(rep['fpa_avg'], 'dec1')}). 1st = easiest matchup.")
    elif sched:
        st.info("Regular season complete.")
    if sched and sched["upcoming"]:
        st.subheader("Rest of season")
        rows = []
        items = [(u["week"], u) for u in sched["upcoming"]] + \
                [(w, None) for w in sched["byes"] if w > rep["last_week"]]
        for wk, u in sorted(items, key=lambda x: x[0]):
            if u is None:
                rows.append({"Wk": wk, "Opponent": "BYE"})
                continue
            r, n = u.get("fpa_rank"), u.get("fpa_n") or nt
            lab = ("Great" if r <= 6 else "Good" if r <= 12 else "Tough" if r >= n - 5 else "Below avg"
                   if r >= n - 11 else "Neutral") if r else "–"
            rows.append({"Wk": f"{wk} ★" if u["playoff"] else wk, "Opponent": u["label"],
                         "Date": str(u.get("gameday") or ""),
                         "Line": f"{u['team_spread']:+.1f}" if u.get("team_spread") is not None else "",
                         "Implied": fmt(u.get("implied"), "dec1"),
                         f"Opp rank vs {pos}": pr.ordinal(r) if r else "–",
                         "Pts allowed": fmt(u.get("fpa_avg"), "dec1"), "Matchup": lab})
        df = pd.DataFrame(rows).fillna("")

        def color(row):
            m = row.get("Matchup", "")
            bg = GOOD_BG if m in ("Great", "Good") else BAD_BG if m in ("Tough", "Below avg") else ""
            return [f"background-color: {bg}; color: #1f2328" if bg else "" for _ in row]
        st.dataframe(df.style.apply(color, axis=1), use_container_width=True, hide_index=True)
        bits = []
        if sched["ros_avg_rank"]:
            bits.append(f"Rest-of-season opponents average a **{sched['ros_avg_rank']:.1f}** rank")
        if sched["playoff_avg_rank"]:
            bits.append(f"fantasy playoff (★) opponents average **{sched['playoff_avg_rank']:.1f}**")
        st.caption("Opponent rank = where that defense ranks in fantasy points allowed to "
                   f"{pos}s (1st = most allowed = best matchup). " + "; ".join(bits))
    st.subheader(f"{rep['team']} offense")
    rows = []
    for key, lab, kind in [("ppg", "Points per game", "dec1"), ("plays_pg", "Plays per game (pace)", "dec1"),
                           ("pass_rate", "Dropback rate", "pct"),
                           ("proe", "Pass rate over expected (neutral situations)", "pct1s"),
                           ("rz_plays_pg", "Red-zone plays per game", "dec1")]:
        r = tc.get(key + "_rank")
        rows.append({"Stat": lab, "Value": fmt(tc.get(key), kind), "NFL rank": f"{pr.ordinal(r)} of {nt}" if r else "–"})
    table(rows)


def rank_df(items):
    return pd.DataFrame([{"Metric": r["label"], "Value": r["value"],
                          "Rank": f"{r['rank']} / {r['n']}" if r["rank"] else "–",
                          "Percentile": round(r["pct"]) if r["pct"] is not None else None} for r in items])


def tab_ranks(rep):
    st.caption(f"Compared with {rep['pool_n']} {rep['pos']}s with {rep['min_games']}+ games and real volume. "
               "Percentile 100 = best (for drop, stuff, sack and INT rates, lower is better and already flipped).")
    cfg = {"Percentile": st.column_config.ProgressColumn("Percentile", min_value=0, max_value=100, format="%d")}
    st.subheader("Production, usage and efficiency")
    st.dataframe(rank_df(rep["ranks"]), use_container_width=True, hide_index=True, column_config=cfg)
    if rep["ngs"]:
        st.subheader("Next Gen Stats (player tracking)")
        st.dataframe(rank_df(rep["ngs"]), use_container_width=True, hide_index=True, column_config=cfg)
    st.caption("WOPR = 1.5 × target share + 0.7 × air yards share. Routes are approximated by pass plays he was "
               "on the field for. Some style metrics (aDOT, cushion, time to throw) are neither good nor bad.")


def tab_splits(rep):
    if not rep["splits"]:
        st.info("No splits yet.")
    cols = st.columns(2)
    for i, (title, spec, items) in enumerate(rep["splits"]):
        with cols[i % 2]:
            st.markdown(f"**{title}**")
            rows = []
            for lab, s in items:
                r = {"": lab}
                for h, key, kind in spec:
                    r[h] = "–" if (key == "drops" and not s.get("charted")) else fmt(s.get(key), kind)
                rows.append(r)
            table(rows)


def tab_plays(rep):
    log = rep["log"]
    if not log:
        st.info("No plays yet.")
        return
    weeks = sorted({l["week"] for l in log})
    c1, c2, c3 = st.columns([2, 2, 1.3])
    pick_weeks = c1.multiselect("Weeks", weeks, default=[], placeholder="All weeks")
    types = sorted({l["type"] for l in log})
    pick_types = c2.multiselect("Play types", types, default=[], placeholder="All play types")
    only_bad = c3.toggle("Mistakes only", help="Drops, turnovers, INT-worthy throws and penalties")
    rows = []
    for l in log:
        if pick_weeks and l["week"] not in pick_weeks:
            continue
        if pick_types and l["type"] not in pick_types:
            continue
        if only_bad and not (l["_drop"] or l["_bad"]):
            continue
        rows.append({"Wk": l["week"], "Opp": l["opp"],
                     "Q": ("OT" if (l["qtr"] or 0) >= 5 else f"Q{int(l['qtr'])}") if l["qtr"] else "",
                     "Time": l["time"] or "",
                     "Down": f"{pr.ordinal(l['down'])} & {int(l['ydstogo'])}" if l["down"] else "",
                     "Spot": l["yrdln"] or "", "Type": l["type"], "Result": l["result"],
                     "Air": int(l["air_yards"]) if l["air_yards"] is not None else None,
                     "YAC": int(l["yac"]) if l["yac"] is not None else None,
                     "EPA": round(l["epa"], 2) if l["epa"] is not None else None,
                     "Flags": l["flags"], "Play": l["desc"],
                     "_k": "td" if l["_td"] else "drop" if l["_drop"] else "bad" if l["_bad"] else ""})
    st.caption(f"{len(rows)} plays · gold = touchdown, orange = drop, red = turnover / INT-worthy / penalty")
    if not rows:
        return
    df = pd.DataFrame(rows)
    kinds = df.pop("_k")

    def color(row):
        bg = {"td": TD_BG, "drop": DROP_BG, "bad": BAD_BG}.get(kinds[row.name], "")
        return [f"background-color: {bg}; color: #1f2328" if bg else "" for _ in row]
    st.dataframe(df.style.apply(color, axis=1).format(precision=2, na_rep=""), use_container_width=True,
                 hide_index=True, height=min(640, 38 + 35 * len(df)),
                 column_config={"Play": st.column_config.TextColumn("Play", width="large")})


def pdf_button(rep):
    key = f"pdf_{rep['pid']}_{rep['season']}_{rep['fmt']}"
    if st.session_state.get(key) is None:
        if st.button("Make a PDF copy", help="Optional. Everything is already on this page."):
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
        st.download_button("Download PDF", st.session_state[key],
                           file_name=f"{pr.slug(rep['name'])}_{rep['season']}_report.pdf", mime="application/pdf")


def page_player(S):
    pids, labels = get_player_list(S, (S.season, S.fmt_name, S.loaded_at))
    if "player" not in st.session_state:
        q = st.query_params.get("player")
        st.session_state.player = q if q in labels else None
    elif st.session_state.player not in labels:  # e.g. after switching seasons
        st.session_state.player = None
    pid = st.selectbox("Player", pids, format_func=lambda p: labels.get(p, p), key="player",
                       placeholder="Search any QB, RB, WR or TE...", label_visibility="collapsed")
    if not pid:
        st.query_params.pop("player", None)
        st.info("Start typing a player's name above. Tip: the **Rankings** view lets you tap any player to "
                "open his report.")
        return
    st.query_params["player"] = pid
    with st.spinner("Building report..."):
        rep = get_report(S, (S.season, S.fmt_name, pid, S.loaded_at))
    header(rep)
    metric_row(rep)
    tabs = st.tabs(["Overview", "Week by week", "Matchups", "League ranks", "Splits", "Plays"])
    with tabs[0]:
        tab_overview(rep)
    with tabs[1]:
        tab_weekly(rep)
    with tabs[2]:
        tab_matchups(rep)
    with tabs[3]:
        tab_ranks(rep)
    with tabs[4]:
        tab_splits(rep)
    with tabs[5]:
        tab_plays(rep)
    st.divider()
    pdf_button(rep)


# ------------------------------------------------------------------------------------
# Rankings and defense pages
# ------------------------------------------------------------------------------------

RANK_COLS = {
    "WR": [("Tgt share", "tgt_share", 100), ("Air share", "air_share", 100), ("WOPR", "wopr", 1),
           ("Route %", "route_pct", 100), ("YPRR", "yprr", 1), ("TPRR", "tprr", 100), ("aDOT", "r_adot", 1),
           ("Drop %", "r_drop_rate", 100)],
    "RB": [("Opp / game", "opp_pg", 1), ("Rush share", "rush_share", 100), ("HVT / game", "hvt_pg", 1),
           ("Inside-10 share", "i10_share", 100), ("Tgt share", "tgt_share", 100), ("YPC", "ru_ypc", 1),
           ("Rush EPA", "ru_epa_per", 1), ("Stuff %", "ru_stuff_rate", 100)],
    "QB": [("Dropbacks / g", "p_dropbacks_pg", 1), ("EPA / DB", "p_epa_per_db", 1), ("CPOE", "p_cpoe", 1),
           ("ANY/A", "p_any_a", 1), ("Rush yds / g", "rush_ypg", 1), ("Scrambles / g", "p_scrambles_pg", 1),
           ("Sack %", "p_sack_rate", 100), ("INT %", "p_int_rate", 100)],
}
RANK_COLS["TE"] = RANK_COLS["WR"]


def page_rankings(S):
    pos = st.radio("Position", list(pr.FANTASY_POS), horizontal=True, index=2, key="rank_pos",
                   label_visibility="collapsed")
    with st.spinner("Ranking players..."):
        pool, thr = pr.position_pool(S, pos)
    rows = []
    for pid, m in pool.items():
        t = S.season_tot.get(pid, {})
        r = {"pid": pid, "Player": t.get("name"), "Team": t.get("team"), "G": m["games"],
             "PPG": m.get("ppg"), "xFP/G": m.get("xfp_pg"), "+/- exp": m.get("fpoe_pg"),
             "Snap %": m.get("snap_pct")}
        for lab, key, mult in RANK_COLS[pos]:
            v = m.get(key)
            r[lab] = v * mult if v is not None else None
        rows.append(r)
    if not rows:
        st.info("Not enough games played yet.")
        return
    df = pd.DataFrame(rows).sort_values("PPG", ascending=False).reset_index(drop=True)
    df.insert(1, "Rk", range(1, len(df) + 1))
    cfg = {"pid": None, "PPG": st.column_config.NumberColumn(format="%.1f"),
           "xFP/G": st.column_config.NumberColumn(format="%.1f"),
           "+/- exp": st.column_config.NumberColumn(format="%+.1f", help="Points over expected per game"),
           "Snap %": st.column_config.NumberColumn(format="%.0f%%")}
    for lab, key, mult in RANK_COLS[pos]:
        cfg[lab] = st.column_config.NumberColumn(format="%.0f%%" if mult == 100 else "%.2f")
    st.caption(f"{len(df)} {pos}s with {S.min_games}+ games and real volume. Tap a column to sort, "
               "tap a row to open the full report. Sort by +/- exp to find buy-low (most negative) and "
               "sell-high (most positive) players.")
    try:
        ev = st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg, height=600,
                          on_select="rerun", selection_mode="single-row", key=f"rank_table_{pos}")
        sel = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
    except TypeError:  # older Streamlit without row selection
        st.dataframe(df, use_container_width=True, hide_index=True, column_config=cfg, height=600)
        sel = []
    if sel:
        st.session_state.pending = {"player": df.iloc[sel[0]]["pid"], "view": VIEWS[0]}
        st.rerun()


def page_defense(S):
    st.caption("Average fantasy points allowed per game to each position "
               f"({pr.FORMAT_LABEL[S.fmt_name]}). Rank 1 = allows the most = best matchup for your players.")
    teams = sorted({k[0] for k in S.fpa})
    rows = []
    for t in teams:
        r = {"Defense": t}
        for pos in pr.FANTASY_POS:
            f = S.fpa.get((t, pos), {})
            r[f"{pos} pts"] = f.get("avg")
            r[f"{pos} rank"] = f.get("rank")
        rows.append(r)
    df = pd.DataFrame(rows).sort_values("WR rank")
    rank_cols = [c for c in df.columns if c.endswith("rank")]

    def color(v):
        if pd.isna(v):
            return ""
        return f"background-color: {GOOD_BG}; color: #1f2328" if v <= 8 else \
            f"background-color: {BAD_BG}; color: #1f2328" if v >= len(teams) - 7 else ""
    styler = df.style.format(precision=1, na_rep="").format("{:.0f}", subset=rank_cols, na_rep="")
    styler = styler.map(color, subset=rank_cols) if hasattr(styler, "map") else styler.applymap(color, subset=rank_cols)
    st.dataframe(styler, use_container_width=True, hide_index=True, height=38 + 35 * len(df))


# ------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------

def main():
    pend = st.session_state.pop("pending", None)
    if pend:
        st.session_state.player = pend["player"]
        st.session_state.view = pend["view"]

    qp = st.query_params
    with st.sidebar:
        st.header("Settings")
        try:
            s_default = SEASONS.index(int(qp.get("season", pr.SEASON)))
        except ValueError:
            s_default = 0
        season = st.selectbox("Season", SEASONS, index=s_default)
        f_default = next((i for i, v in enumerate(FORMATS.values()) if v == qp.get("scoring", pr.SCORING_FORMAT)), 0)
        scoring = FORMATS[st.radio("Scoring", list(FORMATS), index=f_default)]
        st.caption("Point values for each scoring type come from the SETTINGS block in player_report.py.")
        if st.button("Refresh data now"):
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
        st.caption("Try **Refresh data now** in the sidebar (top-left arrow) in a few minutes.")
        st.stop()

    top = st.columns([3, 2])
    with top[0]:
        view = st.radio("View", VIEWS, horizontal=True, key="view", label_visibility="collapsed")
    with top[1]:
        st.caption(f"🏈 {pr.FORMAT_LABEL[scoring]} · {season} through week {S.last_week} · "
                   f"updated {S.loaded_at:%b %d, %I:%M %p}")

    if view == VIEWS[0]:
        page_player(S)
    elif view == VIEWS[1]:
        page_rankings(S)
    else:
        page_defense(S)

    if S.notes:
        with st.expander("Data notes"):
            for n in S.notes:
                st.caption(n)


main()
