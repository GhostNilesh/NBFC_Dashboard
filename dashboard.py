"""Premium Streamlit UI and robust data retrieval."""
from __future__ import annotations
import re
from typing import Optional
import pandas as pd
import streamlit as st
from charts import (find_metric, latest_row, normalize_metric, plot_asset_quality,
                    plot_metric_trend, plot_peer_heatmap, year_sort_key)
from config import ASSET_QUALITY_ALIASES, COLORS, PEER_METRICS, SEGMENT_ICONS


def apply_theme():
    st.markdown(f"""<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"] {{font-family:Inter,'Segoe UI',sans-serif}}
    .stApp {{background:radial-gradient(circle at 85% 0%,rgba(32,227,210,.08),transparent 28%),{COLORS['background']};}}
    #MainMenu, footer {{visibility:hidden}} .block-container{{max-width:1480px;padding:2.2rem 3rem 5rem}}
    [data-testid="stHeader"]{{background:rgba(5,11,18,.78);backdrop-filter:blur(14px)}}
    [data-testid="stSidebar"]{{background:#07121C;border-right:1px solid #162C3A}}
    h1{{font-weight:800;letter-spacing:-.035em}} h2,h3{{letter-spacing:-.02em}}
    .hero{{padding:26px 30px;border:1px solid #17384A;border-radius:22px;background:linear-gradient(120deg,#0C1925 0%,#0D2330 58%,#0A3337 100%);box-shadow:0 24px 70px rgba(0,0,0,.28);margin-bottom:28px}}
    .hero-title{{font-size:2.7rem;font-weight:800;color:#F5FBFF;letter-spacing:-.04em;margin:0}}
    .hero-sub{{color:#9CB1BE;margin-top:8px;font-size:1rem}} .live{{color:{COLORS['cyan']};font-weight:700;font-size:.78rem;letter-spacing:.16em}}
    .section-label{{color:{COLORS['cyan']};font-size:.76rem;letter-spacing:.18em;font-weight:800;margin-bottom:4px}}
    div[data-testid="stMetric"]{{background:linear-gradient(145deg,#0C1924,#102535);border:1px solid #1B3A4B;border-radius:16px;padding:17px 18px;box-shadow:0 10px 28px rgba(0,0,0,.18)}}
    div[data-testid="stMetricLabel"]{{color:#8FA7B5}} div[data-testid="stMetricValue"]{{color:#F7FBFD;font-weight:750}}
    .stButton>button{{min-height:92px;border:1px solid #1C4153;border-radius:16px;background:linear-gradient(145deg,#0B1721,#10232F);color:#EDF8FC;font-weight:650;box-shadow:0 10px 28px rgba(0,0,0,.16);transition:.18s ease}}
    .stButton>button:hover{{border-color:{COLORS['cyan']};color:{COLORS['cyan']};transform:translateY(-3px);box-shadow:0 16px 34px rgba(0,0,0,.3)}}
    [data-testid="stDataFrame"]{{border:1px solid #193443;border-radius:14px;overflow:hidden}}
    .stTabs [data-baseweb="tab-list"]{{gap:8px;background:#091620;padding:7px;border-radius:13px}}
    .stTabs [data-baseweb="tab"]{{border-radius:9px;padding:9px 18px}} .stTabs [aria-selected="true"]{{background:#123240;color:{COLORS['cyan']}}}
    </style>""", unsafe_allow_html=True)


def format_value(row: Optional[pd.Series]) -> str:
    if row is None or pd.isna(row.get("ValueNumeric")): return "N/A"
    v=float(row["ValueNumeric"]); kind=str(row.get("ValueKind","")).lower(); unit=str(row.get("Unit",""))
    if kind=="percentage": return f"{v*100:.2f}%"
    if kind=="multiple": return f"{v:.2f}x"
    suffix=" Cr" if "crore" in unit.lower() else ""
    return (f"{v:,.0f}" if abs(v)>=100 else f"{v:,.2f}")+suffix


def metric_latest(company_df, alias): return latest_row(find_metric(company_df, alias))


def hero(title, subtitle):
    st.markdown(f'<div class="hero"><div class="live">● LIVE INTELLIGENCE</div><div class="hero-title">{title}</div><div class="hero-sub">{subtitle}</div></div>',unsafe_allow_html=True)


def show_segment_tiles(df):
    hero("NBFC Intelligence Platform","Compiled financials, profitability, asset quality and peer benchmarking in one research workspace")
    st.markdown('<div class="section-label">LEVEL 1 · SEGMENT UNIVERSE</div>',unsafe_allow_html=True); st.header("Choose a coverage segment")
    stats=df.groupby("Segment")["Company"].nunique().sort_index(); cols=st.columns(4)
    for i,(segment,count) in enumerate(stats.items()):
        icon=SEGMENT_ICONS.get(segment,"◇")
        with cols[i%4]:
            if st.button(f"{icon}  {segment}\n\n{count} covered NBFCs",key=f"s_{segment}",use_container_width=True):
                st.session_state.selected_segment=segment; st.session_state.selected_company=None; st.rerun()


def show_company_cards(df, segment):
    a,b=st.columns([6,1]);
    with a: hero(segment,"Select a company to open the detailed research workspace")
    with b:
        if st.button("← Segments",use_container_width=True): st.session_state.selected_segment=None; st.rerun()
    companies=sorted(df.loc[df.Segment.eq(segment),"Company"].unique()); q=st.text_input("Search companies",placeholder="Search by NBFC name...")
    if q: companies=[c for c in companies if q.lower() in c.lower()]
    cols=st.columns(4)
    for i,company in enumerate(companies):
        cdf=df[(df.Segment==segment)&(df.Company==company)]; aum=format_value(metric_latest(cdf,"AUM")); roa=format_value(metric_latest(cdf,"ROA"))
        with cols[i%4]:
            if st.button(f"{company}\n\nAUM {aum}   •   ROA {roa}",key=f"c_{segment}_{company}",use_container_width=True):
                st.session_state.selected_company=company; st.rerun()


def normalized_match(data, aliases):
    wanted={normalize_metric(x) for x in aliases}; temp=data.copy(); temp["_n"]=temp.Metric.map(normalize_metric)
    return temp[temp._n.map(lambda x:any(a==x or a in x for a in wanted))]


def find_stage_value(cdf, aliases):
    row=latest_row(normalized_match(cdf,aliases)); return None if row is None else float(row.ValueNumeric)


def build_peer_table(segment_df):
    rows=[]
    for company,cdf in segment_df.groupby("Company"):
        item={"Company":company}; found=False
        for alias in PEER_METRICS:
            r=metric_latest(cdf,alias)
            if r is None: item[alias]=float("nan")
            else:
                v=float(r.ValueNumeric); item[alias]=v*100 if str(r.ValueKind).lower()=="percentage" else v; found=True
        if found: rows.append(item)
    return pd.DataFrame(rows)


def section_table(cdf,section):
    d=cdf[cdf.Section.eq(section)].copy()
    if d.empty:return d
    t=d.pivot_table(index="Metric",columns="Year",values="ValueNumeric",aggfunc="first")
    return t.reindex(columns=sorted(t.columns,key=year_sort_key))


def ratio_display_table(cdf,section):
    d=cdf[cdf.Section.eq(section)].copy()
    if d.empty:return d
    d["DisplayValue"]=d.apply(lambda r:r.ValueNumeric*100 if str(r.ValueKind).lower()=="percentage" else r.ValueNumeric,axis=1)
    t=d.pivot_table(index="Metric",columns="Year",values="DisplayValue",aggfunc="first")
    return t.reindex(columns=sorted(t.columns,key=year_sort_key))


def show_company_dashboard(df,segment,company):
    n1,n2,n3=st.columns([6,1,1])
    with n1: hero(company,f"{segment} · Financial and risk intelligence")
    with n2:
        if st.button("← Companies",use_container_width=True): st.session_state.selected_company=None;st.rerun()
    with n3:
        if st.button("⌂ Home",use_container_width=True): st.session_state.selected_company=None;st.session_state.selected_segment=None;st.rerun()
    cdf=df[(df.Segment==segment)&(df.Company==company)].copy(); sdf=df[df.Segment==segment]
    specs=[("AUM","AUM / Gross Loans"),("PAT","PAT"),("ROA","ROA"),("ROE","ROE"),("GNPA","GNPA"),("CAR","CAR")]
    cols=st.columns(6)
    for col,(key,label) in zip(cols,specs):
        r=metric_latest(cdf,key); col.metric(label,format_value(r),str(r.Year) if r is not None else "Not available")
    overview,financials,ratios,peers,diagnostics=st.tabs(["Overview","Financials","Risk & Ratios","Peer Matrix","Data Check"])
    with overview:
        a,b=st.columns(2); a.plotly_chart(plot_metric_trend(cdf,"AUM","AUM / Gross Loan Book"),use_container_width=True); b.plotly_chart(plot_metric_trend(cdf,"PAT","Profit After Tax"),use_container_width=True)
        a,b=st.columns(2); a.plotly_chart(plot_metric_trend(cdf,"ROA","Return on Assets"),use_container_width=True); b.plotly_chart(plot_metric_trend(cdf,"GNPA","Gross NPA"),use_container_width=True)
    with financials:
        t=section_table(cdf,"Financials"); st.dataframe(t.style.format("{:,.2f}",na_rep="-"),use_container_width=True,height=680)
    with ratios:
        stages={k:find_stage_value(cdf,v) for k,v in ASSET_QUALITY_ALIASES.items()}; a,b=st.columns(2); a.plotly_chart(plot_asset_quality(stages),use_container_width=True); b.plotly_chart(plot_metric_trend(cdf,"ROE","Return on Equity"),use_container_width=True)
        sections=[x for x in cdf.Section.dropna().unique() if x!="Financials"]
        if sections:
            sec=st.selectbox("Ratio section",sections); t=ratio_display_table(cdf,sec); st.dataframe(t.style.format("{:,.2f}",na_rep="-"),use_container_width=True,height=470)
    with peers:
        p=build_peer_table(sdf); st.plotly_chart(plot_peer_heatmap(p,company),use_container_width=True)
        st.dataframe(p.set_index("Company").style.format("{:.2f}",na_rep="-"),use_container_width=True)
    with diagnostics:
        st.caption("Use this tab when a KPI appears missing. It shows every parsed metric for the selected company.")
        check=cdf[["Section","Metric","Year","ValueNumeric","ValueKind","Unit","SourceCell"]].sort_values(["Section","Metric","Year"])
        st.dataframe(check,use_container_width=True,height=620)


def render_dashboard(df):
    apply_theme(); st.session_state.setdefault("selected_segment",None); st.session_state.setdefault("selected_company",None)
    if not st.session_state.selected_segment: show_segment_tiles(df)
    elif not st.session_state.selected_company: show_company_cards(df,st.session_state.selected_segment)
    else: show_company_dashboard(df,st.session_state.selected_segment,st.session_state.selected_company)
