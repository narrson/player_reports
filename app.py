"""
Fantasy Player Reports: website version.

Run on your computer:   streamlit run app.py
Hosted on:              Streamlit Community Cloud (files: app.py, player_report.py, requirements.txt,
                        .streamlit/config.toml)

All the stats come from player_report.py, which must sit in the same folder.
"""

import base64
import difflib
import math
import hashlib
import hmac
import html
import re
import os
import secrets as pysecrets
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import player_report as pr

st.set_page_config(page_title="Fantasy Player Reports", page_icon="🏈", layout="wide",
                   initial_sidebar_state="collapsed")

REQUIRED_ENGINE = 9
if getattr(pr, "ENGINE_VERSION", 0) < REQUIRED_ENGINE:
    # Streamlit can keep an old copy of player_report.py loaded after an update; load the new one.
    import importlib
    pr = importlib.reload(pr)
if getattr(pr, "ENGINE_VERSION", 0) < REQUIRED_ENGINE:
    st.error("**The site's files are out of sync.** app.py was updated but player_report.py is still the older "
             "version. Upload the newest player_report.py to GitHub, then reboot the app (Manage app → ⋮ → Reboot).")
    st.stop()

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
.fr-slot {{display: inline-flex; align-items: center; justify-content: center; min-width: 52px; height: 30px;
           padding: 0 .4rem; border-radius: 7px; font-size: .68rem; font-weight: 800; letter-spacing: .04em;
           border: 1px solid; flex: none;}}
.fr-inj {{display: inline-block; margin-left: .35rem; padding: 0 .3rem; border: 1px solid; border-radius: 5px;
          font-size: .62rem; font-weight: 800; vertical-align: middle; line-height: 1.35;}}
.fr-tag {{display: inline-block; margin-left: .35rem; padding: .02rem .35rem; border-radius: 5px; font-size: .6rem;
          font-weight: 800; letter-spacing: .05em; vertical-align: middle;}}
.fr-tag.start {{background: rgba(34,197,94,.18); color: #4ade80;}}
.fr-tag.sit {{background: rgba(245,158,11,.18); color: #fbbf24;}}
.fr-tc {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px; overflow: hidden;}}
.fr-tc-head {{display: flex; gap: .8rem; align-items: center; padding: .85rem 1rem;}}
.fr-rank-badge {{width: 40px; height: 40px; border-radius: 12px; color: #0b1220; font-weight: 900; font-size: 1.15rem;
                display: flex; align-items: center; justify-content: center; flex: none;}}
.fr-tc-name {{font-size: 1.12rem; font-weight: 800; color: {TEXT}; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis;}}
.fr-tc-sub {{font-size: .78rem; color: {MUTED};}}
.fr-you {{display: inline-block; margin-left: .4rem; padding: .05rem .4rem; border-radius: 6px; background: {GOLD};
         color: #0b1220; font-size: .62rem; font-weight: 900; vertical-align: middle;}}
.fr-grade {{display: inline-block; margin: 0 .25rem .2rem 0; padding: 0 .35rem; border: 1px solid; border-radius: 6px;
           font-size: .66rem; font-weight: 800;}}
.fr-tc-tot {{text-align: right; flex: none;}}
.fr-tc-tot .v {{font-size: 1.5rem; font-weight: 900; color: {TEXT}; line-height: 1;}}
.fr-tc-tot .l {{font-size: .6rem; color: {MUTED}; text-transform: uppercase; letter-spacing: .07em; margin-top: .2rem;}}
.fr-tc-body {{padding: .2rem .8rem .7rem;}}
.fr-grp {{display: flex; justify-content: space-between; align-items: baseline; margin: .7rem .2rem .25rem;
         font-size: .68rem; text-transform: uppercase; letter-spacing: .09em; color: {MUTED};}}
.fr-grp b {{color: {TEXT}; font-weight: 800;}}
.fr-grp b em {{font-style: normal; color: {MUTED}; font-weight: 700; margin-left: .35rem; letter-spacing: .05em;}}
.fr-grp .cols {{display: flex; gap: .2rem;}}
.fr-grp .cols i {{font-style: normal; min-width: 48px; text-align: right; font-size: .58rem; letter-spacing: .1em;
                 color: {MUTED}; font-weight: 800;}}
.fr-pl.bye {{opacity: .55;}}
.fr-strip {{display: flex; flex-wrap: wrap; align-items: center; gap: .35rem .7rem; font-size: .8rem; color: {MUTED};
           background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: .45rem .75rem; margin-bottom: .6rem;}}
.fr-strip-k {{font-size: .62rem; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; color: {TEXT};
             margin-right: .45rem;}}
.fr-strip-sep {{width: 1px; height: 14px; background: {BORDER};}}
.fr-pl {{display: flex; align-items: center; gap: .6rem; padding: .36rem .3rem; border-bottom: 1px solid {BORDER}55;}}
.fr-pl:last-child {{border-bottom: none;}}
.fr-pl.ir {{opacity: .72;}}
.fr-pl-main {{flex: 1; min-width: 0;}}
.fr-pl-name {{font-weight: 700; font-size: .9rem; color: {TEXT}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}}
.fr-pl-name a {{color: {TEXT} !important; text-decoration: none !important;}}
.fr-pl-name a:hover {{color: {GOLD} !important;}}
.fr-pl-meta {{font-size: .74rem; color: {MUTED}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}}
.fr-pts {{text-align: right; flex: none; min-width: 52px;}}
.fr-pts2 {{display: flex; gap: .2rem; flex: none;}}
.fr-pts2 > div {{text-align: right; min-width: 48px;}}
.fr-pts2 span {{display: block; font-size: .53rem; letter-spacing: .1em; color: {MUTED}; font-weight: 800;}}
.fr-pts2 b {{font-size: 1rem; color: {TEXT}; font-weight: 800;}}
.fr-pts2 b.fin {{color: #4ade80;}}
.fr-pts2 b.na {{color: #475569; font-weight: 600;}}
.fr-slot.bn {{background: transparent; border-style: dashed; flex-direction: column; line-height: 1; gap: 1px;}}
.fr-slot.bn i {{font-style: normal; font-size: .5rem; color: {MUTED}; letter-spacing: .08em;}}
.fr-pts span {{display: block; font-size: .55rem; letter-spacing: .1em; color: {MUTED}; font-weight: 800;}}
.fr-pts b {{font-size: 1.02rem; color: {TEXT}; font-weight: 800;}}
.fr-pts.final span {{color: {GREEN};}}
.fr-pts.final b {{color: #4ade80;}}
.fr-move {{display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; background: {CARD}; border: 1px solid {BORDER};
          border-radius: 12px; padding: .6rem .8rem; margin-bottom: .45rem; font-size: .88rem;}}
.fr-move a {{color: {TEXT} !important; font-weight: 700; text-decoration: none !important;}}
.fr-move-side {{display: flex; align-items: center; gap: .35rem; flex: 1; min-width: 220px;}}
.fr-move-arrow {{color: {MUTED}; font-size: 1.1rem;}}
.fr-move-gain {{font-weight: 900; color: #4ade80; font-size: 1.05rem; min-width: 52px; text-align: right;}}
.fr-dim {{color: {MUTED}; font-size: .76rem;}}
.fr-news {{padding: .65rem 0; border-bottom: 1px solid {BORDER};}}
.fr-news:last-child {{border-bottom: none;}}
.fr-news-t a {{color: {TEXT} !important; font-weight: 700; text-decoration: none !important; font-size: .92rem;}}
.fr-news-t a:hover {{color: {GOLD} !important;}}
.fr-news-b {{color: #c3cddb; font-size: .82rem; margin-top: .2rem; line-height: 1.4;}}
.fr-news-m {{color: {MUTED}; font-size: .72rem; margin-top: .25rem;}}
.fr-upd {{display: flex; gap: .6rem; padding: .45rem 0; border-bottom: 1px solid {BORDER}55;}}
.fr-upd:last-child {{border-bottom: none;}}
.fr-upd-dot {{width: 8px; height: 8px; border-radius: 50%; margin-top: .4rem; flex: none;}}
.fr-upd-h {{font-size: .68rem; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; color: {MUTED};}}
.fr-upd-t {{font-size: .84rem; color: {TEXT}; line-height: 1.35;}}

/* ---------- gradients & colour system ---------- */
.stApp {{background:
    radial-gradient(1100px 620px at 8% -8%, rgba(124,58,237,.17), transparent 62%),
    radial-gradient(900px 520px at 100% 0%, rgba(59,130,246,.15), transparent 60%),
    radial-gradient(900px 700px at 50% 115%, rgba(245,179,1,.07), transparent 60%),
    {BG} !important;}}
[data-testid="stSidebar"] {{background: linear-gradient(180deg, #141f38 0%, #0e1628 55%, #0b1220 100%) !important;
                           border-right: 1px solid {BORDER};}}
.fr-card, .fr-stats, .fr-tc, .fr-game, .fr-move, .fr-note, .fr-gl, .fr-strip, .fr-wk {{
    background: linear-gradient(160deg, #17223d 0%, #121a2b 55%, #0f1727 100%) !important;}}
.fr-kpi {{background: linear-gradient(135deg, var(--accbg, rgba(255,255,255,.03)) 0%, #131c30 58%, #101828 100%) !important;}}
.fr-kpi:before {{width: 4px; background: linear-gradient(180deg, var(--acc), transparent);}}
.fr-sec {{display: flex; align-items: center; gap: .55rem;}}
.fr-sec:before {{content: ""; width: 22px; height: 3px; border-radius: 3px;
                background: linear-gradient(90deg, {GOLD}, #f97316, #ef4444);}}
.fr-pl {{border-radius: 9px;}}
.fr-pl:hover {{filter: brightness(1.12);}}
.stTabs [data-baseweb="tab-list"] {{border-bottom: 1px solid {BORDER};}}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{background: linear-gradient(180deg, rgba(245,179,1,.16), rgba(245,179,1,0));
                                                    border-radius: 9px 9px 0 0;}}
.stTabs [data-baseweb="tab-highlight"] {{background: linear-gradient(90deg, {GOLD}, #f97316) !important; height: 3px;}}
div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button,
div[data-testid="stPopover"] button, div[data-testid="stFormSubmitButton"] > button {{
    background: linear-gradient(180deg, #1c2945 0%, #141d33 100%); border: 1px solid #2b3c60; border-radius: 11px;
    color: {TEXT}; transition: border-color .15s, box-shadow .15s;}}
div[data-testid="stButton"] > button:hover, div[data-testid="stDownloadButton"] > button:hover,
div[data-testid="stPopover"] button:hover, div[data-testid="stFormSubmitButton"] > button:hover {{
    border-color: {GOLD}; box-shadow: 0 0 0 1px rgba(245,179,1,.35), 0 6px 18px rgba(245,179,1,.12); color: #fff;}}
button[kind="primary"], button[data-testid="stBaseButton-primary"], button[kind="primaryFormSubmit"],
button[data-testid="stBaseButton-primaryFormSubmit"] {{
    background: linear-gradient(135deg, #f5b301 0%, #f97316 100%) !important; color: #111 !important; border: none !important;
    font-weight: 800 !important; box-shadow: 0 6px 20px rgba(245,158,11,.25) !important;}}
button[data-testid="stBaseButton-segmented_control"], button[kind="segmented_control"] {{
    background: linear-gradient(180deg, #19243f, #131c31) !important; border-color: #2b3c60 !important;}}
button[data-testid="stBaseButton-segmented_controlActive"], button[kind="segmented_controlActive"] {{
    background: linear-gradient(135deg, rgba(245,179,1,.30), rgba(249,115,22,.20)) !important;
    border-color: {GOLD} !important; color: #fff !important; box-shadow: 0 0 14px rgba(245,179,1,.18);}}
[data-baseweb="select"] > div {{background: linear-gradient(180deg, #18233d, #121a2c) !important; border-color: #2b3c60 !important;
                               border-radius: 11px !important;}}
[data-baseweb="select"] input[type="search"]::-webkit-search-cancel-button {{display: none;}}
[data-testid="stExpander"] details {{background: linear-gradient(160deg, #16213b, #101827); border-color: {BORDER};
                                    border-radius: 12px;}}
/* slim league / team bar */
.fr-lbar {{display: flex; flex-wrap: wrap; align-items: center; gap: .45rem .55rem; padding: .62rem 1rem; margin: .1rem 0 .7rem;
          border-radius: 14px; border: 1px solid {BORDER}; border-left: 4px solid var(--pc);
          background: linear-gradient(110deg, color-mix(in srgb, var(--pc) 26%, transparent) 0%, #17223d 38%, #111a2b 100%);}}
.fr-lbar-name {{font-size: 1.22rem; font-weight: 900; color: #fff; margin-right: .35rem; letter-spacing: -.01em;}}
.fr-lchip {{font-size: .7rem; font-weight: 800; padding: .14rem .5rem; border-radius: 999px; color: #e2e8f0;
           background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);}}
.fr-lchip.plat {{background: color-mix(in srgb, var(--pc) 30%, transparent); border-color: var(--pc);}}
.fr-lchip.sc {{background: linear-gradient(90deg, rgba(245,179,1,.18), rgba(249,115,22,.10)); border-color: rgba(245,179,1,.45);
              color: #fde68a;}}
.fr-lbar-sync {{margin-left: auto; font-size: .7rem; color: {MUTED};}}
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
    "Proj/G": "The model's rest-of-season points per game: usage (expected points) first, last season as a prior "
              "early on, efficiency mostly regressed, touchdown luck removed, and remaining schedule.",
    "Signal": "Trade-market call from the model: Buy low (scoring under his role), Sell high (scoring over it), "
              "Buy high (good and role growing), Sell low (role shrinking).",
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

DATA_VERSION = 9  # bump whenever player_report.py changes what a Season holds, so stale cached data is dropped


def preset_scoring(fmt_name):
    sc = dict(pr.SCORING)
    sc["rec"] = pr.FORMAT_REC.get(fmt_name, 0.5)
    sc.setdefault("te_rec", 0)
    return sc


def get_season(season, scoring):
    """scoring: "half" / "ppr" / "standard", or a full league scoring dict."""
    base = _load_base(season, DATA_VERSION)
    if isinstance(scoring, dict):
        sc, name = {**preset_scoring("half"), **scoring}, "custom"
        for preset in ("half", "ppr", "standard"):  # a league that matches a preset shares its data
            if pr.scoring_key(clean_scoring(sc)) == pr.scoring_key(clean_scoring(preset_scoring(preset))):
                sc, name = preset_scoring(preset), preset
                break
    else:
        sc, name = preset_scoring(scoring), scoring
    if pr.scoring_key(sc) == base.scoring_key and name == base.fmt_name:
        return base
    return _rescored(base, (season, base.loaded_at, pr.scoring_key(sc), name), sc, name)


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=1, show_spinner=False)
def _load_base(season, version):
    S = pr.Season(season, preset_scoring("half"), "half")
    pr.load_season(S)
    S.loaded_at = datetime.now()
    return S


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=12, show_spinner=False)
def _rescored(_base, key, _sc, name):
    return pr.rescore(_base, _sc, name)


def skey(S, *extra):
    return (S.season, S.fmt_name, getattr(S, "scoring_key", None), S.loaded_at) + extra


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=300, show_spinner=False)
def get_report(_S, key):
    return pr.build_report(_S, key[-1])


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def get_player_list(_S, key):
    rows = sorted(_S.season_tot.items(), key=lambda kv: -kv[1]["pts"])
    labels = {pid: f"{t['name']}  ·  {t['pos']}  ·  {t['team']}  ·  {t['ppg']:.1f} PPG" for pid, t in rows}
    return [pid for pid, _ in rows], labels


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def get_backtest(_S, key):
    return pr.backtest(_S)


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def get_home(_S, key):
    S = _S
    out = {"market": [], "trend": [], "week_top": {}, "season_top": {}, "matchups": {}, "next_week": None}
    for pos in pr.FANTASY_POS:
        pool, _ = pr.position_pool(S, pos)
        for pid in pool:
            mv = pr.market_view(S, pid)
            if not mv:
                continue
            out["market"].append(mv)
            rs = mv["role"]
            if rs and (rs["flag"] or abs(rs["z"]) >= 1.6) and abs(rs["delta"]) >= 1.5:
                out["trend"].append({**mv, "val": rs["delta"], "l3": rs["recent"], "season": rs["before"],
                                     "z": rs["z"], "parts": rs["parts"], "confirmed": rs["flag"]})
        out["week_top"][pos] = sorted([r for rs_ in S.weekly.values() for r in rs_
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
                        lst.append({"off": off, "def": de, "rank": f["rank"], "n": f["n"], "avg": f["avg"],
                                    "adj": f.get("adj")})
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
    accbg = f"{acc}2b" if (isinstance(acc, str) and acc.startswith("#") and len(acc) == 7 and acc != BORDER) else \
        "rgba(255,255,255,.03)"
    return (f'<div class="fr-kpi" style="--acc:{acc};--accbg:{accbg}"><div class="l">{esc(label)}</div>'
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


# ------------------------------------------------------------------------------------
# News & updates (bottom of the player page)
# ------------------------------------------------------------------------------------

ESPN_NEWS = "https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players"
GOOGLE_NEWS = "https://news.google.com/rss/search"


def espn_id_for(S, pid):
    rev = S.__dict__.setdefault("_espn_rev", {})
    if not rev:
        for eid, gid in ensure_idmap(S).get("espn", {}).items():
            rev[gid] = eid
    return rev.get(pid)


def _clean_text(t, n=230):
    t = re.sub(r"<[^>]+>", " ", html.unescape(str(t or "")))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def parse_espn_news(data):
    items = []
    feed = (data or {}).get("feed") or (data or {}).get("articles") or (data or {}).get("news") or []
    for it in feed:
        head = it.get("headline") or it.get("title")
        if not head:
            continue
        link = (((it.get("links") or {}).get("web") or {}).get("href")) or it.get("link")
        items.append({"title": _clean_text(head, 160), "blurb": _clean_text(it.get("story") or it.get("description")),
                      "when": it.get("published") or it.get("lastModified"), "source": "ESPN", "url": link})
    return items


def parse_google_rss(xml_text, name):
    import xml.etree.ElementTree as ET
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    last = name.split()[-1].lower() if name else ""
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        src = it.findtext("source") or ""
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        if last and last not in title.lower():
            continue  # keep it about him
        items.append({"title": _clean_text(title, 160), "blurb": "", "when": it.findtext("pubDate"),
                      "source": src or "News", "url": it.findtext("link")})
    return items


def _when(ts):
    if not ts:
        return None
    from email.utils import parsedate_to_datetime
    try:
        d = parsedate_to_datetime(ts) if "," in str(ts) else datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def ago(d):
    if not d:
        return ""
    s_ = (datetime.now(timezone.utc) - d).total_seconds()
    if s_ < 3600:
        return f"{max(1, int(s_ // 60))}m ago"
    if s_ < 86400:
        return f"{int(s_ // 3600)}h ago"
    days = int(s_ // 86400)
    return f"{days}d ago" if days < 14 else d.strftime("%b %d")


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_news(name, team, espn_id):
    """Headlines for a player: ESPN's fantasy news feed first, Google News as a backup. Cached 30 minutes."""
    import requests
    items = []
    if espn_id:
        try:
            r = requests.get(ESPN_NEWS, params={"limit": 8, "playerId": espn_id}, timeout=8,
                             headers={"User-Agent": "Mozilla/5.0 (FantasyReports)"})
            if r.ok:
                items = parse_espn_news(r.json())
        except Exception:
            pass
    if len(items) < 3:
        try:
            q = f'"{name}" {team or ""} NFL'.strip()
            r = requests.get(GOOGLE_NEWS, params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=8,
                             headers={"User-Agent": "Mozilla/5.0 (FantasyReports)"})
            if r.ok:
                seen = {i["title"].lower() for i in items}
                items += [i for i in parse_google_rss(r.text, name) if i["title"].lower() not in seen]
        except Exception:
            pass
    for i in items:
        d = _when(i["when"])
        i["ts"] = d.isoformat() if d else ""
    items.sort(key=lambda i: i["ts"], reverse=True)
    return items[:8]


def player_updates(S, rep):
    """Site-generated updates: injury report history, recent games, depth chart and role changes."""
    pid, pos = rep["pid"], rep["pos"]
    out = []
    hist = getattr(S, "inj_hist", {}).get(pid, [])
    for h in hist[-4:][::-1]:
        bits = [b for b in [h.get("status"), h.get("injury"), h.get("practice")] if b]
        if bits:
            out.append(("down" if h.get("status") else "info", f"Week {h['week']} injury report", " · ".join(bits)))
    p = pr.project_player(S, pid)
    if p:
        for tone, text in p["reasons"]:
            if text.startswith(("Depth chart", "Missed his team")):
                out.append((tone, "This week", text))
    played = [w for w in rep["weekly"] if not w.get("status")]
    for w in played[-3:][::-1]:
        bits = [f"{w.get('pts', 0):.1f} pts" + (f" ({pos}{w['rank']})" if w.get("rank") else "")]
        if w.get("snap_pct") is not None:
            bits.append(f"{w['snap_pct']:.0f}% snaps")
        if pos in ("WR", "TE", "RB") and w.get("targets"):
            bits.append(f"{int(w['targets'])} targets")
        if pos in ("RB", "QB") and w.get("carries"):
            bits.append(f"{int(w['carries'])} carries")
        if pos == "QB" and w.get("pass_yds"):
            bits.append(f"{int(w['pass_yds'])} pass yds")
        col = "up" if (w.get("rank") or 99) <= (12 if pos in ("QB", "TE") else 24) else "info"
        out.append((col, f"Week {w['week']} {w.get('opp', '')}", " · ".join(bits)))
    missed = [w for w in rep["weekly"] if w.get("status") == "Did not play"][-2:]
    for w in missed:
        out.append(("down", f"Week {w['week']}", "Did not play"))
    for t in rep.get("trends", []):
        if abs(t["delta"]) >= t["thr"] and not t["label"].startswith("Fantasy points"):
            out.append(("up" if t["delta"] > 0 else "down", "Role trend",
                        f"{t['label']} {'up' if t['delta'] > 0 else 'down'}: {fmt(t['last3'], t['kind'])} over the "
                        f"last 3 games vs {fmt(t['season'], t['kind'])} on the season"))
    return out


def render_news(S, rep):
    sec("News & updates")
    left, right = st.columns([3, 2])
    with left:
        with st.spinner("Loading headlines..."):
            try:
                items = fetch_news(rep["name"], rep["team"], espn_id_for(S, rep["pid"]))
            except Exception:
                items = []
        if items:
            rows = []
            for i in items:
                when = ago(_when(i["ts"])) if i.get("ts") else ""
                title = (f'<a href="{esc(i["url"])}" target="_blank" rel="noopener">{esc(i["title"])}</a>'
                         if i.get("url") else esc(i["title"]))
                blurb = f'<div class="fr-news-b">{esc(i["blurb"])}</div>' if i.get("blurb") else ""
                rows.append(f'<div class="fr-news"><div class="fr-news-t">{title}</div>{blurb}'
                            f'<div class="fr-news-m">{esc(i["source"])}{" · " + when if when else ""}</div></div>')
            H(f'<div class="fr-card" style="padding:.3rem 1rem">{"".join(rows)}</div>')
            st.caption("Headlines open the full story at the source. Refreshed every 30 minutes.")
        else:
            H(f'<div class="fr-card"><div class="fr-sub">No recent headlines found for {esc(rep["name"])}.</div></div>')
    with right:
        ups = player_updates(S, rep)
        if ups:
            rows = []
            for tone, head, text in ups:
                c = {"up": GREEN, "down": RED}.get(tone, BLUE)
                rows.append(f'<div class="fr-upd"><span class="fr-upd-dot" style="background:{c}"></span><div>'
                            f'<div class="fr-upd-h">{esc(head)}</div><div class="fr-upd-t">{esc(text)}</div></div></div>')
            H(f'<div class="fr-card" style="padding:.5rem .9rem">{"".join(rows)}</div>')
            st.caption("Status and usage updates from the official injury report and game data.")


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
    render_news(S, rep)
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

    # 4. Role changes (usage rising / falling)
    tr = d["trend"]
    rising = sorted([x for x in tr if x["val"] > 0], key=lambda x: (-x["confirmed"], -x["val"]))[:6]
    falling = sorted([x for x in tr if x["val"] < 0], key=lambda x: (-x["confirmed"], x["val"]))[:6]

    def parts_txt(x):
        bits = []
        p_ = x["parts"]
        if p_.get("snap") is not None and abs(p_["snap"]) >= 5:
            bits.append(f"snaps {p_['snap']:+.0f}")
        if p_.get("route") is not None and abs(p_["route"]) >= 5:
            bits.append(f"routes {p_['route']:+.0f}")
        if p_.get("share") is not None and abs(p_["share"]) >= 3 and x["pos"] != "QB":
            bits.append(f"share {p_['share']:+.0f}")
        return f"{x['pos']} · {x['team']} · {x['l3']:.1f} xFP last 3 vs {x['season']:.1f}" + \
            (f" · {', '.join(bits)}" if bits else "")
    sec("Role changes (usage that's really moving, not noise)")
    H('<div class="fr-grid g2">' + "".join([
        list_card("Usage rising", "Expected points up beyond normal week-to-week swings", BLUE,
                  [list_item(x["pid"], x["name"], parts_txt(x), ("▲ " if x["confirmed"] else "△ ") + f"{x['val']:.1f}",
                             BLUE, x["team"]) for x in rising]),
        list_card("Usage falling", "Expected points down beyond normal week-to-week swings", AMBER,
                  [list_item(x["pid"], x["name"], parts_txt(x), ("▼ " if x["confirmed"] else "▽ ") +
                             f"{abs(x['val']):.1f}", AMBER, x["team"]) for x in falling]),
    ]) + "</div>")
    H('<div class="fr-sub" style="margin-top:.4rem">▲/▼ = confirmed role change (snaps, routes or share moved with it); '
      '△/▽ = notable but not yet confirmed.</div>')

    # 5. Trade market: model vs production
    mk = d["market"]

    def q(tag, key, rev):
        return sorted([x for x in mk if tag in x["tags"]], key=lambda x: x[key], reverse=rev)[:6]

    def sub_mk(x):
        why = " · ".join(x["why"][:2])
        return f"{x['pos']} · {x['team']} · model {x['ros_rate']:.1f}/g vs {x['ppg']:.1f} so far" + (f" · {why}" if why else "")
    sec("Trade market (what the model expects vs what he's scored)")
    H('<div class="fr-grid g2">' + "".join([
        list_card("Buy low", "Underperforming what his role should produce. Expect more.", GREEN,
                  [list_item(x["pid"], x["name"], sub_mk(x), f"{x['gap']:+.1f}", GREEN, x["team"])
                   for x in q("buy_low", "gap", True)]),
        list_card("Sell high", "Outscoring his role (TD luck, unsustainable efficiency). Expect less.", RED,
                  [list_item(x["pid"], x["name"], sub_mk(x), f"{x['gap']:+.1f}", RED, x["team"])
                   for x in q("sell_high", "gap", False)]),
        list_card("Buy high", "Already good, and his role is growing. Worth paying full price.", BLUE,
                  [list_item(x["pid"], x["name"], sub_mk(x), f"▲ {x['role']['delta']:.1f}", BLUE, x["team"])
                   for x in sorted([x for x in mk if "buy_high" in x["tags"]], key=lambda x: -x["role"]["delta"])[:6]]),
        list_card("Sell low", "Role is shrinking. Move on before his value drops further.", AMBER,
                  [list_item(x["pid"], x["name"], sub_mk(x), f"▼ {abs(x['role']['delta']):.1f}", AMBER, x["team"])
                   for x in sorted([x for x in mk if "sell_low" in x["tags"]], key=lambda x: x["role"]["delta"])[:6]]),
    ]) + "</div>")
    H('<div class="fr-sub" style="margin-top:.4rem">Model = rest-of-season points per game from usage (the stable '
      'signal), last season as a prior, efficiency mostly regressed, touchdown luck removed, and remaining '
      'schedule. Number = model minus production, compared with the position\'s typical gap.</div>')
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
RANK_BY = {"Projection": "Proj/G", "Total points": "Total pts", "Points per game": "PPG", "Expected points": "xFP/G"}
SIGNAL_LABEL = {"buy_low": "Buy low", "sell_high": "Sell high", "buy_high": "Buy high", "sell_low": "Sell low"}


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
        by = segmented("Rank by", list(RANK_BY), "rank_by", "Projection", lambda o: f"Rank by {o.lower()}")
    with st.spinner("Ranking players..."):
        pool, _ = pr.position_pool(S, pos)
    rows = []
    for pid, m in pool.items():
        t = S.season_tot.get(pid, {})
        mv = pr.market_view(S, pid)
        b = pr.player_base(S, pid)
        r = {"pid": pid, "Logo": logo_url(t.get("team")), "Player": t.get("name"), "Team": t.get("team"),
             "Games": m["games"],
             "Proj/G": (mv["ros_rate"] if mv else (b["base"] if b else None)),
             "Signal": " · ".join(SIGNAL_LABEL[x] for x in (mv or {}).get("tags", [])),
             "Total pts": t.get("pts"), "PPG": m.get("ppg"), "xFP/G": m.get("xfp_pg"),
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
           "Proj/G": st.column_config.NumberColumn(format="%.1f", help="Model's rest-of-season points per game "
                                                                       "(usage-driven, schedule-adjusted)"),
           "Signal": st.column_config.TextColumn(help="Buy low / Sell high / Buy high / Sell low from the trade model"),
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
    sig_col = {"Buy low": GREEN, "Sell high": RED, "Buy high": BLUE, "Sell low": AMBER}
    sty = smap(sty, lambda v: (f"color: {sig_col.get(str(v).split(' · ')[0])}; font-weight: 700" if v else ""), ["Signal"])
    try:
        ev = st.dataframe(sty, use_container_width=True, hide_index=True, column_config=cfg, height=640,
                          on_select="rerun", selection_mode="single-row", key=f"rank_table_{pos}_{by}")
        sel = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
    except TypeError:
        st.dataframe(sty, use_container_width=True, hide_index=True, column_config=cfg, height=640)
        sel = []
    note = {"Projection": "Projection ranks by the model's rest-of-season points per game: usage first, last season "
                          "as a prior, efficiency regressed, TD luck removed, schedule included. The best guide for "
                          "who will score the most from here.",
            "Total points": "Total points rewards availability, like your league's standings.",
            "Points per game": "Points per game ignores missed games, so players with fewer games can rank high.",
            "Expected points": "Expected points ranks by usage alone, the most stable predictor of future scoring."}[by]
    st.caption(f"{len(df)} {pos}s with {S.min_games}+ games and real volume. {note} "
               "Rank colour: green top 12, blue 13-24, gold 25-36.")
    if sel:
        st.session_state.pending = {"player": df.iloc[sel[0]]["pid"], "view": "Player"}
        st.rerun()
    with st.expander("📏 How accurate is the projection model? (tested on this season)"):
        st.caption("For every week this season, each player is projected using only the games before it, then checked "
                   "against what he actually scored over his next 3 games. Compared with the two simple methods most "
                   "rankings use. Lower error and higher correlation are better.")
        if st.button("Run the accuracy check", key="bt_run"):
            st.session_state["_bt_on"] = True
        if st.session_state.get("_bt_on"):
            with st.spinner("Re-projecting every week of the season..."):
                bt = get_backtest(S, skey(S))
            if not bt:
                st.info("Not enough games played yet to test.")
            else:
                rows = []
                for lab, d in bt["by_pos"].items():
                    best = min(("model", "ppg", "last3"), key=lambda k: d[k]["mae"])
                    imp = (1 - d["model"]["mae"] / d["ppg"]["mae"]) * 100 if d["ppg"]["mae"] else 0
                    rows.append({"Group": lab, "Tests": d["n"],
                                 "Model error": round(d["model"]["mae"], 2), "PPG-so-far error": round(d["ppg"]["mae"], 2),
                                 "Last-3 error": round(d["last3"]["mae"], 2),
                                 "Model vs PPG": f"{imp:+.0f}%",
                                 "Model corr": round(d["model"]["corr"], 3), "PPG corr": round(d["ppg"]["corr"], 3),
                                 "Most accurate": {"model": "Model", "ppg": "PPG so far", "last3": "Last 3"}[best]})
                styled_df(pd.DataFrame(rows), cell={"Most accurate": lambda v: GREEN if v == "Model" else AMBER,
                                                    "Model vs PPG": lambda v: GREEN if str(v).startswith("+") else RED})
                st.caption("Error = average miss in fantasy points per game over the next 3 games. Model vs PPG = how "
                           "much smaller the model's error is. Rest-of-season matchups and injuries are left out here so "
                           "the comparison is apples to apples.")
    glossary(["Proj/G", "Signal", "Total pts", "PPG", "xFP", "+/- exp", "TD luck", "Snap %"] + POS_TERMS[pos])


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
             "SUPERFLEX": {"QB", "RB", "WR", "TE"}, "K": {"K"}, "DEF": {"DEF"}}
SLOT_LABEL = {"FLEX": "W/R/T", "SUPERFLEX": "Q/W/R/T"}
MAX_TEAMS, MAX_ROSTER = 12, 30
COOKIE = "fr_session"
SESSION_DAYS, SHORT_SESSION_DAYS = 30, 1
MAX_FAILS, LOCK_MINUTES, CODE_MINUTES, CODE_TRIES = 5, 10, 15, 5
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC_LOGIN_ERROR = "Username or password is incorrect."


def text_in(label, autocomplete="off", **kw):
    """st.text_input with an autocomplete hint so browsers and password managers know what each field is."""
    try:
        return st.text_input(label, autocomplete=autocomplete, **kw)
    except TypeError:  # older Streamlit without the autocomplete option
        return st.text_input(label, **kw)


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
    c = f"{COOKIE}={val}; path=/; max-age={age}; SameSite=Lax; Secure"
    components.html(
        "<script>(function(){var c='" + c + "';"
        "var ws=[window];try{if(window.parent&&window.parent!==window)ws.push(window.parent)}catch(e){}"
        "try{if(window.top&&ws.indexOf(window.top)<0)ws.push(window.top)}catch(e){}"
        "ws.forEach(function(w){try{w.document.cookie=c}catch(e){}});})();</script>", height=0)


def read_cookie():
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


AUTH_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0"><script>
(function(){
  var KEY = "fr_session", last = null;
  function post(m){ m.isStreamlitMessage = true; window.parent.postMessage(m, "*"); }
  function read(){ try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  window.addEventListener("message", function(ev){
    var d = ev.data;
    if (!d || d.type !== "streamlit:render") return;
    var a = d.args || {}, sig = JSON.stringify(a);
    if (sig === last) return;
    last = sig;
    try {
      if (a.op === "set" && a.token) {
        localStorage.setItem(KEY, a.token);
        var exp = Date.now() + (a.days || 30) * 86400000;
        localStorage.setItem(KEY + "_exp", String(exp));
      } else if (a.op === "clear") {
        localStorage.removeItem(KEY); localStorage.removeItem(KEY + "_exp");
      }
    } catch (e) {}
    var tok = read();
    try { var exp2 = +localStorage.getItem(KEY + "_exp"); if (exp2 && exp2 < Date.now()) { tok = ""; } } catch (e) {}
    post({ type: "streamlit:setComponentValue", value: { token: tok, n: a.n || 0, ok: true }, dataType: "json" });
  });
  post({ type: "streamlit:componentReady", apiVersion: 1 });
  post({ type: "streamlit:setFrameHeight", height: 0 });
})();
</script></body></html>"""


@st.cache_resource(show_spinner=False)
def _auth_component():
    import streamlit.components.v1 as components
    d = os.path.join(tempfile.gettempdir(), "fr_auth_store_v1")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(AUTH_HTML)
    return components.declare_component("fr_auth_store", path=d)


UI_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0"><script>
(function(){
  function post(m){ m.isStreamlitMessage = true; window.parent.postMessage(m, "*"); }
  // Dropdown search boxes are plain text inputs, so browsers and password managers mistake them for a username
  // field and pop up saved logins. Mark every one as "not a login field" and keep doing it as new ones appear.
  function fix(doc){
    var ins = doc.querySelectorAll('[data-baseweb="select"] input, [role="combobox"]');
    for (var i = 0; i < ins.length; i++) {
      var el = ins[i];
      if (el.tagName !== "INPUT" || el.dataset.frFix === "1") continue;
      el.setAttribute("autocomplete", "off");
      el.setAttribute("autocorrect", "off");
      el.setAttribute("spellcheck", "false");
      el.setAttribute("data-lpignore", "true");
      el.setAttribute("data-1p-ignore", "true");
      el.setAttribute("data-bwignore", "true");
      el.setAttribute("data-form-type", "other");
      el.setAttribute("name", "fr-pick-" + Math.random().toString(36).slice(2, 9));
      try { el.type = "search"; } catch (e) {}
      el.dataset.frFix = "1";
    }
  }
  try {
    var d = window.parent.document;
    fix(d);
    var queued = false;
    new MutationObserver(function(){
      if (queued) return; queued = true;
      setTimeout(function(){ queued = false; fix(d); }, 60);
    }).observe(d.body, { childList: true, subtree: true });
  } catch (e) {}
  post({ type: "streamlit:componentReady", apiVersion: 1 });
  post({ type: "streamlit:setFrameHeight", height: 0 });
})();
</script></body></html>"""


@st.cache_resource(show_spinner=False)
def _ui_component():
    import streamlit.components.v1 as components
    d = os.path.join(tempfile.gettempdir(), "fr_ui_helper_v1")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(UI_HTML)
    return components.declare_component("fr_ui_helper", path=d)


def ui_helper():
    try:
        _ui_component()(key="fr_ui_helper", default=None)
    except Exception:
        pass


def device_store():
    """Invisible helper that keeps the sign-in token in this browser's local storage. Returns
    {"token": ...} once the browser has answered, or None on the very first moment of a visit."""
    op = st.session_state.pop("_store_op", None)
    if op:
        st.session_state._store_args = {"op": op[0], "token": op[1], "days": op[2] if len(op) > 2 else 30,
                                        "n": int(datetime.now().timestamp() * 1000)}
    try:
        return _auth_component()(key="fr_auth_store", default=None, **st.session_state.get("_store_args", {}))
    except Exception:
        return {"token": "", "ok": False}


def restore_session():
    """On each visit: keep the browser's saved sign-in in sync, and sign back in from it."""
    op = st.session_state.pop("_cookie_op", None)
    if op:
        write_cookie(*op)
    if not get_db():
        st.session_state._store_ready = True
        return
    val = device_store()
    st.session_state._store_ready = val is not None
    if st.session_state.get("account") or st.session_state.get("_signed_out"):
        return
    tok = ((val or {}).get("token") or "") or (read_cookie() or "")
    if not tok or st.session_state.get("_cookie_checked") == tok:
        return
    st.session_state._cookie_checked = tok
    try:
        a = Accounts(get_db()).session_account(tok)
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
    st.session_state._store_op = ("set", tok, days)


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
    st.session_state._store_op = ("clear", "")


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
    order = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DEF"]
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
    order = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DEF"]
    lineup.sort(key=lambda l: order.index(l["slot"]) if l["slot"] in order else 99)
    return lineup, bench


def grade_for(ratio):
    if ratio is None:
        return "–", SLATE
    for cut, g_, c in [(1.15, "A", GREEN), (1.05, "B", "#86efac"), (0.95, "C", AMBER), (0.85, "D", "#fca5a5")]:
        if ratio >= cut:
            return g_, c
    return "F", RED


def analyze_team(S, team, owner_of=None, my_team_id=None):
    """owner_of: {pid: team dict} for every rostered player in the league (league mode)."""
    slots = {**DEFAULT_SLOTS, **(team.get("slots") or {})}
    n_teams = int(team.get("teams_in_league") or 12)
    week = pr.next_week(S)
    all_keys = list(dict.fromkeys(team.get("roster", [])))
    projs = {}
    for k in all_keys:
        p = project_any(S, k, week) if week else None
        if p:
            projs[k] = p
    roster = [k for k in projs if projs[k]["pos"] in pr.FANTASY_POS and pr.player_base(S, k)]
    missing = [k for k in all_keys if k not in projs]
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
    out["bye_names"] = [p["name"] for p in projs.values() if p and p["bye"]]
    out["inj_list"] = [(p["name"], (p.get("inj_status") or "").split(" (")[0], p["injf"] == 0)
                       for p in projs.values() if p and p.get("inj_status") and not p["bye"]]

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
    for slot in ("K", "DEF"):
        n = slots.get(slot, 0)
        if n:
            top = kdef_pool(S, slot, week)[: n_teams * n]
            total_avg += (mean([p["proj"] for p in top]) or 0) * n
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
            if owner_of is not None and (p["pid"] not in owner_of or owner_of[p["pid"]]["id"] == my_team_id):
                continue  # league mode: trade targets must be on someone else's roster
            m = pr.player_base(S, p["pid"])["m"]
            worst = min([x["proj"] for x in out["grades"][pos]["players"]] or [0])
            if pr.player_base(S, p["pid"])["base"] <= worst:
                continue
            cands.append({"pid": p["pid"], "p": p, "m": m, "ros": pr.ros_value(S, p["pid"]),
                          "buy_low": (m.get("regress_pg") or 0) <= -1.0,
                          "owner": (owner_of or {}).get(p["pid"], {}).get("name")})
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
    kd = [k for k in projs if projs[k]["pos"] in ("K", "DEF")]
    for w in range(week, pr.FANTASY_PLAYOFF_WEEKS[-1] + 1):
        pw = {pid: pr.project_player(S, pid, w, injuries=(w == week)) for pid in roster}
        pw.update({k: project_any(S, k, w) for k in kd})
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
# League sync: Sleeper (public API), ESPN (API, or the bookmark for private leagues),
# Yahoo (the bookmark reads your logged-in league pages and sends the rosters here)
# ------------------------------------------------------------------------------------

SLEEPER_API = "https://api.sleeper.app/v1"
ESPN_API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{lid}"
PLATFORM_LABEL = {"sleeper": "Sleeper", "espn": "ESPN", "yahoo": "Yahoo", "manual": "Manual"}
SLEEPER_SLOTS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "FLEX": "FLEX", "WRRB_FLEX": "FLEX",
                 "REC_FLEX": "FLEX", "SUPER_FLEX": "SUPERFLEX"}
ESPN_SLOTS = {"0": "QB", "2": "RB", "4": "WR", "6": "TE", "23": "FLEX", "3": "FLEX", "5": "FLEX", "7": "SUPERFLEX"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(n):
    w = re.sub(r"[^a-z0-9 ]", "", str(n or "").lower().replace("-", " ")).split()
    return " ".join(x for x in w if x not in SUFFIXES)


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=4, show_spinner=False)
def name_index(_S, key):
    idx = defaultdict(list)
    for pid, p in _S.players.items():
        if p.get("pos") in pr.FANTASY_POS and p.get("name"):
            idx[norm_name(p["name"])].append(pid)
    for k in idx:
        idx[k].sort(key=lambda pid: -(_S.season_tot.get(pid, {}).get("pts") or -1))
    return idx


def ensure_idmap(S):
    """Load the cross-platform player ID table if this Season doesn't have it yet."""
    if getattr(S, "idmap", None) and any(S.idmap.values()):
        return S.idmap
    S.idmap = {"sleeper": {}, "espn": {}, "yahoo": {}}
    try:
        import nflreadpy as nfl
        for r in nfl.load_ff_playerids().to_dicts():
            gid = r.get("gsis_id")
            if not gid:
                continue
            for plat in S.idmap:
                v = r.get(f"{plat}_id")
                if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
                    continue
                try:
                    v = str(int(float(v)))
                except (TypeError, ValueError):
                    v = str(v).strip()
                S.idmap[plat][v] = gid
    except Exception:
        pass  # fall back to name matching
    return S.idmap


def map_player(S, plat, ext_id, name=None):
    idmap = ensure_idmap(S)
    gid = idmap.get(plat, {}).get(str(ext_id).strip()) if ext_id is not None else None
    if gid and (gid in S.season_tot or gid in S.players):
        return gid
    if name:
        cands = name_index(S, skey(S)).get(norm_name(name), [])
        if cands:
            return cands[0]
    return None


def http_json(url, params=None, cookies=None):
    import requests
    r = requests.get(url, params=params, cookies=cookies, timeout=25,
                     headers={"User-Agent": "Mozilla/5.0 (FantasyReports)", "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise PermissionError("This league is private.")
    if r.status_code == 404:
        raise LookupError("Not found. Check the ID.")
    r.raise_for_status()
    return r.json()


def fmt_for_rec(rec):
    rec = float(rec or 0)
    return "ppr" if rec >= 0.75 else "half" if rec >= 0.25 else "standard"


def _finish_league(league):
    league["kind"] = "league"
    league["teams_in_league"] = len(league["teams"])
    league["synced_at"] = _now().isoformat()
    my = league.get("my_team")
    if my is not None and str(my) not in {t["id"] for t in league["teams"]}:
        league["my_team"] = None
    league["name"] = league.get("name") or f"{PLATFORM_LABEL[league['platform']]} league"
    return league


# ----- Sleeper -----

def sleeper_user_leagues(username, season):
    user = http_json(f"{SLEEPER_API}/user/{username.strip()}")
    if not user or not user.get("user_id"):
        raise LookupError(f"No Sleeper user named '{username}'.")
    leagues = http_json(f"{SLEEPER_API}/user/{user['user_id']}/leagues/nfl/{season}") or []
    return user, leagues


# Every synced team keeps "entries": one row per rostered player with the slot the manager actually set
# (QB, RB, WR, TE, FLEX, SUPERFLEX, K, DEF, BN, IR, TAXI), so the site can show the real lineup next to
# the recommended one, and show kickers, defenses and injured reserve.

SLOT_ORDER = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DEF", "BN", "IR", "TAXI"]
STARTING = {"QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DEF"}
SLEEPER_SLOT_ALL = {**SLEEPER_SLOTS, "K": "K", "DEF": "DEF"}
ESPN_SLOT_ALL = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "FLEX", 3: "FLEX", 5: "FLEX", 7: "SUPERFLEX", 16: "DEF",
                 17: "K", 20: "BN", 21: "IR"}
ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
ESPN_TEAM = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN",
             11: "IND", 12: "KC", 13: "LV", 14: "LA", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
             21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR",
             30: "JAX", 33: "BAL", 34: "HOU"}
YAHOO_SLOT = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "W/R/T": "FLEX", "W/R": "FLEX", "W/T": "FLEX",
              "R/T": "FLEX", "Q/W/R/T": "SUPERFLEX", "K": "K", "DEF": "DEF", "BN": "BN", "IR": "IR", "IR+": "IR",
              "NA": "BN"}
YAHOO_TEAM = {"ari": "ARI", "atl": "ATL", "bal": "BAL", "buf": "BUF", "car": "CAR", "chi": "CHI", "cin": "CIN",
              "cle": "CLE", "dal": "DAL", "den": "DEN", "det": "DET", "gnb": "GB", "hou": "HOU", "ind": "IND",
              "jac": "JAX", "jax": "JAX", "kan": "KC", "lac": "LAC", "lar": "LA", "lvr": "LV", "mia": "MIA",
              "min": "MIN", "nwe": "NE", "nor": "NO", "nyg": "NYG", "nyj": "NYJ", "phi": "PHI", "pit": "PIT",
              "sea": "SEA", "sfo": "SF", "tam": "TB", "ten": "TEN", "was": "WAS"}
TEAM_ABBRS = set(TEAM_COLORS) - {"LAR"}


def norm_slot_pos(p):
    p = str(p or "").upper().strip()
    return {"PK": "K", "D/ST": "DEF", "DST": "DEF", "DEF": "DEF", "FB": "RB", "HB": "RB"}.get(p, p) or None


def make_entry(S, gid, name=None, pos=None, team=None, slot="BN", status=None):
    p = S.players.get(gid) if gid else None
    pos_n = norm_slot_pos(pos) or (p or {}).get("pos")
    tm = team or (pr.player_team(S, gid) if gid else None)
    return {"gid": gid, "key": gid or (f"DST:{tm}" if pos_n == "DEF" and tm else None),
            "name": name or (p or {}).get("name") or "Unknown player",
            "pos": norm_slot_pos(pos) or (p or {}).get("pos"),
            "team": team or (pr.player_team(S, gid) if gid else None), "slot": slot,
            "status": (str(status).strip().title()[:14] if status and str(status).upper() not in ("ACTIVE", "NORMAL", "")
                       else None)}


def team_from_entries(t):
    """Fill the analysis fields (players / starters) from entries."""
    es = t.get("entries") or []
    fant = [e for e in es if e.get("gid") and e.get("pos") in pr.FANTASY_POS]
    t["players"] = list(dict.fromkeys(e["gid"] for e in fant))
    t["active"] = list(dict.fromkeys(e["gid"] for e in fant if e["slot"] not in ("IR", "TAXI")))
    t["starters"] = [e["gid"] for e in fant if e["slot"] in STARTING]
    t["unmatched"] = sum(1 for e in es if not entry_key(e))
    t["kdef"] = list(dict.fromkeys(entry_key(e) for e in es if e.get("pos") in ("K", "DEF") and entry_key(e)
                                   and e["slot"] not in ("IR", "TAXI")))
    return t


def team_keys(S, t):
    """(active skill players, active K/DEF keys) for a synced team, worked out from its roster entries every time,
    so leagues saved by any version of the site behave the same."""
    es = t.get("entries")
    if not es:
        return list(t.get("active") or t.get("players") or []), list(t.get("kdef") or [])
    skill, kdef = [], []
    for e in es:
        if e.get("slot") in ("IR", "TAXI"):
            continue
        k = entry_key(e)
        if not k:
            continue
        pos = e.get("pos") or (S.players.get(k) or {}).get("pos")
        (kdef if pos in ("K", "DEF") else skill if pos in pr.FANTASY_POS else []).append(k)
    return list(dict.fromkeys(skill)), list(dict.fromkeys(kdef))


def entry_key(e):
    """Projection key for a roster entry: gsis id for players and kickers, DST:<team> for defenses."""
    if e.get("key"):
        return e["key"]
    if e.get("gid"):
        return e["gid"]
    if e.get("pos") == "DEF" and e.get("team"):
        return f"DST:{e['team']}"
    return None


def kdef_pool(S, kind, week):
    """Projections for every kicker (anyone who kicked this season) or every team defense, best first."""
    cache = S.__dict__.setdefault("_kdef_pool", {})
    if (kind, week) not in cache:
        if kind == "K":
            last_kick = {}
            for (kid, wk) in S.k_games:
                last_kick[kid] = max(wk, last_kick.get(kid, 0))
            recent = max(last_kick.values()) if last_kick else 0
            ids = [k for k, w in last_kick.items() if w >= recent - 2]  # still kicking recently
            ps = [pr.project_kdef(S, "K", k, week) for k in ids]
        else:
            ps = [pr.project_kdef(S, "DEF", t, week) for t in sorted(S.team_ctx)]
        cache[(kind, week)] = sorted([p for p in ps if not p["bye"]], key=lambda p: -p["proj"])
    return cache[(kind, week)]


def project_any(S, key, week=None):
    if not key:
        return None
    if str(key).startswith("DST:"):
        return pr.project_kdef(S, "DEF", key[4:], week)
    p = S.players.get(key) or {}
    if p.get("pos") == "K" or (key in S.k_team and key not in S.season_tot):
        return pr.project_kdef(S, "K", key, week)
    return pr.project_player(S, key, week)


def ros_any(S, key):
    if str(key).startswith("DST:"):
        return pr.ros_kdef(S, "DEF", key[4:])
    if (S.players.get(key) or {}).get("pos") == "K":
        return pr.ros_kdef(S, "K", key)
    return pr.ros_value(S, key)


def slots_from_entries(entries):
    c = Counter(e["slot"] for e in entries if e["slot"] in STARTING)
    out = {k: 0 for k in DEFAULT_SLOTS}
    out.update({k: c.get(k, 0) for k in ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"]})
    out["K"], out["DEF"] = c.get("K", 0), c.get("DEF", 0)
    return out if sum(out.values()) >= 5 else None


# ----- League scoring -----

SCORING_FIELDS = [
    ("pass_yd", "Passing yards (points per yard)", 0.04), ("pass_td", "Passing TD", 4.0),
    ("int", "Interception thrown", -1.0), ("pick6", "Pick-six thrown (extra)", 0.0),
    ("pass_cmp", "Completion", 0.0), ("pass_inc", "Incomplete pass", 0.0), ("pass_att", "Pass attempt", 0.0),
    ("pass_fd", "Passing first down", 0.0),
    ("rush_yd", "Rushing yards (per yard)", 0.1), ("rush_td", "Rushing TD", 6.0), ("rush_att", "Rush attempt", 0.0),
    ("rush_fd", "Rushing first down", 0.0),
    ("rec", "Reception (PPR)", 0.5), ("te_rec", "TE premium (extra per TE catch)", 0.0), ("rec_tgt", "Target", 0.0),
    ("rec_yd", "Receiving yards (per yard)", 0.1), ("rec_td", "Receiving TD", 6.0),
    ("rec_fd", "Receiving first down", 0.0),
    ("two_pt", "2-point conversion", 2.0), ("fum", "Fumble (lost or not)", 0.0), ("fum_lost", "Fumble lost", -2.0),
    ("fum_ret_td", "Offensive fumble return TD", 6.0), ("st_td", "Return TD (player)", 6.0),
    ("ret_yd", "Return yards (player, per yard)", 0.0)]
BONUS_FIELDS = [("bonus_pass_300", "300+ passing yards in a game", 0.0), ("bonus_pass_400", "400+ passing yards", 0.0),
                ("bonus_rush_100", "100+ rushing yards", 0.0), ("bonus_rush_200", "200+ rushing yards", 0.0),
                ("bonus_rec_100", "100+ receiving yards", 0.0), ("bonus_rec_200", "200+ receiving yards", 0.0),
                ("bonus_td_40", "40+ yard TD (each, passer and scorer)", 0.0)]
K_FIELDS = [("fg_0_19", "FG made 0-19 yds", 3.0), ("fg_20_29", "FG made 20-29 yds", 3.0),
            ("fg_30_39", "FG made 30-39 yds", 3.0), ("fg_40_49", "FG made 40-49 yds", 4.0),
            ("fg_50p", "FG made 50+ yds", 5.0), ("fgm_0_19", "FG missed 0-19 yds", 0.0),
            ("fgm_20_29", "FG missed 20-29 yds", 0.0), ("fgm_30_39", "FG missed 30-39 yds", 0.0),
            ("fgm_40_49", "FG missed 40-49 yds", 0.0), ("fgm_50p", "FG missed 50+ yds", 0.0),
            ("xp", "Extra point made", 1.0), ("xp_miss", "Extra point missed", 0.0)]
DST_FIELDS = [("dst_sack", "Sack", 1.0), ("dst_int", "Interception", 2.0), ("dst_fr", "Fumble recovery", 2.0),
              ("dst_td", "Defensive TD", 6.0), ("dst_ret_td", "Kickoff / punt return TD", 6.0),
              ("dst_safety", "Safety", 2.0), ("dst_blk", "Blocked kick", 2.0),
              ("dst_xp_ret", "Extra point / 2-pt returned", 2.0), ("dst_ret_yd", "Return yards (per yard)", 0.0),
              ("pa_0", "0 points allowed", 10.0), ("pa_1_6", "1-6 points allowed", 7.0),
              ("pa_7_13", "7-13 points allowed", 4.0), ("pa_14_20", "14-20 points allowed", 1.0),
              ("pa_21_27", "21-27 points allowed", 0.0), ("pa_28_34", "28-34 points allowed", -1.0),
              ("pa_35p", "35+ points allowed", -4.0),
              ("ya_0_99", "0-99 yards allowed", 0.0), ("ya_100_199", "100-199 yards allowed", 0.0),
              ("ya_200_299", "200-299 yards allowed", 0.0), ("ya_300_349", "300-349 yards allowed", 0.0),
              ("ya_350_399", "350-399 yards allowed", 0.0), ("ya_400_449", "400-449 yards allowed", 0.0),
              ("ya_450_499", "450-499 yards allowed", 0.0), ("ya_500_549", "500-549 yards allowed", 0.0),
              ("ya_550p", "550+ yards allowed", 0.0)]
ALL_SCORING_FIELDS = SCORING_FIELDS + BONUS_FIELDS + K_FIELDS + DST_FIELDS
SECTION_FIELDS = {"offense": [f[0] for f in SCORING_FIELDS + BONUS_FIELDS], "kicker": [f[0] for f in K_FIELDS],
                  "defense": [f[0] for f in DST_FIELDS]}


def clean_scoring(sc):
    sc = dict(sc or {})
    # older saves used combined kicker buckets
    if "fg_0_39" in sc:
        for k in ("fg_0_19", "fg_20_29", "fg_30_39"):
            sc.setdefault(k, sc["fg_0_39"])
    if "fg_miss" in sc:
        for k in ("fgm_0_19", "fgm_20_29", "fgm_30_39", "fgm_40_49", "fgm_50p"):
            sc.setdefault(k, sc["fg_miss"])
    out = {}
    for k, _, d in ALL_SCORING_FIELDS:
        try:
            out[k] = round(float(sc.get(k, d)), 4)
        except (TypeError, ValueError):
            out[k] = d
    return out


def scoring_summary(sc):
    if not sc:
        return ""
    r = sc.get("rec", 0)
    ppr = "PPR" if r == 1 else "Half-PPR" if r == 0.5 else "Standard" if r == 0 else f"{r:g} PPR"
    bits = [ppr, f"{sc.get('pass_td', 4):g}-pt pass TD"]
    py = sc.get("pass_yd", 0.04)
    if py and abs(py - 0.04) > 1e-6:
        bits.append(f"1 pt / {1 / py:.0f} pass yds")
    if sc.get("int", -1) != -1:
        bits.append(f"{sc['int']:g} INT")
    if sc.get("te_rec"):
        bits.append(f"TE +{sc['te_rec']:g}")
    if sc.get("fum_lost", -2) != -2:
        bits.append(f"{sc['fum_lost']:g} fumble")
    return " · ".join(bits)


def sleeper_scoring(ss):
    ss = ss or {}

    def v(*keys, d):
        for k in keys:
            if ss.get(k) is not None:
                return float(ss[k])
        return d
    return clean_scoring({
        "pass_yd": v("pass_yd", d=0.04), "pass_td": v("pass_td", d=4), "int": v("pass_int", d=-1),
        "pick6": v("pass_int_td", d=0), "pass_cmp": v("pass_cmp", d=0), "pass_inc": v("pass_inc", d=0),
        "pass_att": v("pass_att", d=0), "pass_fd": v("pass_fd", d=0),
        "rush_yd": v("rush_yd", d=0.1), "rush_td": v("rush_td", d=6), "rush_att": v("rush_att", d=0),
        "rush_fd": v("rush_fd", d=0), "rec": v("rec", d=0), "te_rec": v("bonus_rec_te", d=0),
        "rec_tgt": v("rec_tgt", d=0), "rec_yd": v("rec_yd", d=0.1), "rec_td": v("rec_td", d=6),
        "rec_fd": v("rec_fd", d=0), "two_pt": v("rec_2pt", "rush_2pt", "pass_2pt", d=2), "fum": v("fum", d=0),
        "fum_lost": v("fum_lost", d=-2), "fum_ret_td": v("fum_rec_td", d=6), "st_td": v("st_td", "kr_td", "pr_td", d=6),
        "ret_yd": v("kr_yd", "pr_yd", d=0),
        "bonus_pass_300": v("bonus_pass_yd_300", d=0), "bonus_pass_400": v("bonus_pass_yd_400", d=0),
        "bonus_rush_100": v("bonus_rush_yd_100", d=0), "bonus_rush_200": v("bonus_rush_yd_200", d=0),
        "bonus_rec_100": v("bonus_rec_yd_100", d=0), "bonus_rec_200": v("bonus_rec_yd_200", d=0),
        "bonus_td_40": v("rec_td_40p", "rush_td_40p", "pass_td_40p", d=0),
        "fg_0_19": v("fgm_0_19", "fgm", d=3), "fg_20_29": v("fgm_20_29", "fgm", d=3), "fg_30_39": v("fgm_30_39", "fgm", d=3),
        "fg_40_49": v("fgm_40_49", "fgm", d=4), "fg_50p": v("fgm_50p", "fgm_50_59", d=5),
        "fgm_0_19": v("fgmiss_0_19", "fgmiss", d=0), "fgm_20_29": v("fgmiss_20_29", "fgmiss", d=0),
        "fgm_30_39": v("fgmiss_30_39", "fgmiss", d=0), "fgm_40_49": v("fgmiss_40_49", "fgmiss", d=0),
        "fgm_50p": v("fgmiss_50p", "fgmiss", d=0), "xp": v("xpm", d=1), "xp_miss": v("xpmiss", d=0),
        "dst_sack": v("sack", d=1), "dst_int": v("int", d=2), "dst_fr": v("fum_rec", d=2), "dst_td": v("def_td", d=6),
        "dst_ret_td": v("def_st_td", "st_td", d=6), "dst_safety": v("safe", d=2), "dst_blk": v("blk_kick", d=2),
        "dst_xp_ret": v("def_2pt", d=2), "dst_ret_yd": v("def_kr_yd", "def_pr_yd", d=0),
        "pa_0": v("pts_allow_0", d=10), "pa_1_6": v("pts_allow_1_6", d=7), "pa_7_13": v("pts_allow_7_13", d=4),
        "pa_14_20": v("pts_allow_14_20", d=1), "pa_21_27": v("pts_allow_21_27", d=0),
        "pa_28_34": v("pts_allow_28_34", d=-1), "pa_35p": v("pts_allow_35p", d=-4),
        "ya_0_99": v("yds_allow_0_100", d=0), "ya_100_199": v("yds_allow_100_199", d=0),
        "ya_200_299": v("yds_allow_200_299", d=0), "ya_300_349": v("yds_allow_300_349", d=0),
        "ya_350_399": v("yds_allow_350_399", d=0), "ya_400_449": v("yds_allow_400_449", d=0),
        "ya_450_499": v("yds_allow_450_499", d=0), "ya_500_549": v("yds_allow_500_549", d=0),
        "ya_550p": v("yds_allow_550p", d=0)})


ESPN_STATS = {0: "pass_att", 1: "pass_cmp", 2: "pass_inc", 3: "pass_yd", 4: "pass_td", 20: "int", 23: "rush_att",
              24: "rush_yd", 25: "rush_td", 53: "rec", 58: "rec_tgt", 42: "rec_yd", 43: "rec_td", 68: "fum",
              72: "fum_lost", 19: "two_pt", 26: "two_pt", 44: "two_pt", 101: "st_td", 102: "st_td",
              74: "fg_50p", 77: "fg_40_49", 76: "fgm_50p", 79: "fgm_40_49", 86: "xp", 88: "xp_miss",
              99: "dst_sack", 95: "dst_int", 96: "dst_fr", 94: "dst_td", 98: "dst_safety", 97: "dst_blk",
              89: "pa_0", 90: "pa_1_6", 91: "pa_7_13", 92: "pa_14_20", 124: "pa_21_27", 125: "pa_28_34", 126: "pa_35p"}


def espn_scoring(items):
    sc = {k: d for k, _, d in ALL_SCORING_FIELDS}
    sc.update(rec=0, pass_td=4, int=-2)
    for k in ("ya_0_99", "ya_100_199", "ya_200_299", "ya_300_349", "ya_350_399", "ya_400_449", "ya_450_499",
              "ya_500_549", "ya_550p"):
        sc[k] = 0
    for it in items or []:
        sid, pts = it.get("statId"), float(it.get("points") or 0)
        key = ESPN_STATS.get(sid)
        if key:
            sc[key] = pts
        if sid == 80:  # ESPN groups FGs under 40 yards
            sc["fg_0_19"] = sc["fg_20_29"] = sc["fg_30_39"] = pts
        if sid == 82:
            sc["fgm_0_19"] = sc["fgm_20_29"] = sc["fgm_30_39"] = pts
        if sid == 85:  # total missed FGs
            for k in ("fgm_0_19", "fgm_20_29", "fgm_30_39", "fgm_40_49", "fgm_50p"):
                sc[k] = sc.get(k, 0) + pts
        if sid == 53:
            ov = (it.get("pointsOverrides") or {}).get("6")
            if ov is not None:
                sc["te_rec"] = float(ov) - pts
    return clean_scoring(sc)


def _score_value(val):
    """'20 yards per point' -> 0.05, '1 point per 25 yards' -> 0.04, '-1' -> -1."""
    v = str(val).strip().lower()
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*yards?\s*per\s*point", v)
    if m and float(m.group(1)):
        return 1 / float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*points?\s*per\s*(\d+(?:\.\d+)?)\s*yards?", v)
    if m and float(m.group(2)):
        return float(m.group(1)) / float(m.group(2))
    m = re.search(r"-?\d+(?:\.\d+)?", v)
    return float(m.group(0)) if m else None


def _range_key(prefix, lo, hi, tiers):
    for top, key in tiers:
        if lo <= top:
            return key
    return None


PA_KEYS = [(0, "pa_0"), (6, "pa_1_6"), (13, "pa_7_13"), (20, "pa_14_20"), (27, "pa_21_27"), (34, "pa_28_34"),
           (999, "pa_35p")]
YA_KEYS = [(99, "ya_0_99"), (199, "ya_100_199"), (299, "ya_200_299"), (349, "ya_300_349"), (399, "ya_350_399"),
           (449, "ya_400_449"), (499, "ya_450_499"), (549, "ya_500_549"), (99999, "ya_550p")]


def _label_key(label, section):
    l = re.sub(r"\s+", " ", label.lower()).strip()
    nums = [int(x) for x in re.findall(r"\d+", l)]
    lo = nums[0] if nums else 0
    if section == "kicker" or l.startswith(("field goal", "point after", "pat")):
        if l.startswith("point after") or l.startswith("pat"):
            return "xp_miss" if "miss" in l else "xp"
        if l.startswith("field goal"):
            miss = "miss" in l
            if not nums:
                return "fgm_30_39" if miss else None
            band = "0_19" if lo < 20 else "20_29" if lo < 30 else "30_39" if lo < 40 else "40_49" if lo < 50 else "50p"
            return ("fgm_" if miss else "fg_") + band
    if l.startswith("points allowed"):
        return _range_key("pa", lo, None, PA_KEYS)
    if l.startswith("yards allowed"):
        return _range_key("ya", lo, None, YA_KEYS)
    if section == "defense":
        for pat, key in [("kickoff and punt return touchdown", "dst_ret_td"), ("return touchdown", "dst_ret_td"),
                         ("extra point returned", "dst_xp_ret"), ("2-point return", "dst_xp_ret"),
                         ("block", "dst_blk"), ("fumble recovery", "dst_fr"), ("sack", "dst_sack"),
                         ("interception", "dst_int"), ("safety", "dst_safety"), ("return yards", "dst_ret_yd"),
                         ("touchdown", "dst_td"), ("defensive touchdown", "dst_td")]:
            if l.startswith(pat):
                return key
        return None
    for pat, key in [("passing yards", "pass_yd"), ("passing touchdown", "pass_td"), ("pick six", "pick6"),
                     ("pick-six", "pick6"), ("interception", "int"), ("completions", "pass_cmp"),
                     ("incomplete pass", "pass_inc"), ("passing attempt", "pass_att"), ("pass attempt", "pass_att"),
                     ("passing 1st down", "pass_fd"), ("passing first down", "pass_fd"),
                     ("rushing yards", "rush_yd"), ("rushing touchdown", "rush_td"), ("rushing attempt", "rush_att"),
                     ("rush attempt", "rush_att"), ("rushing 1st down", "rush_fd"), ("rushing first down", "rush_fd"),
                     ("receptions", "rec"), ("targets", "rec_tgt"), ("receiving yards", "rec_yd"),
                     ("receiving touchdown", "rec_td"), ("receiving 1st down", "rec_fd"),
                     ("receiving first down", "rec_fd"), ("return touchdown", "st_td"), ("return yards", "ret_yd"),
                     ("2-point conversion", "two_pt"), ("two-point conversion", "two_pt"),
                     ("fumbles lost", "fum_lost"), ("offensive fumble return", "fum_ret_td"), ("fumble return td", "fum_ret_td"),
                     ("fumbles", "fum")]:
        if l.startswith(pat):
            return key
    if "40+" in l and "touchdown" in l:
        return "bonus_td_40"
    if ("pass" in l and "300" in l) or ("pass" in l and "400" in l):
        return "bonus_pass_400" if "400" in l else "bonus_pass_300"
    if "rush" in l and ("100" in l or "200" in l):
        return "bonus_rush_200" if "200" in l else "bonus_rush_100"
    if ("rec" in l) and ("100" in l or "200" in l):
        return "bonus_rec_200" if "200" in l else "bonus_rec_100"
    return None


DEFENSE_ONLY = {"dst_sack", "dst_fr", "dst_safety", "dst_blk", "dst_ret_td", "dst_xp_ret"}


def parse_scoring_rows(rows):
    """Read a league scoring table (rows of [label, value, ...]) the way Yahoo shows it: sections for offense,
    kickers and defense, listing only the categories the league uses. Categories missing from a section that was
    read are worth 0 in that league, which is what makes the transfer exact."""
    found, seen_sections, section, int_seen = {}, Counter(), "offense", 0
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        label = str(row[0]).strip()
        val = str(row[1]).strip() if len(row) > 1 else ""
        low = label.lower()
        if low in ("offense", "offensive players") or low.startswith("offense"):
            section = "offense"
            continue
        if low.startswith("kicker"):
            section = "kicker"
            continue
        if low.startswith("defense") or low.startswith("special teams") or low.startswith("team defense"):
            section = "defense"
            continue
        if val.lower() in ("league value", "value", "points"):
            continue
        n = _score_value(val)
        if n is None:
            continue
        key = _label_key(label, section)
        if section != "defense" and key is None:
            k2 = _label_key(label, "defense")
            if k2 in DEFENSE_ONLY or (k2 and k2.startswith(("pa_", "ya_"))):
                section, key = "defense", k2          # tables without headers: defense rows start here
        if key and key in SECTION_FIELDS["kicker"]:
            section = "kicker" if section == "offense" else section
        if key == "int" and section != "defense":
            int_seen += 1
            if int_seen > 1:
                key = "dst_int"
        if not key or key in found:
            continue
        found[key] = n
        sec_of = next((s_ for s_, ks in SECTION_FIELDS.items() if key in ks), section)
        seen_sections[sec_of] += 1
    offense_found = sum(1 for k in found if k in SECTION_FIELDS["offense"])
    if offense_found < 4:
        return None, {}
    sc = {k: d for k, _, d in ALL_SCORING_FIELDS}
    for sec_name, keys in SECTION_FIELDS.items():
        if seen_sections[sec_name] >= 3:
            for k in keys:
                sc[k] = 0.0  # not listed in the league's table = not scored
    sc.update(found)
    return clean_scoring(sc), {"found": len(found), "sections": dict(seen_sections)}


def yahoo_scoring(rows):
    return parse_scoring_rows(rows)[0]


def parse_scoring_text(text):
    """Scoring settings copied from a league settings page and pasted (tabs or spaces between columns)."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"\t+|\s{2,}", line) if p.strip()]
        if len(parts) >= 2:
            rows.append(parts)
            continue
        m = re.match(r"^(.*?\D)\s+(-?\d+(?:\.\d+)?(?:\s+yards?\s+per\s+point|\s+points?\s+per\s+\d+\s+yards?)?)"
                     r"(?:\s+-?\d+(?:\.\d+)?(?:\s+yards?\s+per\s+point)?)?$", line, re.I)
        if m:
            rows.append([m.group(1).strip(), m.group(2).strip()])
        else:
            rows.append([line, ""])
    return parse_scoring_rows(rows)


# ----- Sleeper -----

def sleeper_import(S, league_id, user_id=None):
    lg = http_json(f"{SLEEPER_API}/league/{league_id}")
    if not lg:
        raise LookupError("Sleeper league not found.")
    rosters = http_json(f"{SLEEPER_API}/league/{league_id}/rosters") or []
    users = {u["user_id"]: u for u in (http_json(f"{SLEEPER_API}/league/{league_id}/users") or [])}
    try:
        week = (http_json(f"{SLEEPER_API}/state/nfl") or {}).get("week")
        matchups = http_json(f"{SLEEPER_API}/league/{league_id}/matchups/{week}") if week else []
    except Exception:
        week, matchups = None, []
    positions = lg.get("roster_positions") or []
    starter_slots = [SLEEPER_SLOT_ALL.get(rp, "FLEX" if "FLEX" in rp else rp) for rp in positions
                     if rp not in ("BN", "IR", "TAXI")]
    slots = {k: 0 for k in DEFAULT_SLOTS}
    for sl in starter_slots:
        slots[sl] = slots.get(sl, 0) + 1
    rec = (lg.get("scoring_settings") or {}).get("rec", 0)
    scoring = sleeper_scoring(lg.get("scoring_settings"))

    def sentry(sid, slot):
        sid = str(sid)
        if not sid.isdigit():
            return make_entry(S, None, f"{sid} Defense", "DEF", sid.upper(), slot)
        return make_entry(S, map_player(S, "sleeper", sid), None, None, None, slot)
    teams, my = [], None
    for r in rosters:
        u = users.get(r.get("owner_id"), {})
        name = (u.get("metadata") or {}).get("team_name") or u.get("display_name") or f"Team {r['roster_id']}"
        entries, placed = [], set()
        for i, sid in enumerate(r.get("starters") or []):
            if str(sid) in ("0", "None") or i >= len(starter_slots):
                continue
            entries.append(sentry(sid, starter_slots[i]))
            placed.add(str(sid))
        for sid in r.get("reserve") or []:
            if str(sid) not in placed:
                entries.append(sentry(sid, "IR"))
                placed.add(str(sid))
        for sid in r.get("taxi") or []:
            if str(sid) not in placed:
                entries.append(sentry(sid, "TAXI"))
                placed.add(str(sid))
        for sid in r.get("players") or []:
            if str(sid) not in placed:
                entries.append(sentry(sid, "BN"))
                placed.add(str(sid))
        stt = r.get("settings") or {}
        teams.append(team_from_entries({
            "id": str(r["roster_id"]), "name": name, "owner": u.get("display_name"), "entries": entries,
            "record": [stt.get("wins", 0), stt.get("losses", 0), stt.get("ties", 0)]}))
        if user_id and r.get("owner_id") == user_id:
            my = str(r["roster_id"])
    opp = {}
    by_mid = defaultdict(list)
    for m in matchups or []:
        if m.get("matchup_id") is not None:
            by_mid[m["matchup_id"]].append(str(m["roster_id"]))
    for ids in by_mid.values():
        if len(ids) == 2:
            opp[ids[0]], opp[ids[1]] = ids[1], ids[0]
    return _finish_league({"platform": "sleeper", "league_id": str(league_id), "name": lg.get("name"),
                           "season": int(lg.get("season") or S.season), "rec": rec, "scoring": fmt_for_rec(rec),
                           "slots": slots, "teams": teams, "my_team": my, "opponents": opp, "week": week,
                           "has_lineups": True, "scoring_custom": scoring, "scoring_source": "Sleeper",
                           "resync": {"type": "sleeper", "league_id": str(league_id), "user_id": user_id}})


# ----- ESPN -----

def espn_fetch(league_id, season, s2=None, swid=None):
    cookies = {"espn_s2": s2, "SWID": swid} if (s2 and swid) else None
    params = [("view", "mTeam"), ("view", "mRoster"), ("view", "mSettings"), ("view", "mMatchup")]
    return http_json(ESPN_API.format(season=season, lid=league_id), params=params, cookies=cookies)


def espn_from_json(S, data, league_id, season, my_team_id=None, swid=None):
    st_ = data.get("settings") or {}
    counts = (st_.get("rosterSettings") or {}).get("lineupSlotCounts") or {}
    slots = {k: 0 for k in DEFAULT_SLOTS}
    for k, n in counts.items():
        sl = ESPN_SLOT_ALL.get(int(k)) if str(k).isdigit() else None
        if sl in STARTING:
            slots[sl] = slots.get(sl, 0) + int(n or 0)
    items = (st_.get("scoringSettings") or {}).get("scoringItems") or []
    rec = next((i.get("points", 0) for i in items if i.get("statId") == 53), 0)
    members = {m.get("id"): m.get("displayName") for m in data.get("members") or []}
    teams, my = [], (str(my_team_id) if my_team_id else None)
    for t in data.get("teams") or []:
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or f"Team {t.get('id')}"
        owners = t.get("owners") or []
        entries = []
        for e in ((t.get("roster") or {}).get("entries") or []):
            pl = ((e.get("playerPoolEntry") or {}).get("player")) or {}
            nm, pos = pl.get("fullName"), ESPN_POS.get(pl.get("defaultPositionId"))
            team = ESPN_TEAM.get(pl.get("proTeamId"))
            slot = ESPN_SLOT_ALL.get(e.get("lineupSlotId"), "BN")
            if pos == "DEF" or (nm and "D/ST" in nm):
                entries.append(make_entry(S, None, nm or f"{team} D/ST", "DEF", team, slot))
                continue
            gid = map_player(S, "espn", e.get("playerId"), nm)
            entries.append(make_entry(S, gid, nm, pos, team, slot, pl.get("injuryStatus")))
        rec_ = ((t.get("record") or {}).get("overall")) or {}
        teams.append(team_from_entries({
            "id": str(t.get("id")), "name": name, "owner": members.get(owners[0]) if owners else None,
            "entries": entries, "record": [rec_.get("wins", 0), rec_.get("losses", 0), rec_.get("ties", 0)]}))
        if not my and swid and swid in owners:
            my = str(t.get("id"))
    per = (data.get("status") or {}).get("currentMatchupPeriod")
    opp = {}
    for g_ in data.get("schedule") or []:
        if g_.get("matchupPeriodId") == per:
            h, a = (g_.get("home") or {}).get("teamId"), (g_.get("away") or {}).get("teamId")
            if h is not None and a is not None:
                opp[str(h)], opp[str(a)] = str(a), str(h)
    return _finish_league({"platform": "espn", "league_id": str(league_id), "name": st_.get("name"),
                           "season": int(season), "rec": rec, "scoring": fmt_for_rec(rec), "slots": slots,
                           "teams": teams, "my_team": my, "opponents": opp, "week": per, "has_lineups": True,
                           "scoring_custom": espn_scoring(items), "scoring_source": "ESPN",
                           "resync": {"type": "espn", "league_id": str(league_id), "season": int(season)}})


# ----- Yahoo (from the bookmark) -----

def yahoo_from_payload(S, p):
    teams, any_slots = [], False
    for t in p.get("teams") or []:
        entries, seen = [], set()
        for item in t.get("players") or []:
            item = list(item) if isinstance(item, (list, tuple)) else [item]
            yid, nm, slot_raw, tslug, inj = (item + [None] * 5)[:5]
            key = yid or nm
            if not key or key in seen:
                continue
            seen.add(key)
            slot = YAHOO_SLOT.get(str(slot_raw or "").upper().strip())
            any_slots = any_slots or slot is not None
            slot = slot or "BN"
            if tslug and not yid:
                team = YAHOO_TEAM.get(str(tslug).lower(), str(tslug).upper()[:3])
                entries.append(make_entry(S, None, f"{nm or team}", "DEF", team, slot))
                continue
            gid = map_player(S, "yahoo", yid, nm)
            entries.append(make_entry(S, gid, nm, None, None, slot, inj if inj and len(str(inj)) <= 4 else None))
        teams.append(team_from_entries({"id": str(t.get("id")), "name": t.get("name") or f"Team {t.get('id')}",
                                        "owner": None, "entries": entries, "record": None}))
    my = str(p["my"]) if p.get("my") else None
    mine = next((t for t in teams if t["id"] == my), None)
    slots = (slots_from_entries(mine["entries"]) if (mine and any_slots) else None) or dict(DEFAULT_SLOTS)
    nm = (p.get("name") or "").replace("Yahoo Fantasy Football", "").strip(" -|") or None
    ysc = yahoo_scoring(p.get("sc"))
    return _finish_league({"platform": "yahoo", "scoring_custom": ysc,
                           "scoring_source": "Yahoo settings page" if ysc else None, "league_id": str(p.get("league")), "name": nm,
                           "season": S.season, "rec": 0.5, "scoring": "half", "slots": slots,
                           "teams": teams, "my_team": my, "opponents": {}, "week": None,
                           "has_lineups": any_slots, "slots_auto": any_slots, "resync": None,
                           "bookmark_version": p.get("v", 1)})


def decode_sync(code):
    import json as _json
    code = (code or "").strip()
    if not code or len(code) > 400_000:
        raise ValueError("That sync code is empty or too large.")
    import zlib
    packed = code.startswith("z")
    body = code[1:] if packed else code
    body += "=" * (-len(body) % 4)
    try:
        raw = base64.urlsafe_b64decode(body.encode())
        if packed:
            raw = zlib.decompress(raw, -15)
        return _json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("That sync code couldn't be read. Run the bookmark again.")


def league_from_sync(S, payload):
    src = payload.get("src")
    if src == "sleeper":
        return sleeper_import(S, payload["league"])
    if src == "espn":
        return espn_from_json(S, payload["data"], payload["league"], payload.get("season") or S.season,
                              payload.get("my"))
    if src == "yahoo":
        return yahoo_from_payload(S, payload)
    raise ValueError("Unknown sync source.")


BOOKMARK_VERSION = 6
LINEUP_BOOKMARK_VERSION = 3  # older bookmarks didn't send lineup slots / K / DEF / IR
BOOKMARKLET_JS = r"""(async()=>{const SITE='__SITE__';
const b64=u=>{let s='';for(let i=0;i<u.length;i+=8192)s+=String.fromCharCode.apply(null,u.subarray(i,i+8192));return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')};
const enc=async o=>{const raw=new TextEncoder().encode(JSON.stringify(o));try{const st=new Blob([raw]).stream().pipeThrough(new CompressionStream('deflate-raw'));return 'z'+b64(new Uint8Array(await new Response(st).arrayBuffer()))}catch(e){return b64(raw)}};
const go=async o=>{o.v=6;const b=await enc(o);const u=SITE+'/?sync='+b;if(u.length<=7000){location.href=u;return}
const d=document.createElement('div');d.style.cssText='position:fixed;z-index:2147483647;top:20px;right:20px;width:380px;background:#121a2b;color:#e6edf3;border:2px solid #f5b301;border-radius:14px;padding:18px;font:14px sans-serif;box-shadow:0 10px 40px rgba(0,0,0,.5)';
d.innerHTML='<b style="font-size:16px">Your league is ready</b><p style="color:#8b98ad;margin:8px 0 12px">It is too big to send in a link, so it goes through your clipboard.</p>';
const bt=document.createElement('button');bt.textContent='Copy & open Fantasy Reports';bt.style.cssText='width:100%;padding:12px;border:0;border-radius:10px;background:#f5b301;color:#111;font-weight:800;font-size:15px;cursor:pointer';
bt.onclick=async()=>{try{await navigator.clipboard.writeText(b)}catch(e){const t=document.createElement('textarea');t.value=b;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove()}window.open(SITE+'/?sync=paste','_blank');d.remove()};
const x=document.createElement('div');x.textContent='Cancel';x.style.cssText='text-align:center;margin-top:10px;color:#8b98ad;cursor:pointer';x.onclick=()=>d.remove();
d.appendChild(bt);d.appendChild(x);document.body.appendChild(d)};
const trim=a=>{while(a.length&&(a[a.length-1]===''||a[a.length-1]==null))a.pop();return a};
const h=location.hostname,p=location.pathname;
try{
if(h.includes('sleeper')){const m=p.match(/leagues\/(\d+)/);if(!m)return alert('Open your Sleeper league first, then tap this bookmark.');return go({src:'sleeper',league:m[1]})}
if(h.includes('espn')){const q=new URLSearchParams(location.search);const lid=q.get('leagueId');if(!lid)return alert('Open your ESPN league or team page first.');
const yr=q.get('seasonId')||new Date().getFullYear();
const r=await fetch('https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/'+yr+'/segments/0/leagues/'+lid+'?view=mTeam&view=mRoster&view=mSettings&view=mMatchup',{credentials:'include'});
if(!r.ok)return alert('ESPN returned '+r.status+'. Make sure you are logged in to ESPN.');
const d=await r.json();const per=(d.status||{}).currentMatchupPeriod;const ss=d.settings||{};
return go({src:'espn',league:lid,season:+yr,my:q.get('teamId'),data:{settings:{name:ss.name,rosterSettings:{lineupSlotCounts:(ss.rosterSettings||{}).lineupSlotCounts},scoringSettings:{scoringItems:((ss.scoringSettings||{}).scoringItems||[]).filter(i=>i.statId<200).map(i=>({statId:i.statId,points:i.points,pointsOverrides:i.pointsOverrides}))}},
members:(d.members||[]).map(m=>({id:m.id,displayName:m.displayName})),status:{currentMatchupPeriod:per},
schedule:(d.schedule||[]).filter(s=>s.matchupPeriodId==per).map(s=>({matchupPeriodId:s.matchupPeriodId,home:{teamId:(s.home||{}).teamId},away:{teamId:(s.away||{}).teamId}})),
teams:(d.teams||[]).map(t=>({id:t.id,name:t.name||((t.location||'')+' '+(t.nickname||'')).trim(),owners:t.owners,record:{overall:((t.record||{}).overall)||{}},roster:{entries:((t.roster||{}).entries||[]).map(e=>{const pl=((e.playerPoolEntry||{}).player)||{};return {playerId:e.playerId,lineupSlotId:e.lineupSlotId,playerPoolEntry:{player:{fullName:pl.fullName,defaultPositionId:pl.defaultPositionId,proTeamId:pl.proTeamId,injuryStatus:pl.injuryStatus}}}})}}))}})}
if(h.includes('yahoo')){const m=p.match(/\/f1\/(\d+)/);if(!m)return alert('Open your Yahoo fantasy football league first, then tap this bookmark.');const lid=m[1];
const P=new DOMParser();const get=async u=>{const r=await fetch(u,{credentials:'include'});return P.parseFromString(await r.text(),'text/html')};
const home=await get('/f1/'+lid);const names={};let my=null;const re=new RegExp('/f1/'+lid+'/(\\d+)/?$');
home.querySelectorAll('a[href]').forEach(a=>{const mm=(a.getAttribute('href')||'').split('?')[0].match(re);if(!mm)return;const t=a.textContent.trim();
if(/^my team$/i.test(t))my=mm[1];else if(t&&t.length<60&&(!names[mm[1]]||t.length>names[mm[1]].length))names[mm[1]]=t});
const cur=p.match(new RegExp('/f1/'+lid+'/(\\d+)'));if(!my&&cur)my=cur[1];
let ids=Object.keys(names);if(!ids.length)ids=Array.from({length:16},(_,i)=>String(i+1));
const teams=[];for(const id of ids){const doc=await get('/f1/'+lid+'/'+id);const seen=new Set(),pl=[];
doc.querySelectorAll('tr').forEach(tr=>{const a=tr.querySelector('a[href*="/nfl/players/"],a[href*="/nfl/teams/"]');if(!a)return;
const href=a.getAttribute('href')||'',nm=a.textContent.trim();if(nm.length<2)return;
const pm=href.match(/players\/(\d+)/),tm=href.match(/teams\/([a-z]+)/);const key=pm?pm[1]:'t'+(tm?tm[1]:nm);if(seen.has(key))return;seen.add(key);
const pe=tr.querySelector('[data-pos]');let slot=pe?pe.getAttribute('data-pos'):'';if(!slot){const c=tr.querySelector('td');slot=c?c.textContent.trim():''}
const ie=tr.querySelector('.F-injury,[class*="injury"],[class*="Injury"]');let injt=ie?ie.textContent.trim():'';
if(!injt){const sm=tr.querySelectorAll('span,abbr,em,strong');for(let k=0;k<sm.length;k++){const tx=(sm[k].textContent||'').trim();if(/^(Q|D|O|IR|IR-R|IR-N|PUP|PUP-R|PUP-P|SUSP|NA|COV|NFI-R)$/.test(tx)){injt=tx;break}}}
const inj={textContent:injt};pl.push(trim([pm?pm[1]:'',nm,(slot||'').slice(0,8),pm?'':(tm?tm[1]:''),inj.textContent.slice(0,6)]))});
if(!pl.length){doc.querySelectorAll('a[href*="/nfl/players/"]').forEach(a=>{const mm=(a.getAttribute('href')||'').match(/players\/(\d+)/);const t=a.textContent.trim();
if(mm&&t.length>3&&!seen.has(mm[1])){seen.add(mm[1]);pl.push([mm[1],t])}})}
if(pl.length)teams.push({id:id,name:names[id]||('Team '+id),players:pl})}
if(!teams.length)return alert('Could not read the rosters. Make sure you are logged in to Yahoo.');
let sc=[];try{const sd=await get('/f1/'+lid+'/settings');let on=false;sd.querySelectorAll('tr').forEach(tr=>{const c=tr.querySelectorAll('td,th');if(c.length<2)return;const a=c[0].textContent.trim(),b=c[1].textContent.trim();
if(/^(offense|kickers|defense)/i.test(a)&&/value/i.test(b))on=true;if(on&&a&&a.length<60&&b.length<40)sc.push([a,b])});sc=sc.slice(0,120)}catch(e){}
return go({src:'yahoo',league:lid,name:((home.querySelector('title')||{}).textContent||'').split('|')[0].trim(),my:my,teams:teams,sc:sc})}
alert('Open your league on Yahoo, ESPN or Sleeper first, then tap this bookmark.')
}catch(e){alert('Sync failed: '+e.message)}})();"""


def site_url():
    cfg = _secrets("site")
    if cfg and cfg.get("url"):
        return cfg["url"].rstrip("/")
    try:
        host = st.context.headers.get("Host")
    except Exception:
        host = None
    if host:
        local = host.startswith(("localhost", "127.", "0.0.0.0"))
        return f"{'http' if local else 'https'}://{host}"
    return None


def bookmarklet(site):
    js = " ".join(line.strip() for line in BOOKMARKLET_JS.replace("__SITE__", site).splitlines())
    return "javascript:" + js


def bookmark_page(bm):
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Sync to Fantasy Reports</title></head>"
            "<body style='font-family:sans-serif;background:#0b1220;color:#e6edf3;padding:40px;text-align:center'>"
            "<h2>Drag the gold button to your bookmarks bar</h2>"
            "<p style='color:#8b98ad'>Bookmarks bar hidden? Press Ctrl+Shift+B (Cmd+Shift+B on Mac).</p>"
            f"<p style='margin:30px'><a href=\"{html.escape(bm, quote=True)}\" style='display:inline-block;"
            "padding:18px 28px;border-radius:14px;background:#f5b301;color:#111;font-weight:800;font-size:20px;"
            "text-decoration:none'>⚡ Sync to Fantasy Reports</a></p>"
            "<p style='color:#8b98ad'>Then open your league on Yahoo, ESPN or Sleeper and click the bookmark.</p>"
            "</body></html>")


def bookmark_widget(site, key="bm"):
    import streamlit.components.v1 as components
    bm = bookmarklet(site)
    components.html(
        f"""<div style="font-family:sans-serif;display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:4px 2px">
        <a href="{esc(bm)}" onclick="event.preventDefault();alert('Drag this button to your bookmarks bar instead of clicking it.');"
           style="display:inline-block;padding:13px 20px;border-radius:12px;background:#f5b301;color:#111;font-weight:800;
           text-decoration:none;font-size:15px;cursor:grab;box-shadow:0 4px 14px rgba(245,179,1,.35)">⚡ Sync to Fantasy Reports</a>
        <span style="color:#8b98ad;font-size:13px">⬅ Drag this onto your bookmarks bar (Ctrl+Shift+B shows the bar)</span></div>""",
        height=70)
    H(f'<div class="fr-sub" style="margin:.3rem 0 .4rem"><b style="color:{TEXT}">Don\'t see a gold button, or it won\'t '
      f'drag?</b> Use either backup:</div>')
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Download the bookmark page", bookmark_page(bm), file_name="sync-to-fantasy-reports.html",
                           mime="text/html", key=f"{key}_dl", use_container_width=True)
        st.caption("Open the downloaded file in Brave and drag the big gold button from there.")
    with c2:
        with st.expander("Or create it by hand"):
            st.caption("1. Press Ctrl+D to bookmark any page. 2. Right-click the new bookmark → Edit. "
                       "3. Name it 'Sync to Fantasy Reports' and replace the URL with everything below "
                       "(use the copy icon in the corner).")
            st.code(bm, language=None)


# ------------------------------------------------------------------------------------
# League analysis
# ------------------------------------------------------------------------------------

# ------------------------------------------------------------------------------------
# League display components: team cards, set-vs-recommended lineups, K/DEF matchup hints
# ------------------------------------------------------------------------------------

SLOT_COLORS = {"QB": "#f2557a", "RB": "#22c3a6", "WR": "#4ea3ff", "TE": "#ff9f43", "FLEX": "#a78bfa",
               "SUPERFLEX": "#e879f9", "K": "#94a3b8", "DEF": "#c08457", "BN": "#3b4a63", "IR": "#ef4444",
               "TAXI": "#3b4a63"}
SLOT_TEXT = {"FLEX": "FLEX", "SUPERFLEX": "SFLX", "BN": "BENCH", "IR": "IR", "TAXI": "TAXI"}
TEAM_ACCENTS = ["#f5b301", "#4ea3ff", "#22c3a6", "#f2557a", "#a78bfa", "#ff9f43", "#38bdf8", "#84cc16", "#e879f9",
                "#fb7185", "#2dd4bf", "#facc15", "#60a5fa", "#f97316", "#c084fc", "#34d399"]
INJ_COLORS = {"Q": AMBER, "QUESTIONABLE": AMBER, "D": "#fb923c", "DOUBTFUL": "#fb923c", "O": RED, "OUT": RED,
              "IR": RED, "INJURY_RESERVE": RED, "PUP": RED, "SUSP": RED, "SUSPENSION": RED}


POS_COLORS = {"QB": "#f2557a", "RB": "#22c3a6", "WR": "#4ea3ff", "TE": "#ff9f43", "K": "#a3a3c2", "DEF": "#c08457"}


def slot_pill(slot, pos=None):
    """Starters: the slot they're in (QB, RB, WR, TE, FLEX, K, DEF), filled in their position's colour.
    Bench/taxi: their position, outlined. IR: red."""
    if slot == "IR":
        return f'<span class="fr-slot" style="background:{RED}26;color:#fca5a5;border-color:{RED}88">IR</span>'
    c = POS_COLORS.get(pos) or SLOT_COLORS.get(slot, "#64748b")
    if slot in STARTING:
        txt = SLOT_TEXT.get(slot, slot)
        return f'<span class="fr-slot" style="background:{c}2e;color:{c};border-color:{c}99">{txt}</span>'
    txt = pos or SLOT_TEXT.get(slot, slot)
    return (f'<span class="fr-slot bn" style="color:{c};border-color:{c}66" title="On the bench">{esc(txt)}'
            f'<i>{"TAXI" if slot == "TAXI" else "BN"}</i></span>')


def inj_badge(status):
    if not status:
        return ""
    s = str(status).upper().replace(" ", "_")
    short = {"QUESTIONABLE": "Q", "DOUBTFUL": "D", "OUT": "O", "INJURY_RESERVE": "IR", "INJURED_RESERVE": "IR",
             "SUSPENSION": "SUSP"}.get(s, s[:4])
    c = INJ_COLORS.get(short, INJ_COLORS.get(s, AMBER))
    return f'<span class="fr-inj" style="color:{c};border-color:{c}">{esc(short)}</span>'


def game_result(S, pid, week):
    """Actual fantasy points if his game this week is already final, else None."""
    if str(pid).startswith("DST:"):
        return pr.kdef_actual(S, "DEF", pid[4:], week)
    if (S.players.get(pid) or {}).get("pos") == "K":
        return pr.kdef_actual(S, "K", pid, week)
    team = pr.player_team(S, pid)
    gm = pr.team_game(S, team, week) if (team and week) else None
    if not gm or gm["home_score"] is None:
        return None
    for r in S.weekly.get(pid, []):
        if r["week"] == week:
            return r["pts"]
    return 0.0


def team_week_label(S, team, week):
    gm = pr.team_game(S, team, week) if (team and week) else None
    if not gm:
        return "BYE", None
    home = gm["home"] == team
    opp = gm["away"] if home else gm["home"]
    imp = None
    if gm["total"] is not None and gm["spread"] is not None:
        h = (gm["total"] + gm["spread"]) / 2
        imp = {"own": h if home else gm["total"] - h, "opp": gm["total"] - h if home else h}
    return f"{'vs' if home else '@'} {opp}", imp


def kdef_hint(S, e, week):
    """K and DEF have no projection model; show the Vegas context that drives them instead."""
    lab, imp = team_week_label(S, e.get("team"), week)
    if lab == "BYE":
        return lab, "On bye", RED
    if not imp:
        return lab, "", MUTED
    if e["pos"] == "DEF":
        o = imp["opp"]
        col = GREEN if o <= 19 else RED if o >= 25 else MUTED
        return lab, f"Opp. implied {o:.1f}", col
    o = imp["own"]
    col = GREEN if o >= 25 else RED if o <= 19 else MUTED
    return lab, f"Team implied {o:.1f}", col


def pts_cell(S, e, p, week):
    """PROJ and FINAL numbers; the column labels sit once in each section header."""
    dash = '<b class="na">·</b>'
    key = entry_key(e)
    proj = f'<b>{p["proj"]:.1f}</b>' if p else dash
    f = game_result(S, key, week) if key else None
    fin = f'<b class="fin">{f:.1f}</b>' if f is not None else dash
    return f'<div class="fr-pts2"><div>{proj}</div><div>{fin}</div></div>'


def grp_header(title, total=None):
    t = f' <em>{total:.1f} proj</em>' if total is not None else ""
    return (f'<div class="fr-grp"><b>{title}{t}</b><span class="cols"><i>PROJ</i><i>FINAL</i></span></div>')


def player_line(S, e, p, week, badge=""):
    slot = e["slot"]
    if e.get("pos") in ("K", "DEF") or not e.get("gid"):
        lab, hint, hcol = kdef_hint(S, e, week) if e.get("pos") in ("K", "DEF") else \
            ("", "No eligible player on the roster" if e.get("name") == "Empty slot" else "Not matched", MUTED)
        if p and p.get("bye"):
            hint, hcol = "BYE", RED
        name = esc(e["name"])
        meta = f'{esc(e.get("pos") or "")} · {esc(e.get("team") or "")}{" · " + esc(lab) if lab else ""}'
        extra = f' · <span style="color:{hcol}">{esc(hint)}</span>' if hint else ""
    else:
        name = plink(e["gid"], e["name"])
        lab = p["label"] if p else ""
        meta = f'{esc(e.get("pos") or "")} · {esc(e.get("team") or "")}{" · " + esc(lab) if lab else ""}'
        extra = ""
        if p and p.get("fpa_rank") and not p["bye"]:
            ml, mc = matchup_info(p["fpa_rank"], p["fpa_n"])
            extra = f' · <span style="color:{mc}">{ml}</span>'
        if p and p["bye"]:
            extra = f' · <span style="color:{RED}">BYE</span>'
    st_ = e.get("status") or ((p or {}).get("inj_status") or "").split(" (")[0]
    dim = " ir" if slot == "IR" else " bye" if (p and p.get("bye")) else ""
    pc = POS_COLORS.get(e.get("pos"), "#64748b")
    tint = (f' style="background:linear-gradient(90deg,{pc}{"1f" if slot in STARTING else "0e"} 0%,transparent 45%)"'
            if slot != "IR" else "")
    return (f'<div class="fr-pl{dim}"{tint}>{slot_pill(slot, e.get("pos"))}{logo(e.get("team"), 26)}'
            f'<div class="fr-pl-main"><div class="fr-pl-name">{name}{inj_badge(st_)}{badge}</div>'
            f'<div class="fr-pl-meta">{meta}{extra}</div></div>{pts_cell(S, e, p, week)}</div>')


def ordered_entries(entries, group):
    if group == "start":
        es = [e for e in entries if e["slot"] in STARTING]
    elif group == "bench":
        es = [e for e in entries if e["slot"] in ("BN", "TAXI")]
    else:
        es = [e for e in entries if e["slot"] == "IR"]
    pos_rank = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
    return sorted(es, key=lambda e: (SLOT_ORDER.index(e["slot"]) if e["slot"] in SLOT_ORDER else 99,
                                     pos_rank.get(e.get("pos"), 9)))


def legacy_entries(t):
    """Teams synced before lineups were captured: show everyone as roster with no slot."""
    return [{"gid": g, "name": None, "pos": None, "team": None, "slot": "BN", "status": None} for g in t["players"]]


def resolve_entries(S, t):
    es = t.get("entries")
    if es:
        return es
    out = []
    for g in t.get("players") or []:
        out.append(make_entry(S, g))
    return out


def lineup_moves(S, entries, rec_lineup, projs):
    act = [entry_key(e) for e in entries if e["slot"] in STARTING and entry_key(e) in projs]
    rec = [l["p"]["pid"] for l in rec_lineup if l["p"]]
    start = sorted([projs[g] for g in rec if g not in act and g in projs], key=lambda p: -p["proj"])
    sit = sorted([projs[g] for g in act if g not in rec], key=lambda p: p["proj"])
    moves, used = [], set()
    for s_ in start:
        partner = next((x for x in sit if x["pid"] not in used and x["pos"] == s_["pos"]), None) or \
            next((x for x in sit if x["pid"] not in used and x["pos"] not in ("K", "DEF")
                  and s_["pos"] not in ("K", "DEF")), None)
        if partner:
            used.add(partner["pid"])
        gain = s_["proj"] - (partner["proj"] if partner else 0)
        risky = bool(s_.get("inj_detail")) and s_.get("injf", 1) < 1
        moves.append({"start": s_, "sit": partner, "gain": gain, "check": risky and gain < 2.5})
    return moves


def same_team_notes(lineup):
    """Starters sharing a backfield / receiver room: explain that projections already account for it."""
    groups = defaultdict(list)
    for l in lineup:
        p = l["p"]
        if p and p["pos"] in ("RB", "WR", "TE", "QB") and p.get("team"):
            groups[(p["team"], p["pos"])].append(p)
    out = []
    for (team, pos), ps in groups.items():
        if len(ps) >= 2 and pos in ("RB", "QB"):
            names = " and ".join(p["name"] for p in ps)
            out.append(f"{names} share the {team} {'backfield' if pos == 'RB' else 'QB room'}. Their projections "
                       f"already account for splitting the work, and both start only because both still project "
                       f"higher than your other options.")
    return out


def set_total_of(es, projs):
    return sum(projs[entry_key(e)]["proj"] for e in es if e["slot"] in STARTING and entry_key(e) in projs)


def team_card_html(S, t, T, week, rank, accent, is_me, n_teams):
    es = resolve_entries(S, t)
    projs = T["projs"]
    rec_ids = {l["p"]["pid"] for l in T["lineup"] if l["p"]}
    has_slots = any(e["slot"] in STARTING for e in es)
    rec = t.get("record")
    rec_txt = f"{rec[0]}-{rec[1]}{'-' + str(rec[2]) if rec[2] else ''}" if rec else ""
    set_total = set_total_of(es, projs)
    grades = "".join(f'<span class="fr-grade" style="color:{T["grades"][p]["grade"][1]};border-color:'
                     f'{T["grades"][p]["grade"][1]}55">{p} {T["grades"][p]["grade"][0]}</span>'
                     for p in pr.FANTASY_POS if p in T["grades"])
    you = ' <span class="fr-you">YOU</span>' if is_me else ""

    def badge(e):
        k = entry_key(e)
        if not has_slots or k not in projs:
            return ""
        if e["slot"] in STARTING and k not in rec_ids:
            return '<span class="fr-tag sit">SIT?</span>'
        if e["slot"] == "BN" and k in rec_ids:
            return '<span class="fr-tag start">START?</span>'
        return ""
    body = []
    groups = [("Starters", "start"), ("Bench", "bench"), ("Injured reserve", "ir")] if has_slots else \
        [("Roster", "bench"), ("Injured reserve", "ir")]
    for title, g_ in groups:
        rows = ordered_entries(es, g_)
        if not rows:
            continue
        body.append(grp_header(title, set_total if g_ == "start" else None))
        body += [player_line(S, e, projs.get(entry_key(e)), week, badge(e)) for e in rows]
    head = (f'<div class="fr-tc-head" style="background:linear-gradient(120deg,{accent}33 0%,{accent}0d 60%,transparent);'
            f'border-bottom:1px solid {accent}44">'
            f'<div class="fr-rank-badge" style="background:{accent};">{rank}</div>'
            f'<div style="flex:1;min-width:0"><div class="fr-tc-name">{esc(t["name"])}{you}</div>'
            f'<div class="fr-tc-sub">{esc(t.get("owner") or "")}{" · " if t.get("owner") and rec_txt else ""}'
            f'{rec_txt}</div><div style="margin-top:.35rem">{grades}</div></div>'
            f'<div class="fr-tc-tot"><div class="v">{(set_total if has_slots else T["total"]):.1f}</div>'
            f'<div class="l">{"set lineup" if has_slots else "best lineup"}<br>wk {week} proj</div></div></div>')
    return (f'<div class="fr-tc" style="border-top:4px solid {accent};{"box-shadow:0 0 0 1px " + accent + "88;" if is_me else ""}">'
            f'{head}<div class="fr-tc-body">{"".join(body)}</div></div>')


def lineup_compare(S, t, T, week, slots):
    es = resolve_entries(S, t)
    projs = T["projs"]
    has_slots = any(e["slot"] in STARTING for e in es)
    rec_total = T["total"]
    set_total = set_total_of(es, projs)
    moves = lineup_moves(S, es, T["lineup"], projs) if has_slots else []
    gain = rec_total - set_total if has_slots else 0
    if not has_slots:
        H(notes_html([("info", "This sync didn't include the lineup you set, so only the recommended lineup is shown. "
                               "Re-sync to compare.")]))
    cards = []
    if has_slots:
        cards.append(kpi("Your lineup", f"{set_total:.1f}", f"projected · week {week}", BLUE))
    cards.append(kpi("Recommended", f"{rec_total:.1f}", "projected · best possible", GOLD))
    if has_slots:
        cards.append(kpi("Gain from changes", f"{gain:+.1f}",
                         f"{len(moves)} move{'s' if len(moves) != 1 else ''} below" if moves else "Already optimal",
                         GREEN if gain >= 0.5 else BORDER, GREEN if gain >= 0.5 else TEXT))
    H(f'<div class="fr-grid g3">{"".join(cards)}</div>')
    if moves:
        sec("Suggested changes")
        items = []
        for mv in moves:
            s_, o = mv["start"], mv["sit"]
            nm = (lambda p: esc(p["name"]) if p.get("kdef") else plink(p["pid"], p["name"]))
            tag = ('<span class="fr-tag sit">CHECK STATUS</span>' if mv.get("check") else "")
            why = (f'<div class="fr-dim" style="flex-basis:100%;margin-top:-.15rem">{esc(s_["name"])} is '
                   f'{esc(s_.get("inj_detail") or "on the injury report")}; the edge is small, so only make this swap '
                   f'if he\'s confirmed active.</div>' if mv.get("check") else "")
            items.append(f'<div class="fr-move"><div class="fr-move-side in"><span class="fr-tag start">START</span>'
                         f'{logo(s_["team"], 22)} {nm(s_)} <span class="fr-dim">{s_["pos"]} · {s_["proj"]:.1f}</span></div>'
                         f'<div class="fr-move-arrow">⇄</div><div class="fr-move-side out"><span class="fr-tag sit">BENCH</span>'
                         + (f'{logo(o["team"], 22)} {nm(o)} <span class="fr-dim">{o["pos"]} · {o["proj"]:.1f}</span>'
                            if o else '<span class="fr-dim">open slot</span>')
                         + f'</div><div class="fr-move-gain">{tag} {mv["gain"]:+.1f}</div>{why}</div>')
        H("".join(items))
    stn = same_team_notes(T["lineup"])
    if stn:
        H(notes_html([("info", x) for x in stn]))
    set_rows = ordered_entries(es, "start") if has_slots else []
    by_key = {entry_key(e): e for e in es if entry_key(e)}
    rec_rows = []
    for l in T["lineup"]:
        p = l["p"]
        if p:
            e = by_key.get(p["pid"]) or make_entry(S, p["pid"] if not p.get("kdef") or p["pos"] == "K" else None,
                                                   p["name"], p["pos"], p["team"])
            rec_rows.append({**e, "slot": l["slot"]})
        else:
            rec_rows.append({"gid": None, "name": "Empty slot", "pos": None, "team": None, "slot": l["slot"],
                             "status": None})
    rec_ids = {entry_key(r) for r in rec_rows if entry_key(r)}
    set_ids = {entry_key(r) for r in set_rows if entry_key(r)}

    def lines(rows, badge_fn=None):
        return "".join(player_line(S, e, projs.get(entry_key(e)), week, badge_fn(e) if badge_fn else "")
                       for e in rows)
    ir_rows = ordered_entries(es, "ir")
    left = ""
    if has_slots:
        bench_rows = ordered_entries(es, "bench")
        left = (grp_header("Starters", set_total) +
                lines(set_rows, lambda e: '<span class="fr-tag sit">SIT?</span>' if entry_key(e) in projs and
                      entry_key(e) not in rec_ids else "") +
                (grp_header("Bench") + lines(bench_rows, lambda e: '<span class="fr-tag start">START?</span>'
                                             if entry_key(e) in rec_ids else "") if bench_rows else "") +
                (grp_header("Injured reserve") + lines(ir_rows) if ir_rows else ""))
    rec_bench = ordered_entries([{**e, "slot": "TAXI" if e["slot"] == "TAXI" else "BN"} for e in es
                                 if e["slot"] != "IR" and entry_key(e) not in rec_ids], "bench")
    right = (grp_header("Starters", rec_total) +
             lines(rec_rows, lambda e: '<span class="fr-tag start">NEW</span>' if has_slots and entry_key(e) and
                   entry_key(e) not in set_ids else "") +
             (grp_header("Bench") + lines(rec_bench) if rec_bench else "") +
             (grp_header("Injured reserve") + lines(ir_rows) if ir_rows else ""))
    plat = esc(PLATFORM_LABEL.get(t.get("_platform"), "your site"))
    cols = (f'<div class="fr-tc" style="border-top:4px solid {BLUE}"><div class="fr-tc-head" style="background:'
            f'linear-gradient(120deg,{BLUE}26,transparent 70%)"><div style="flex:1"><div class="fr-tc-name">'
            f'Your lineup</div><div class="fr-tc-sub">as set on {plat}</div></div><div class="fr-tc-tot">'
            f'<div class="v">{set_total:.1f}</div><div class="l">wk {week} proj</div></div></div>'
            f'<div class="fr-tc-body">{left}</div></div>' if has_slots else "")
    cols += (f'<div class="fr-tc" style="border-top:4px solid {GOLD}"><div class="fr-tc-head" style="background:'
             f'linear-gradient(120deg,{GOLD}26,transparent 70%)"><div style="flex:1"><div class="fr-tc-name">'
             f'Recommended</div><div class="fr-tc-sub">highest projection at every slot</div></div>'
             f'<div class="fr-tc-tot"><div class="v">{rec_total:.1f}</div><div class="l">wk {week} proj</div></div>'
             f'</div><div class="fr-tc-body">{right}</div></div>')
    H(f'<div style="height:.5rem"></div><div class="fr-grid g2">{cols}</div>')
    st.caption("PROJ = projected points this week under this league's scoring (kickers and defenses included); "
               "FINAL = his game is over. A defense's line shows what its opponent is expected to score; a kicker's "
               "shows his own team's expected total.")


def effective_scoring(league):
    sc = league.get("scoring_manual") or league.get("scoring_custom")
    return clean_scoring(sc) if sc else None


def league_settings_editor(store, owner, row, lg):
    rid = row["id"]
    cur = effective_scoring(lg) or clean_scoring(preset_scoring(lg.get("scoring", "half")))
    src = "You edited this." if lg.get("scoring_manual") else \
        (f"Synced from {lg['scoring_source']}." if lg.get("scoring_source") else "Not synced yet; please check it.")
    st.markdown(f"**Scoring** · <span style='color:{MUTED};font-size:.85rem'>{esc(src)}</span>", unsafe_allow_html=True)
    if lg.get("platform") == "yahoo" and lg.get("bookmark_version", 1) < BOOKMARK_VERSION:
        st.info("Your newest bookmark reads your full Yahoo scoring table (every kicker, defense and bonus "
                "category). Add it from Update from Yahoo, then click it on Yahoo, or paste the table below.")
    with st.expander("📋 Paste your league's scoring table (exact copy)", expanded=not lg.get("scoring_source")):
        st.caption("On your league site, open the scoring settings (Yahoo: League → Settings), select the whole "
                   "scoring table from 'Offense' down to the last defense row, copy, and paste it here. Every "
                   "category is read, and anything your league doesn't list counts as 0.")
        txt = st.text_area("Scoring table", height=140, key=f"scpaste_{rid}", label_visibility="collapsed",
                           placeholder="Offense   League Value\nPassing Yards   20 yards per point\n...")
        if st.button("Read it", key=f"scread_{rid}"):
            sc, info = parse_scoring_text(txt)
            if not sc:
                st.error("Couldn't read that. Make sure the copy includes the Offense rows (Passing Yards, "
                         "Rushing Yards and so on) and their values.")
            else:
                lg["scoring_manual"] = sc
                store.save(owner, rid, lg)
                list_teams.clear()
                st.session_state._flash = (f"Read {info['found']} scoring categories from your table and saved them "
                                           f"for this league.")
                st.rerun()
    presets = {"Current": cur, "Standard": clean_scoring(preset_scoring("standard")),
               "Half-PPR": clean_scoring(preset_scoring("half")), "PPR": clean_scoring(preset_scoring("ppr")),
               "Half-PPR, 6-pt pass TD": clean_scoring({**preset_scoring("half"), "pass_td": 6})}
    pick = st.selectbox("Or edit by hand, starting from", list(presets), key=f"scp_{rid}")
    base = presets[pick]
    vals = {}
    for tab, fields in zip(st.tabs(["Offense", "Bonuses", "Kicker", "Defense"]),
                           [SCORING_FIELDS, BONUS_FIELDS, K_FIELDS, DST_FIELDS]):
        with tab:
            cols = st.columns(2)
            for i, (k, lab, _) in enumerate(fields):
                step = 0.01 if k.endswith("_yd") else 0.5
                vals[k] = cols[i % 2].number_input(lab, value=float(base.get(k, 0.0)), step=step,
                                                   format="%.2f" if step < 0.5 else "%.1f", key=f"sc_{k}_{rid}_{pick}")
            if fields is SCORING_FIELDS:
                st.caption("Yardage values are points per yard: 25 yards per point = 0.04, 20 = 0.05, 10 = 0.1.")
    st.caption("Not modeled: individual defensive players (IDP).")
    st.markdown("**Starting lineup**")
    sl = {**DEFAULT_SLOTS, **(lg.get("slots") or {})}
    new_slots = dict(sl)
    cols = st.columns(4)
    for i, key in enumerate(["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX", "K", "DEF"]):
        new_slots[key] = cols[i % 4].number_input(SLOT_LABEL.get(key, key), 0, 4, int(sl.get(key, 0)),
                                                  key=f"sl_{key}_{rid}")
    b1, b2 = st.columns(2)
    if b1.button("Save settings", type="primary", key=f"scsave_{rid}", use_container_width=True):
        new_sc = clean_scoring(vals)
        if new_sc != clean_scoring(lg.get("scoring_custom") or {}) or lg.get("scoring_manual"):
            lg["scoring_manual"] = new_sc
        lg["slots"] = new_slots
        store.save(owner, rid, lg)
        list_teams.clear()
        st.session_state._flash = "League settings saved."
        st.rerun()
    if lg.get("scoring_manual") and lg.get("scoring_custom"):
        if b2.button("Use synced scoring", key=f"scclr_{rid}", use_container_width=True):
            lg.pop("scoring_manual", None)
            store.save(owner, rid, lg)
            list_teams.clear()
            st.rerun()


PLATFORM_STATUS = {"O": "Out", "OUT": "Out", "NA": "Out", "COV": "Out", "SUSP": "Suspended", "SUSPENSION": "Suspended",
                   "D": "Doubtful", "DOUBTFUL": "Doubtful", "Q": "Questionable", "QUESTIONABLE": "Questionable",
                   "IR": "Injured Reserve", "IR-R": "Injured Reserve", "IR-N": "Injured Reserve",
                   "INJURY_RESERVE": "Injured Reserve", "PUP": "Injured Reserve", "PUP-R": "Injured Reserve",
                   "PUP-P": "Injured Reserve", "NFI-R": "Injured Reserve"}


def league_injury_overrides(S, league):
    """Injury statuses the league platform showed at sync time (e.g. Yahoo's game-day 'O'), which beat the
    official report when they're newer."""
    out = {}
    for t in league.get("teams", []):
        for e in t.get("entries") or []:
            gid = e.get("gid")
            if not gid or e.get("pos") not in pr.FANTASY_POS:
                continue
            raw = str(e.get("status") or "").upper().replace(" ", "_")
            st_ = PLATFORM_STATUS.get(raw) or ("Injured Reserve" if e.get("slot") == "IR" and not raw else None)
            if not st_:
                continue
            base = S.injuries.get(gid) or {}
            out[gid] = {"week": 999, "status": st_, "injury": base.get("injury"),
                        "practice": base.get("practice") if st_ == "Questionable" else None,
                        "updated": "from your league"}
    return out


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=24, show_spinner=False)
def _with_overrides(_S, key, _ov):
    return pr.with_injury_overrides(_S, _ov)


def league_season(S, league, season):
    LS = _league_season_base(S, league, season)
    ov = league_injury_overrides(LS, league)
    if not ov:
        return LS
    return _with_overrides(LS, skey(LS, tuple(sorted((k, v["status"]) for k, v in ov.items()))), ov)


def _league_season_base(S, league, season):
    sc = effective_scoring(league)
    if sc:
        return get_season(season, sc)
    fmt_ = league.get("scoring") or S.fmt_name
    return S if fmt_ == S.fmt_name else get_season(season, fmt_)


def team_strength(S, roster, slots, n_teams, week):
    projs = {}
    for key in roster:
        p = project_any(S, key, week)
        if p:
            projs[key] = p
    roster = list(projs)
    lineup, bench = optimal_lineup(projs, slots)
    ros = {pid: ros_any(S, pid) for pid in roster}
    ros_projs = {pid: {**projs[pid], "proj": ros[pid]} for pid in roster if projs[pid]}
    ros_lineup, _ = optimal_lineup(ros_projs, slots)
    grades, surplus = {}, defaultdict(list)
    for pos in pr.FANTASY_POS:
        n = slots.get(pos, 0)
        if not n:
            continue
        league_top = [p for p in pr.position_projections(S, pos, week) if not p["bye"]][: n_teams * n]
        avg = mean([p["proj"] for p in league_top])
        mine = [l["p"]["proj"] for l in lineup if l["slot"] == pos and l["p"]]
        ratio = div(mean(mine) if mine else 0.0, avg) if avg else None
        grades[pos] = {"ratio": ratio, "grade": grade_for(ratio)}
        base_cut = league_top[-1]["proj"] if league_top else None
        for b in bench:
            if b["pos"] == pos and base_cut and pr.player_base(S, b["pid"])["base"] >= base_cut:
                surplus[pos].append(b)
    return {"lineup": lineup, "bench": bench, "projs": projs, "ros": ros, "grades": grades, "surplus": surplus,
            "total": sum(l["p"]["proj"] for l in lineup if l["p"]),
            "ros_total": sum(l["p"]["proj"] for l in ros_lineup if l["p"]),
            "needs": sorted([p for p, g_ in grades.items() if g_["ratio"] is not None and g_["ratio"] < 1.0],
                            key=lambda p: grades[p]["ratio"])}


@st.cache_resource(ttl=pr.CACHE_HOURS * 3600, max_entries=40, show_spinner=False)
def league_report(_S, key, _league):
    S, league = _S, _league
    week = pr.next_week(S)
    slots = {**DEFAULT_SLOTS, **(league.get("slots") or {})}
    n = league.get("teams_in_league") or len(league["teams"])
    owner_of = {pid: t for t in league["teams"] for pid in t["players"]}
    out = {"week": week, "teams": {}, "owner_of": owner_of}
    for t in league["teams"]:
        skill, kdef = team_keys(S, t)
        out["teams"][t["id"]] = team_strength(S, skill + kdef, slots, n, week)
    my = league.get("my_team")
    if my and my in out["teams"]:
        me = next(t for t in league["teams"] if t["id"] == my)
        skill, kdef = team_keys(S, me)
        out["mine"] = analyze_team(S, {"roster": skill + kdef, "slots": slots, "teams_in_league": n},
                                   owner_of=owner_of, my_team_id=my)
        out["partners"] = trade_partners(S, league, out, my)
        out["waivers"] = waiver_targets(S, league, out, my)
        opp = (league.get("opponents") or {}).get(my)
        out["opponent"] = opp
    return out


def ros_rate(S, pid):
    """Rest-of-season points per game (model rate x remaining schedule); 0 for players out long-term."""
    cache = S.__dict__.setdefault("_rosr", {})
    if pid not in cache:
        b = pr.player_base(S, pid)
        if not b:
            cache[pid] = None
        else:
            inj = pr.current_status(S, pid)
            long_out = bool(inj and any(w in str(inj.get("status", "")).lower() for w in ("injured reserve", "pup")))
            cache[pid] = 0.0 if long_out else b["base"] * pr.schedule_factor(S, pid)
    return cache[pid]


def lineup_pg(players, slots):
    """Best starting lineup's points per game from (pid, pos, rate) tuples (skill positions only)."""
    avail = sorted([p for p in players if p[2] is not None], key=lambda p: -p[2])
    used, tot = set(), 0.0
    order = [s_ for s_ in ["QB", "RB", "WR", "TE"] for _ in range(int(slots.get(s_, 0) or 0))] + \
            [s_ for s_ in ["FLEX", "SUPERFLEX"] for _ in range(int(slots.get(s_, 0) or 0))]
    for slot in order:
        for p in avail:
            if p[0] not in used and p[1] in SLOT_ELIG[slot]:
                used.add(p[0])
                tot += p[2]
                break
    return tot


def remaining_weeks(S):
    nw = pr.next_week(S)
    return max(0, pr.FANTASY_PLAYOFF_WEEKS[-1] - nw + 1) if nw else 0


def roster_rates(S, keys):
    out = []
    for k in keys:
        r = ros_rate(S, k)
        p = S.season_tot.get(k) or S.players.get(k) or {}
        if r is not None and p.get("pos") in pr.FANTASY_POS:
            out.append((k, p.get("pos"), r))
    return out


def evaluate_trade(S, slots, mine, theirs, give, get, waiver=None):
    """Change in each team's best lineup (points per game, rest of season) from swapping give <-> get.
    Rosters stay the same size: a team taking on extra players drops its least valuable one(s); a team that
    frees a spot picks up the best free agent that helps its lineup (waiver = {pos: rate})."""
    my_before, th_before = lineup_pg(mine, slots), lineup_pg(theirs, slots)
    gset, rset = set(give), set(get)
    my_after = [p for p in mine if p[0] not in gset] + [p for p in theirs if p[0] in rset]
    th_after = [p for p in theirs if p[0] not in rset] + [p for p in mine if p[0] in gset]

    def fit(after, size):
        after = sorted(after, key=lambda p: -p[2])
        while len(after) > size:                      # drop the least valuable player(s)
            after.pop()
        while len(after) < size and waiver:          # fill open spots from waivers
            best = max(((pos, r) for pos, r in waiver.items()),
                       key=lambda pr_: lineup_pg(after + [("FA_" + pr_[0], pr_[0], pr_[1])], slots))
            after.append(("FA_" + best[0], best[0], best[1]))
            if len(after) < size and lineup_pg(after, slots) == lineup_pg(after[:-1], slots):
                break
        return after
    my_after, th_after = fit(my_after, len(mine)), fit(th_after, len(theirs))
    return lineup_pg(my_after, slots) - my_before, lineup_pg(th_after, slots) - th_before


def waiver_rates(S, owned):
    """Best free agent's rest-of-season rate at each position (what an open roster spot is worth)."""
    best = {}
    for pid, t in S.season_tot.items():
        if pid in owned or t["pos"] not in pr.FANTASY_POS or t["games"] < 2:
            continue
        r = ros_rate(S, pid)
        if r is not None and r > best.get(t["pos"], 0):
            best[t["pos"]] = r
    return best


def trade_partners(S, league, R, my):
    slots = {**DEFAULT_SLOTS, **(league.get("slots") or {})}
    names = {t["id"]: t["name"] for t in league["teams"]}
    rost = {t["id"]: roster_rates(S, team_keys(S, t)[0]) for t in league["teams"]}
    mine = rost.get(my, [])
    weeks = remaining_weeks(S)
    owned = {p[0] for r in rost.values() for p in r}
    wv = waiver_rates(S, owned)
    ideas = []
    for tid, theirs in rost.items():
        if tid == my or not theirs:
            continue
        # 1-for-1
        for a in mine:
            for b in theirs:
                mg, tg = evaluate_trade(S, slots, mine, theirs, [a[0]], [b[0]], wv)
                if mg > 0.4 and tg > -0.5:
                    ideas.append({"team": names[tid], "tid": tid, "give": [a], "get": [b], "mg": mg, "tg": tg})
        # 2-for-1 consolidation: two of mine for one of their better players
        mine_sorted = sorted(mine, key=lambda p: -p[2])[:10]
        for i in range(len(mine_sorted)):
            for j in range(i + 1, len(mine_sorted)):
                pair = [mine_sorted[i], mine_sorted[j]]
                for b in theirs:
                    if b[2] <= max(pair[0][2], pair[1][2]):
                        continue
                    mg, tg = evaluate_trade(S, slots, mine, theirs, [pair[0][0], pair[1][0]], [b[0]], wv)
                    if mg > 0.6 and tg > -0.5:
                        ideas.append({"team": names[tid], "tid": tid, "give": pair, "get": [b], "mg": mg, "tg": tg})
    def market(k):  # what most managers go by: points per game so far
        t = S.season_tot.get(k)
        return t["ppg"] if t else (ros_rate(S, k) or 0)
    kept = []
    for i in ideas:
        their_in = sum(market(p[0]) for p in i["give"])    # what they receive, as they see it
        their_out = sum(market(p[0]) for p in i["get"])
        ratio = their_in / their_out if their_out > 0 else 2.0
        if len(i["give"]) > 1:
            ratio = (max(market(p[0]) for p in i["give"]) + 0.35 * min(market(p[0]) for p in i["give"])) / \
                (their_out or 1)  # two lesser players are worth less than their sum to the other manager
        i["their_ratio"], i["their_in"], i["their_out"] = ratio, their_in, their_out
        accept = ratio >= 0.95 and (i["tg"] >= -0.3 or ratio >= 1.1)
        if not accept:
            continue
        i["score"] = (i["mg"] + 0.4 * max(min(i["tg"], 2.0), -0.5) + 1.5 * min(ratio - 1, 0.3)
                      - (0.3 if len(i["give"]) > 1 else 0.0))
        i["ros_gain"] = i["mg"] * weeks
        i["fit"] = ("win-win" if i["tg"] > 0.2 else "sells itself" if ratio >= 1.08 else "fair")
        kept.append(i)
    ideas = sorted(kept, key=lambda x: -x["score"])
    out, used = [], set()
    for i in ideas:
        k = (tuple(p[0] for p in i["give"]), i["get"][0][0])
        if k in used or any(p[0] in {q[0] for o in out for q in o["get"]} for p in i["get"]):
            continue
        used.add(k)
        out.append(i)
        if len(out) >= 8:
            break
    return out


def waiver_targets(S, league, R, my):
    owned = set(R["owner_of"])
    for t in league["teams"]:
        owned.update(team_keys(S, t)[1])
    mine = R["teams"][my]
    week = R["week"]
    out = {}
    for pos in pr.FANTASY_POS:
        if not (league.get("slots") or DEFAULT_SLOTS).get(pos) and pos not in ("RB", "WR", "TE"):
            continue
        worst = [l["p"]["proj"] for l in mine["lineup"] if l["p"] and l["p"]["pos"] == pos]
        floor_ = min(worst) if worst else 0
        fas = []
        for pid, t in S.season_tot.items():
            if t["pos"] != pos or pid in owned:
                continue
            p = pr.project_player(S, pid, week)
            if not p or p["proj"] <= 0:
                continue
            b = pr.player_base(S, pid)
            fas.append({"p": p, "ros": pr.ros_value(S, pid), "trend": (b["xfp_last3"] or 0) - (b["xfp_season"] or 0)
                        if b["xfp_last3"] is not None and b["xfp_season"] is not None else None,
                        "upgrade": p["proj"] - floor_})
        fas.sort(key=lambda x: -x["ros"])
        out[pos] = fas[:8]
    slots = {**DEFAULT_SLOTS, **(league.get("slots") or {})}
    mine_kdef = {l["slot"]: l["p"]["proj"] for l in mine["lineup"] if l["p"] and l["slot"] in ("K", "DEF")}
    for kind in ("K", "DEF"):
        if not slots.get(kind):
            continue
        fas = []
        for p in kdef_pool(S, kind, week):
            if p["pid"] in owned:
                continue
            ident = p["pid"][4:] if kind == "DEF" else p["pid"]
            fas.append({"p": p, "ros": pr.ros_kdef(S, kind, ident), "trend": None,
                        "upgrade": p["proj"] - mine_kdef.get(kind, 0)})
        fas.sort(key=lambda x: -x["p"]["proj"])  # K and DEF are streamed week to week
        out[kind] = fas[:6]
    return out


def win_prob(my_lineup, opp_lineup):
    a = sum(l["p"]["proj"] for l in my_lineup if l["p"])
    b = sum(l["p"]["proj"] for l in opp_lineup if l["p"])
    var = sum((l["p"].get("sd") or 0) ** 2 for l in my_lineup + opp_lineup if l["p"])
    sd = math.sqrt(var) if var > 0 else 1.0
    return a, b, pr._norm_cdf((a - b) / sd)


# ------------------------------------------------------------------------------------
# League pages
# ------------------------------------------------------------------------------------

def save_league(store, owner, league, existing_teams):
    for t in existing_teams:
        d = t["data"]
        if d.get("kind") == "league" and d.get("platform") == league["platform"] and \
                str(d.get("league_id")) == str(league["league_id"]):
            if not league.get("my_team") and d.get("my_team"):
                league["my_team"] = d["my_team"]
            if d.get("scoring_manual"):
                league["scoring_manual"] = d["scoring_manual"]
            if not league.get("scoring_custom") and d.get("scoring_custom"):
                league["scoring_custom"], league["scoring_source"] = d["scoring_custom"], d.get("scoring_source")
            if league["platform"] == "yahoo" and not league.get("slots_auto"):
                league["slots"] = d.get("slots", league["slots"])
            return store.save(owner, t["id"], league)
    return store.save(owner, None, league)


def sync_page(S, store, owner, teams, season):
    H('<div class="fr-title">Sync a league</div><div class="fr-sub">Bring in your whole league: every team\'s roster, '
      'your matchup, scoring and lineup settings. Re-sync anytime to pick up trades and waiver moves.</div>')
    H('<div style="height:.6rem"></div>')
    t_sl, t_bm, t_es, t_code = st.tabs(["🟣 Sleeper", "⚡ Yahoo (and any site)", "🔴 ESPN", "🔑 Paste a sync code"])
    done = None
    with t_sl:
        st.caption("Sleeper leagues are public, so all it takes is your Sleeper username.")
        with st.form("sl_user"):
            un = text_in("Sleeper username", "off")
            go_ = st.form_submit_button("Find my leagues", type="primary")
        if go_ and un.strip():
            try:
                user, lgs = sleeper_user_leagues(un, season)
                st.session_state._sl_found = (user, lgs)
            except Exception as e:
                st.error(str(e))
        found = st.session_state.get("_sl_found")
        if found:
            user, lgs = found
            if not lgs:
                st.info(f"No {season} NFL leagues found for {user.get('display_name')}.")
            for lg in lgs:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{esc(lg.get('name') or 'League')}** · {lg.get('total_rosters', '?')} teams")
                if c2.button("Import", key=f"sl_{lg['league_id']}", use_container_width=True):
                    with st.spinner("Importing league..."):
                        try:
                            done = sleeper_import(S, lg["league_id"], user.get("user_id"))
                        except Exception as e:
                            st.error(f"Couldn't import: {e}")
    with t_bm:
        H(f'<div class="fr-sub">One-time setup on a computer. Works for <b>Yahoo</b>, ESPN (including private '
          f'leagues) and Sleeper. It reads your league through your own logged-in browser, so no passwords are '
          f'shared with this site.</div>')
        site = site_url()
        if not site:
            site = text_in("This site's address", "url", placeholder="https://your-app.streamlit.app").rstrip("/")
        if site:
            H('<div style="height:.5rem"></div>')
            bookmark_widget(site)
            H(notes_html([
                ("info", "1. Drag the gold button to your bookmarks bar (press Ctrl+Shift+B in Brave if the bar is "
                         "hidden)."),
                ("info", "2. Open your league on Yahoo Fantasy (any league or team page) while logged in."),
                ("info", "3. Click the bookmark. It reads every team's roster (about 10 seconds) and opens this site "
                         "with your league ready to import."),
                ("info", "4. To update after trades or waiver moves, click the bookmark again on Yahoo."),
            ]))
    with t_es:
        st.caption("Public ESPN leagues import with just the league ID (the leagueId=... number in your ESPN league "
                   "link). For a private league, use the ⚡ bookmark tab, which needs no extra setup.")
        with st.form("espn"):
            c1, c2 = st.columns([2, 1])
            lid = c1.text_input("ESPN league ID")
            yr = c2.number_input("Season", 2018, 2100, int(season))
            with st.expander("Private league? (advanced: espn_s2 and SWID cookies)"):
                s2 = text_in("espn_s2", "off", type="password")
                swid = text_in("SWID", "off", placeholder="{XXXXXXXX-XXXX-...}")
            go_ = st.form_submit_button("Import", type="primary")
        if go_ and lid.strip().isdigit():
            with st.spinner("Importing league..."):
                try:
                    data = espn_fetch(lid.strip(), int(yr), s2 or None, swid or None)
                    done = espn_from_json(S, data, lid.strip(), int(yr), swid=swid or None)
                except PermissionError:
                    st.error("That league is private. Use the ⚡ bookmark tab (easiest), or enter espn_s2 and SWID.")
                except Exception as e:
                    st.error(f"Couldn't import: {e}")
    with t_code:
        st.caption("If the bookmark said it copied a sync code (very large leagues), paste it here.")
        with st.form("code"):
            code = st.text_area("Sync code", height=100)
            go_ = st.form_submit_button("Import", type="primary")
        if go_:
            try:
                done = league_from_sync(S, decode_sync(code))
            except Exception as e:
                st.error(str(e))
    if done:
        finish_import(store, owner, teams, done)
    if st.button("← Back to my teams"):
        st.session_state.team_mode = "view"
        st.rerun()


def finish_import(store, owner, teams, league):
    if not league["teams"] or not any(t["players"] for t in league["teams"]):
        st.error("No players could be read from that league. Try again, or tell Claude what you see.")
        return
    try:
        tid = save_league(store, owner, league, teams)
    except Exception as e:
        st.error(f"Couldn't save the league: {e}")
        return
    st.session_state.team_sel = tid
    st.session_state.team_mode = "view"
    st.session_state.pop("_sl_found", None)
    st.session_state._flash = f"Synced {league['name']}: {len(league['teams'])} teams."
    list_teams.clear()
    st.rerun()


def handle_pending_sync(S, store, owner, teams):
    code = st.session_state.get("_pending_sync")
    if not code:
        return False
    try:
        payload = decode_sync(code)
        src = PLATFORM_LABEL.get(payload.get("src"), "your")
    except ValueError as e:
        st.error(str(e))
        st.session_state.pop("_pending_sync", None)
        return False
    H(f'<div class="fr-card" style="border-left:5px solid {GOLD}"><div class="fr-cardh" style="color:{GOLD}">'
      f'Ready to import</div><div style="font-weight:800;color:{TEXT};font-size:1.1rem">Your {esc(src)} league'
      f'{" with " + str(len(payload.get("teams") or [])) + " teams" if payload.get("teams") else ""}</div></div>')
    c1, c2, _ = st.columns([1, 1, 3])
    if c1.button("Import league", type="primary", use_container_width=True):
        st.session_state.pop("_pending_sync", None)
        with st.spinner("Matching players..."):
            try:
                league = league_from_sync(S, payload)
            except Exception as e:
                st.error(f"Couldn't import: {e}")
                return True
        finish_import(store, owner, teams, league)
    if c2.button("Cancel", use_container_width=True):
        st.session_state.pop("_pending_sync", None)
        st.rerun()
    return True


def resync(S, store, owner, row):
    lg = row["data"]
    rs = lg.get("resync") or {}
    if rs.get("type") == "sleeper":
        new = sleeper_import(S, rs["league_id"], rs.get("user_id"))
    elif rs.get("type") == "espn":
        new = espn_from_json(S, espn_fetch(rs["league_id"], rs.get("season") or S.season), rs["league_id"],
                             rs.get("season") or S.season)
    else:
        raise ValueError("Use the ⚡ bookmark on the league's website to re-sync this one.")
    new["my_team"] = new.get("my_team") or lg.get("my_team")
    if lg.get("scoring_manual"):
        new["scoring_manual"] = lg["scoring_manual"]
    store.save(owner, row["id"], new)


def render_league(S, store, owner, row, season):
    lg = row["data"]
    LS = league_season(S, lg, season)
    tnames = {t["id"]: t["name"] for t in lg["teams"]}
    synced = _parse_ts(lg.get("synced_at"))
    eff_sc = effective_scoring(lg)
    sc_src = "set by you" if lg.get("scoring_manual") else (f"from {lg['scoring_source']}" if lg.get("scoring_source")
                                                             else "default, edit in League settings")
    plat_col = {"sleeper": "#a78bfa", "espn": "#ef4444", "yahoo": "#8b5cf6"}.get(lg["platform"], GOLD)
    sc_line = scoring_summary(eff_sc) if eff_sc else pr.FORMAT_LABEL[lg.get("scoring", "half")]
    synced_txt = synced.strftime("%b %d, %I:%M %p") if synced else ""
    H(f'<div class="fr-lbar" style="--pc:{plat_col}">'
      f'<div class="fr-lbar-name">{esc(lg["name"])}</div>'
      f'<span class="fr-lchip plat">{esc(PLATFORM_LABEL.get(lg["platform"], ""))}</span>'
      f'<span class="fr-lchip">{lg["teams_in_league"]} teams</span>'
      f'<span class="fr-lchip sc" title="Scoring {esc(sc_src)}">{esc(sc_line)}</span>'
      + (f'<span class="fr-lbar-sync">Synced {esc(synced_txt)}</span>' if synced_txt else "") + '</div>')
    c1, c2, c3 = st.columns([2.2, 1, 1])
    ids = [t["id"] for t in lg["teams"]]
    cur = lg.get("my_team") if lg.get("my_team") in ids else None
    pick = c1.selectbox("Your team", ids, index=ids.index(cur) if cur else None,
                        format_func=lambda i: f"👤 {tnames[i]}  (your team)" if i == cur else tnames[i],
                        placeholder="Which team is yours?", key=f"my_{row['id']}", label_visibility="collapsed")
    if pick and pick != cur:
        lg["my_team"] = pick
        store.save(owner, row["id"], lg)
        list_teams.clear()
        st.rerun()
    can_api = (lg.get("resync") or {}).get("type") in ("sleeper", "espn")
    if can_api:
        if c2.button("🔄 Re-sync", use_container_width=True, help="Pull the latest rosters, lineups and scoring"):
            try:
                with st.spinner("Syncing..."):
                    resync(S, store, owner, row)
                list_teams.clear()
                st.session_state._flash = "League re-synced."
                st.rerun()
            except Exception as e:
                st.error(str(e))
    else:
        if c2.button("⚡ Update from Yahoo" if lg["platform"] == "yahoo" else "⚡ Update", use_container_width=True,
                     help="Shows the bookmark that re-syncs this league"):
            st.session_state[f"_bm_open_{row['id']}"] = not st.session_state.get(f"_bm_open_{row['id']}", False)
    with c3.popover("⚙️ League settings", use_container_width=True):
        league_settings_editor(store, owner, row, lg)
    outdated = lg["platform"] == "yahoo" and lg.get("bookmark_version", 1) < LINEUP_BOOKMARK_VERSION
    if not can_api and (st.session_state.get(f"_bm_open_{row['id']}") or outdated):
        site = site_url()
        H(f'<div class="fr-card" style="border-left:5px solid {GOLD};margin:.3rem 0 .6rem">'
          f'<div class="fr-cardh" style="color:{GOLD}">Update this league</div><div class="fr-sub">'
          + ("This league was synced with an older bookmark, so it's missing your set lineup, kickers, defenses, "
             "IR and scoring. Add the new bookmark below (and delete the old one), open your league on Yahoo, "
             "and click it." if outdated else
             "Open your league on Yahoo (logged in) and click this bookmark. It updates this same league.")
          + '</div></div>')
        if site:
            bookmark_widget(site, key=f"bm_{row['id']}")
    if not pick:
        st.info("Pick your team above to see your lineup, matchup, trade partners and waiver targets.")
    with st.spinner("Analyzing the league..."):
        R = league_report(LS, skey(LS, row["id"], lg.get("synced_at"), pick, str(lg.get("slots"))), lg)
    week = R["week"]
    tabs = st.tabs(["📋 My team", "🆚 Matchup", "🏆 Power rankings", "🔁 Trades", "🧲 Waiver wire",
                    "👥 All rosters"])
    slots_all = {**DEFAULT_SLOTS, **(lg.get("slots") or {})}
    with tabs[0]:
        if pick and R.get("mine"):
            me = next(t for t in lg["teams"] if t["id"] == pick)
            render_team(LS, {"name": tnames[pick], "roster": me["players"], "scoring": lg.get("scoring", "half")},
                        R["mine"], show_header=False,
                        lineup_fn=lambda: lineup_compare(LS, {**me, "_platform": lg.get("platform")},
                                                         R["teams"][pick], week, slots_all))
        else:
            st.caption("Pick your team above.")
    with tabs[1]:
        render_matchup(LS, lg, R, pick, tnames, week)
    with tabs[2]:
        render_power(lg, R, pick, tnames)
    with tabs[3]:
        if not pick:
            st.caption("Pick your team above.")
        else:
            render_trades(LS, lg, R, pick, tnames, slots_all)
    with tabs[4]:
        if not pick:
            st.caption("Pick your team above.")
        else:
            W = R.get("waivers") or {}
            sec("Best available players (not on any roster in this league)")
            cols = st.columns(2)
            for i, pos in enumerate(pr.FANTASY_POS):
                with cols[i % 2]:
                    items = []
                    for x in W.get(pos, []):
                        p = x["p"]
                        tr = x["trend"]
                        trend = (f' · <span style="color:{GREEN if tr > 0 else RED}">usage {"▲" if tr > 0 else "▼"} '
                                 f'{abs(tr):.1f}</span>') if tr is not None and abs(tr) >= 1.5 else ""
                        items.append(player_row_html(p, f" · wk {week}: {p['proj']:.1f}{trend}",
                                                     f'<span style="color:{GREEN}">{x["ros"]:.0f}</span>'))
                    H(list_card(f"{pos}s", "Ranked by rest-of-season points", GREEN if pos in
                                R["teams"][pick]["needs"] else BLUE, items))
            kd = [k for k in ("K", "DEF") if W.get(k)]
            if kd:
                sec(f"Kickers and defenses to stream in week {week}")
                cols = st.columns(2)
                for i, kind in enumerate(kd):
                    with cols[i % 2]:
                        items = []
                        for x in W[kind]:
                            p = x["p"]
                            up = x["upgrade"]
                            items.append(
                                f'<div class="it"><div style="display:flex;gap:.55rem;align-items:center">{logo(p["team"], 24)}'
                                f'<div><b style="color:{TEXT}">{esc(p["name"])}</b><div class="sm">{esc(p["label"])} · '
                                f'{esc(p["reasons"][-1][1]) if p["reasons"] else ""}</div></div></div>'
                                f'<div class="num" style="color:{GREEN if up > 0.5 else MUTED}">{p["proj"]:.1f}'
                                f'<div class="sm" style="text-align:right">{up:+.1f} vs yours</div></div></div>')
                        H(list_card("Kickers" if kind == "K" else "Defenses",
                                    f"Ranked by week {week} projection under this league's scoring",
                                    GREEN if any(x["upgrade"] > 0.5 for x in W[kind]) else BLUE, items))
            st.caption("Green header = a position you need (or, for K/DEF, a better option than yours this week). "
                       "Skill players: number = projected rest-of-season points; 'Usage ▲' = his role grew over the last "
                       "3 games, often the best waiver signal. K/DEF: number = this week's projection, since they're "
                       "usually streamed.")
    with tabs[5]:
        order = sorted(lg["teams"], key=lambda t: -R["teams"][t["id"]]["ros_total"])
        accents = {t["id"]: TEAM_ACCENTS[i % len(TEAM_ACCENTS)] for i, t in enumerate(sorted(lg["teams"],
                                                                                            key=lambda t: t["id"]))}
        mine_first = sorted(order, key=lambda t: t["id"] != pick)
        rank = {t["id"]: i for i, t in enumerate(order, 1)}
        H(f'<div class="fr-sub" style="margin-bottom:.6rem">Sorted with your team first, then by power rank '
          f'(the number in each badge). <span class="fr-tag start">START?</span> = on the bench but in the '
          f'recommended lineup; <span class="fr-tag sit">SIT?</span> = starting but not recommended.</div>')
        cards = [team_card_html(LS, t, R["teams"][t["id"]], week, rank[t["id"]], accents[t["id"]], t["id"] == pick,
                                lg["teams_in_league"]) for t in mine_first]
        H(f'<div class="fr-grid g2">{"".join(cards)}</div>')
    glossary(["ROS", "Projection", "xFP", "TD luck", "Floor / ceiling", "Defense rank"])


def set_lineup_list(S, t, T):
    es = resolve_entries(S, t)
    out = [{"slot": e["slot"], "p": T["projs"].get(entry_key(e)), "e": e} for e in ordered_entries(es, "start")]
    return out


def trade_side_html(S, players, color, title):
    rows = []
    for k, pos, rate in players:
        p = S.players.get(k) or {}
        nm = (S.season_tot.get(k) or {}).get("name") or p.get("name") or k
        team = pr.player_team(S, k)
        rows.append(f'<div style="display:flex;align-items:center;gap:.45rem;margin:.15rem 0">{logo(team, 22)}'
                    f'{plink(k, nm)} <span class="fr-dim">{pos} · {rate:.1f}/g</span></div>')
    return f'<div><div class="fr-cardh" style="color:{color}">{title}</div>{"".join(rows)}</div>'


def render_trades(S, lg, R, pick, tnames, slots):
    needs = R["teams"][pick]["needs"]
    H(notes_html([("down", f"Your weakest spots: {', '.join(needs)}.")] if needs else
                 [("up", "Every starting spot is at or above an average starter in this league.")]))
    weeks = remaining_weeks(S)
    P = R.get("partners") or []
    sec("Best trades for you (that they'd likely accept)")
    if P:
        items = []
        for t in P:
            fit_col = GREEN if t["fit"] == "win-win" else BLUE
            items.append(
                f'<div class="fr-card" style="margin-bottom:.5rem"><div style="display:flex;justify-content:space-between;'
                f'flex-wrap:wrap;gap:.4rem"><div class="fr-cardh" style="color:{fit_col}">With {esc(t["team"])} · '
                f'{t["fit"]}</div><div class="fr-dim">your lineup <b style="color:#4ade80">{t["mg"]:+.1f}/g</b> '
                f'(≈{t["ros_gain"]:+.0f} pts rest of season) · theirs <b style="color:{GREEN if t["tg"] >= 0 else AMBER}">'
                f'{t["tg"]:+.1f}/g</b> · on paper they get {t["their_in"]:.1f} PPG for {t["their_out"]:.1f}</div></div>'
                f'<div style="display:flex;flex-wrap:wrap;gap:1rem;align-items:center;'
                f'justify-content:space-between;margin-top:.35rem">'
                f'{trade_side_html(S, t["give"], RED, "You give")}<div style="font-size:1.4rem;color:{MUTED}">⇄</div>'
                f'{trade_side_html(S, t["get"], GREEN, "You get")}</div></div>')
        H("".join(items))
        st.caption("Every possible 1-for-1 and 2-for-1 swap with every team. Ranked by how much it improves your best "
                   f"starting lineup over the rest of the season ({weeks} weeks, schedule included, rosters kept "
                   "full), kept only if their lineup doesn't take a real hit and it looks fair on paper to them "
                   "(points per game so far, which is how most managers judge). The edge: you're trading on the "
                   "model, they're trading on box scores. Win-win = both lineups improve; sells itself = looks like a "
                   "win to them. /g = points per game.")
    else:
        st.caption("No trades that clearly improve your lineup without hurting theirs right now.")
    sec("Trade analyzer")
    others = [t["id"] for t in lg["teams"] if t["id"] != pick]
    c1, c2, c3 = st.columns([1.2, 2, 2])
    tid = c1.selectbox("Trade with", others, format_func=lambda i: tnames[i], key="ta_team")
    me = next(t for t in lg["teams"] if t["id"] == pick)
    them = next(t for t in lg["teams"] if t["id"] == tid)
    mine, theirs = roster_rates(S, team_keys(S, me)[0]), roster_rates(S, team_keys(S, them)[0])
    nm = lambda k: (S.season_tot.get(k) or {}).get("name") or (S.players.get(k) or {}).get("name") or k  # noqa: E731
    give = c2.multiselect("You give", [p[0] for p in sorted(mine, key=lambda p: -p[2])], format_func=nm, key="ta_give",
                          placeholder="Your players")
    get = c3.multiselect("You get", [p[0] for p in sorted(theirs, key=lambda p: -p[2])], format_func=nm, key="ta_get",
                         placeholder="Their players")
    if give or get:
        owned = {p[0] for t_ in lg["teams"] for p in roster_rates(S, team_keys(S, t_)[0])}
        mg, tg = evaluate_trade(S, slots, mine, theirs, give, get, waiver_rates(S, owned))
        po = [w for w in pr.FANTASY_PLAYOFF_WEEKS if w >= (pr.next_week(S) or 99)]

        def weekly_gain(roster_keys, out_keys, in_keys, w):
            def tot(keys):
                ps = {k: project_any(S, k, w) for k in keys}
                return lineup_pg([(k, p["pos"], p["proj"]) for k, p in ps.items() if p and p["pos"] in pr.FANTASY_POS],
                                 slots)
            before = tot(roster_keys)
            after = tot([k for k in roster_keys if k not in out_keys] + list(in_keys))
            return after - before
        mk_ = [p[0] for p in mine]
        po_gain = sum(weekly_gain(mk_, give, get, w) for w in po) if po else None
        give_val = sum(ros_rate(S, k) or 0 for k in give)
        get_val = sum(ros_rate(S, k) or 0 for k in get)
        verdict, vcol = (("Accept", GREEN) if mg >= 0.8 else ("Lean accept", "#86efac") if mg >= 0.25 else
                         ("Neutral", MUTED) if mg > -0.25 else ("Lean decline", "#fca5a5") if mg > -0.8 else
                         ("Decline", RED))
        def mkt(k):
            t_ = S.season_tot.get(k)
            return t_["ppg"] if t_ else (ros_rate(S, k) or 0)
        their_in, their_out = sum(mkt(k) for k in give), sum(mkt(k) for k in get)
        ratio = their_in / their_out if their_out else 2.0
        they = ("they'd likely say yes" if (tg >= 0.2 or ratio >= 1.08) and ratio >= 0.95 else
                "a fair ask" if ratio >= 0.95 and tg >= -0.3 else "they'd probably say no")
        H('<div class="fr-grid">' + "".join([
            kpi("Verdict for you", verdict, f"{they}", vcol, vcol),
            kpi("Your lineup", f"{mg:+.1f}/g", f"≈{mg * weeks:+.0f} pts over {weeks} weeks", GREEN if mg > 0 else RED,
                GREEN if mg > 0 else RED),
            kpi("Fantasy playoffs", f"{po_gain:+.1f}" if po_gain is not None else "–",
                f"weeks {pr.FANTASY_PLAYOFF_WEEKS[0]}-{pr.FANTASY_PLAYOFF_WEEKS[-1]}, real matchups",
                GREEN if (po_gain or 0) > 0 else RED if (po_gain or 0) < 0 else BORDER),
            kpi("Their side", f"{tg:+.1f}/g", f"on paper: {their_in:.1f} PPG in for {their_out:.1f} out",
                GREEN if tg > 0 else AMBER, TEXT),
        ]) + "</div>")
        st.caption("Judged by your best starting lineup, not raw player value: a better player you can't start (or "
                   "losing depth you need) shows up here. Rates are the model's rest-of-season points per game.")


def render_matchup(S, lg, R, pick, tnames, week):
    if not pick:
        st.caption("Pick your team above.")
        return
    opp = R.get("opponent")
    ids = [t["id"] for t in lg["teams"] if t["id"] != pick]
    if not opp or opp not in R["teams"]:
        opp = st.selectbox("This week's opponent", ids, index=None, format_func=lambda i: tnames[i],
                           placeholder="Pick your opponent", key=f"opp_{pick}")
        if not opp:
            st.caption("Pick your opponent to see the head-to-head projection.")
            return
    tA = next(t for t in lg["teams"] if t["id"] == pick)
    tB = next(t for t in lg["teams"] if t["id"] == opp)
    A, B = R["teams"][pick], R["teams"][opp]
    setA, setB = set_lineup_list(S, tA, A), set_lineup_list(S, tB, B)
    has_set = bool(setA) and bool(setB)
    a1, b1, p1 = win_prob([x for x in setA if x["p"]], [x for x in setB if x["p"]]) if has_set else (0, 0, None)
    a2, b2, p2 = win_prob(A["lineup"], B["lineup"])
    show = p1 if p1 is not None else p2
    col = GREEN if show >= 0.55 else RED if show <= 0.45 else AMBER
    tiles = []
    if p1 is not None:
        tiles.append(kpi("Win chance · lineups as set", f"{p1:.0%}", f"{a1:.1f} vs {b1:.1f} projected", col, col))
    c2 = GREEN if p2 >= 0.55 else RED if p2 <= 0.45 else AMBER
    tiles.append(kpi("Win chance · if you both play the best lineup", f"{p2:.0%}", f"{a2:.1f} vs {b2:.1f} projected",
                     c2, c2))
    if p1 is not None:
        my_best_vs_set = win_prob(A["lineup"], [x for x in setB if x["p"]])[2]
        d = my_best_vs_set - p1
        tiles.append(kpi("Your gain from the recommended lineup", f"{d * 100:+.0f} pts",
                         f"win chance {my_best_vs_set:.0%} with the best lineup", GREEN if d > 0.01 else BORDER,
                         GREEN if d > 0.01 else TEXT))
    H(f'<div class="fr-sub" style="margin-bottom:.5rem">Week {week} · {esc(tnames[pick])} vs {esc(tnames[opp])}</div>'
      f'<div class="fr-grid g3">{"".join(tiles)}</div>')
    view = "set"
    if has_set:
        view = "set" if st.radio("Show", ["Lineups as set", "Recommended lineups"], horizontal=True,
                                 key=f"mv_{pick}", label_visibility="collapsed") == "Lineups as set" else "best"
    else:
        view = "best"

    you_tag = ' <span class="fr-you">YOU</span>'

    def card(t, T, rows, total, accent, me):
        lines = []
        for x in rows:
            e = x.get("e") or (make_entry(S, x["p"]["pid"], slot=x["slot"]) if x["p"] else
                               {"gid": None, "name": "Empty slot", "pos": None, "team": None, "slot": x["slot"],
                                "status": None})
            if "e" in x:
                e = x["e"]
            else:
                e = {**e, "slot": x["slot"]}
            lines.append(player_line(S, e, x["p"], week))
        lines.insert(0, grp_header("Starters"))
        return (f'<div class="fr-tc" style="border-top:4px solid {accent}"><div class="fr-tc-head" style="background:'
                f'linear-gradient(120deg,{accent}33 0%,transparent 70%)"><div style="flex:1;min-width:0">'
                f'<div class="fr-tc-name">{esc(t["name"])}{you_tag if me else ""}</div>'
                f'<div class="fr-tc-sub">{esc(t.get("owner") or "")}</div></div><div class="fr-tc-tot"><div class="v">'
                f'{total:.1f}</div><div class="l">wk {week} proj</div></div></div><div class="fr-tc-body">'
                f'{"".join(lines)}</div></div>')
    if view == "set":
        L = card(tA, A, setA, a1, GOLD, True)
        Rr = card(tB, B, setB, b1, BLUE, False)
    else:
        L = card(tA, A, A["lineup"], a2, GOLD, True)
        Rr = card(tB, B, B["lineup"], b2, BLUE, False)
    H(f'<div style="height:.6rem"></div><div class="fr-grid g2">{L}{Rr}</div>')
    st.caption("Win chance accounts for how much each starter's scoring swings week to week, kickers and defenses "
               "included. PROJ = projected points; FINAL = his game is already over.")


def render_power(lg, R, pick, tnames):
    rows = []
    order = sorted(lg["teams"], key=lambda t: -R["teams"][t["id"]]["ros_total"])
    for i, t in enumerate(order, 1):
        T = R["teams"][t["id"]]
        rec = t.get("record")
        r = {"Rank": i, "Team": t["name"] + (" (you)" if t["id"] == pick else ""),
             "Record": f"{rec[0]}-{rec[1]}{'-' + str(rec[2]) if rec and rec[2] else ''}" if rec else "",
             f"Wk {R['week']} proj": round(T["total"], 1), "ROS strength": round(T["ros_total"])}
        for pos in pr.FANTASY_POS:
            if pos in T["grades"]:
                r[pos] = T["grades"][pos]["grade"][0]
        rows.append(r)
    df = pd.DataFrame(rows)
    gcol = {"A": GREEN, "B": "#86efac", "C": AMBER, "D": "#fca5a5", "F": RED}
    styled_df(df, row_bg=lambda r: "rgba(245,179,1,.12)" if str(r.get("Team", "")).endswith("(you)") else None,
              cell={pos: (lambda v: gcol.get(v)) for pos in pr.FANTASY_POS})
    st.caption("Ranked by ROS strength: each team's best lineup projected over the rest of the season through the "
               "fantasy playoffs. Letter grades compare each team's starters with an average starter in this league.")


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
                ident = text_in("Username or email", "username")
                pw = text_in("Password", "current-password", type="password")
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
                un = text_in("Username", "username", max_chars=20, help="3-20 letters, numbers, dots, dashes or underscores")
                em = text_in("Email", "email", help="Only used to recover your account. Never shown to anyone.")
                p1 = text_in("Password", "new-password", type="password", help="At least 8 characters, mixing letters and numbers")
                p2 = text_in("Confirm password", "new-password", type="password")
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
                    ident = text_in("Username or email", "username", key="fp_ident")
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
                        code = text_in("6-digit code", "one-time-code", max_chars=7)
                        n1 = text_in("New password", "new-password", type="password")
                        n2 = text_in("Confirm new password", "new-password", type="password")
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
                    ident = text_in("Username or email", "username", key="fk_ident")
                    key = text_in("Recovery key", "off", placeholder="XXXXX-XXXXX-XXXXX-XXXXX")
                    n1 = text_in("New password", "new-password", type="password", key="fk_n1")
                    n2 = text_in("Confirm new password", "new-password", type="password", key="fk_n2")
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
        saved = (st.session_state.get("fr_auth_store") or {}).get("token")
        remembered = bool(st.session_state.get("_token")) and st.session_state.get("_token") in (saved, read_cookie())
        st.caption("✅ This device stays signed in." if remembered else
                   "This device will ask you to sign in next visit. Sign out and back in with "
                   "'Keep me signed in' checked to remember it.")
        t1, t2, t3, t4 = st.tabs(["Password", "Email", "Recovery key", "Delete account"])
        with t1:
            with st.form("chpw"):
                cur = text_in("Current password", "current-password", type="password")
                n1 = text_in("New password", "new-password", type="password")
                n2 = text_in("Confirm new password", "new-password", type="password")
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
                em = text_in("New email", "email", value=a["email"])
                cur = text_in("Current password", "current-password", type="password", key="chem_pw")
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
                cur = text_in("Current password", "current-password", type="password", key="nk_pw")
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
                confirm = text_in(f"Type your username ({a['display_name']}) to confirm", "off")
                cur = text_in("Current password", "current-password", type="password", key="del_pw")
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
        if not st.session_state.get("_store_ready") and not st.session_state.get("_skip_wait"):
            H(f'<div class="fr-card" style="text-align:center;padding:1.6rem 1rem;max-width:520px;margin:1rem auto">'
              f'<div class="fr-sub">Checking if this device is signed in...</div></div>')
            _, mid, _ = st.columns([1, 1, 1])
            if mid.button("Sign in manually", use_container_width=True):
                st.session_state._skip_wait = True
                st.rerun()
            return None, None
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


def sort_teams(teams):
    """Your chosen order first (set in ⋯ Manage), then most recently updated."""
    return sorted(teams, key=lambda t: (t["data"].get("order", 999), -(_parse_ts(t.get("updated_at")) or
                                                                       datetime(2000, 1, 1, tzinfo=timezone.utc)).timestamp()))


def default_team_id(teams):
    return next((t["id"] for t in teams if t["data"].get("is_default")), teams[0]["id"])


def manage_teams(store, owner, teams, by_id, tid, is_league):
    cur = by_id[tid]
    st.markdown(f"**{esc(cur['name'])}**")
    c1, c2 = st.columns(2)
    if cur["data"].get("is_default"):
        if c1.button("☆ Remove default", key="mg_undef", use_container_width=True):
            cur["data"]["is_default"] = False
            store.save(owner, tid, cur["data"])
            list_teams.clear()
            st.rerun()
    elif c1.button("⭐ Open this by default", key="mg_def", use_container_width=True):
        for t in teams:
            if t["data"].get("is_default") and t["id"] != tid:
                t["data"]["is_default"] = False
                store.save(owner, t["id"], t["data"])
        cur["data"]["is_default"] = True
        store.save(owner, tid, cur["data"])
        list_teams.clear()
        st.rerun()
    if not is_league:
        if c2.button("✏️ Edit team", key="mg_edit", use_container_width=True):
            st.session_state.team_mode = "edit"
            st.session_state.pop("edit_roster", None)
            st.rerun()
    if st.button("🗑️ Delete", key="mg_del", use_container_width=True):
        st.session_state._confirm_delete = tid
        st.rerun()
    if len(teams) > 1:
        st.markdown("**Order in the dropdown**")
        ids = [t["id"] for t in teams]
        for i, t in enumerate(teams):
            r = st.columns([5, 1, 1])
            star = "⭐ " if t["data"].get("is_default") else ""
            r[0].markdown(f'<div style="padding-top:.45rem;font-size:.86rem">{i + 1}. {star}{esc(t["name"])}</div>',
                          unsafe_allow_html=True)
            if r[1].button("↑", key=f"up_{t['id']}", disabled=i == 0):
                ids[i - 1], ids[i] = ids[i], ids[i - 1]
                save_order(store, owner, by_id, ids)
            if r[2].button("↓", key=f"dn_{t['id']}", disabled=i == len(ids) - 1):
                ids[i + 1], ids[i] = ids[i], ids[i + 1]
                save_order(store, owner, by_id, ids)
        st.caption("⭐ The default opens first every time you come to My Teams.")


def save_order(store, owner, by_id, ids):
    for n, i in enumerate(ids):
        d = by_id[i]["data"]
        if d.get("order") != n:
            d["order"] = n
            store.save(owner, i, d)
    list_teams.clear()
    st.rerun()


def page_teams(S, season):
    owner, store = teams_login_gate()
    if not owner:
        return
    try:
        teams = list_teams(owner, store)
    except Exception as e:
        st.error(f"Couldn't load your teams: {e}")
        return
    if st.session_state.get("_paste_mode"):
        H(f'<div class="fr-card" style="border-left:5px solid {GOLD}"><div class="fr-cardh" style="color:{GOLD}">'
          f'Almost there</div><div style="font-weight:800;color:{TEXT};font-size:1.1rem">Paste your league below</div>'
          f'<div class="fr-sub">Your league was copied by the bookmark. Click the box and press Ctrl+V (Cmd+V on Mac), '
          f'then Import.</div></div>')
        with st.form("paste_sync"):
            code = st.text_area("Sync code", height=90, label_visibility="collapsed", placeholder="Paste here")
            c1, c2 = st.columns([1, 4])
            go_ = c1.form_submit_button("Import league", type="primary", use_container_width=True)
            stop = c2.form_submit_button("Cancel")
        if stop:
            st.session_state.pop("_paste_mode", None)
            st.rerun()
        if go_:
            try:
                payload = decode_sync(code)
            except ValueError as e:
                st.error(str(e))
                return
            st.session_state.pop("_paste_mode", None)
            with st.spinner("Matching players..."):
                try:
                    league = league_from_sync(S, payload)
                except Exception as e:
                    st.error(f"Couldn't import: {e}")
                    return
            finish_import(store, owner, teams, league)
        return
    if handle_pending_sync(S, store, owner, teams):
        return
    mode = st.session_state.get("team_mode", "view")
    if mode in ("new", "sync") and len(teams) >= MAX_TEAMS:
        st.warning(f"You can save up to {MAX_TEAMS} leagues and teams. Delete one to add another.")
        mode = "view"
    if mode == "sync":
        sync_page(S, store, owner, teams, season)
        return
    if mode == "new":
        team_editor(S, store, owner, None)
        return
    if not teams:
        H('<div class="fr-title">My leagues & teams</div>')
        H(f'<div class="fr-card" style="text-align:center;padding:2.2rem 1rem;margin-top:.8rem">'
          f'<div style="font-size:2.2rem">🏈</div><div style="font-weight:800;color:{TEXT};font-size:1.15rem;'
          f'margin:.3rem 0">Bring in your league</div><div class="fr-sub">Sync a whole Sleeper, ESPN or Yahoo league to '
          f'get your matchup odds, start/sit calls, power rankings, trade partners and waiver targets. '
          f'Or build a team by hand.</div></div>')
        c = st.columns([1, 1.2, 1.2, 1])
        if c[1].button("🔄 Sync a league", type="primary", use_container_width=True):
            st.session_state.team_mode = "sync"
            st.rerun()
        if c[2].button("📝 Build a team", use_container_width=True):
            st.session_state.team_mode = "new"
            st.session_state.pop("edit_roster", None)
            st.rerun()
        return
    teams = sort_teams(teams)
    by_id = {t["id"]: t for t in teams}
    if st.session_state.get("team_sel") not in by_id:
        st.session_state.team_sel = default_team_id(teams)
    if mode == "edit":
        row = by_id[st.session_state.team_sel]
        if row["data"].get("kind") == "league":
            st.session_state.team_mode = "view"
        else:
            team_editor(S, store, owner, row)
            return

    def label(t):
        d = by_id[t]["data"]
        star = "⭐ " if d.get("is_default") else ""
        if d.get("kind") == "league":
            return f"{star}🏆 {d['name']} · {PLATFORM_LABEL.get(d.get('platform'), '')}"
        return f"{star}📝 {d['name']}"
    top = st.columns([3.2, 1.15, 1.1, 1.05])
    tid = top[0].selectbox("Team", list(by_id), key="team_sel", format_func=label, label_visibility="collapsed")
    is_league = by_id[tid]["data"].get("kind") == "league"
    if top[1].button("🔄 Sync league", use_container_width=True):
        st.session_state.team_mode = "sync"
        st.rerun()
    if top[2].button("📝 New team", use_container_width=True):
        st.session_state.team_mode = "new"
        st.session_state.pop("edit_roster", None)
        st.rerun()
    with top[3].popover("⋯ Manage", use_container_width=True):
        manage_teams(store, owner, teams, by_id, tid, is_league)
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
    if is_league:
        render_league(S, store, owner, by_id[tid], season)
        return
    team = by_id[tid]["data"]
    TS = get_season(season, team.get("scoring", S.fmt_name)) if team.get("scoring", S.fmt_name) != S.fmt_name else S
    with st.spinner("Analyzing your team..."):
        A = analyze_team(TS, team)
    render_team(TS, team, A)


def render_team(S, team, A, show_header=True, lineup_fn=None):
    week = A["week"]
    lt, la = A.get("lineup_total"), A.get("league_avg_total")
    edge = div(lt - la, la) if (lt is not None and la) else None
    head_col = GREEN if (edge or 0) >= 0.05 else RED if (edge or 0) <= -0.05 else AMBER
    grades = A["grades"]
    if show_header:
        H(f'<div class="fr-lbar" style="--pc:{GOLD}"><div class="fr-lbar-name">{esc(team["name"])}</div>'
          f'<span class="fr-lchip plat">Manual team</span>'
          f'<span class="fr-lchip">{A["n_teams"]}-team league</span>'
          f'<span class="fr-lchip sc">{pr.FORMAT_LABEL[team.get("scoring", "half")].replace(" scoring", "")}</span>'
          f'<span class="fr-lchip">{len(team["roster"])} players</span>'
          f'<span class="fr-lbar-sync" style="font-size:.85rem;color:#fff"><b style="color:{head_col}">'
          f'{fmt(lt, "dec1")}</b> wk {week} proj</span></div>')
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
        strip = []
        if A.get("bye_names"):
            strip.append(f'<span class="fr-strip-k">Byes</span>' + " · ".join(esc(n) for n in A["bye_names"]))
        if A.get("inj_list"):
            strip.append(f'<span class="fr-strip-k">Injuries</span>' + " · ".join(
                f'{esc(n)} {inj_badge(st_)}' for n, st_, out_ in A["inj_list"]))
        if strip:
            H('<div class="fr-strip">' + '<span class="fr-strip-sep"></span>'.join(strip) + "</div>")
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
        if lineup_fn:
            lineup_fn()
        else:
            starters = []
            for l in A["lineup"]:
                p = l["p"]
                e = make_entry(S, p["pid"], slot=l["slot"]) if p else \
                    {"gid": None, "name": "Empty slot", "pos": None, "team": None, "slot": l["slot"], "status": None}
                starters.append(player_line(S, e, p, week))
            bench = [player_line(S, make_entry(S, p["pid"], slot="BN"), p, week) for p in A["bench"]]
            card = (f'<div class="fr-tc" style="border-top:4px solid {GOLD}"><div class="fr-tc-body">'
                    f'<div class="fr-grp"><b>Recommended starters</b><span>{lt:.1f} proj</span></div>{"".join(starters)}'
                    + (f'<div class="fr-grp"><b>Bench</b></div>{"".join(bench)}' if bench else "") + "</div></div>")
            H(card)
            st.caption("Recommended = highest projection at every slot. PROJ = projected fantasy points this week; "
                       "FINAL = his game is over. Tap a name for his full report, or use Compare for a head-to-head.")
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
            H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class=sm>None. Nobody is running hot on touchdowns.</div>"}</div></div>')
            sec("Surplus depth (startable on most teams)")
            items = [player_row_html(x["p"], "", f'<span style="color:{BLUE}">{x["ros"]:.0f} ROS</span>')
                     for x in A["surplus"]]
            H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class=sm>No spare starters on the bench.</div>"}</div></div>')
        with c2:
            for pos in needs[:2]:
                sec(f"{pos} upgrade targets")
                items = [player_row_html(x["p"], " · buy-low" if x["buy_low"] else "",
                                         f'<span style="color:{GREEN}">{x["ros"]:.0f} ROS</span>')
                         for x in A["targets"].get(pos, [])]
                H(f'<div class="fr-card"><div class="fr-list">{"".join(items) or "<div class=sm>No clear upgrades found.</div>"}</div></div>')
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
    if show_header:
        glossary(["ROS", "Projection", "xFP", "TD luck", "PPG", "Floor / ceiling", "Defense rank", "Implied total"])


# ------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------

def main():
    H(CSS)
    ui_helper()
    restore_session()
    sync_code = st.query_params.get("sync")
    if sync_code == "paste":
        st.session_state._paste_mode = True
        st.session_state.view = "My Teams"
        st.query_params.pop("sync", None)
    elif sync_code:
        st.session_state._pending_sync = sync_code
        st.session_state.view = "My Teams"
        st.query_params.pop("sync", None)
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
