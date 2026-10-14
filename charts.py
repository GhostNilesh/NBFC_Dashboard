"""Robust metric matching and Bloomberg-style Plotly charts."""
from __future__ import annotations
import re
from typing import Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from config import COLORS, KPI_ALIASES, LOWER_IS_BETTER


def normalize_metric(value: object) -> str:
    text = str(value or "").lower().replace("&", " and ").replace("%", " percent ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\b(on|the|of)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def year_sort_key(value: object) -> tuple[int, int, int]:
    text = str(value).upper()
    y = re.search(r"FY\s*(\d{2})", text)
    q = re.search(r"Q([1-4])", text)
    return (int(y.group(1)) if y else -1, int(q.group(1)) if q else 5, 1 if "(A)" in text else 0)


def latest_row(data: pd.DataFrame) -> Optional[pd.Series]:
    if data.empty:
        return None
    temp = data.copy()
    temp["ValueNumeric"] = pd.to_numeric(temp["ValueNumeric"], errors="coerce")
    temp = temp.dropna(subset=["ValueNumeric"])
    if temp.empty:
        return None
    temp["_sort"] = temp["Year"].map(year_sort_key)
    return temp.sort_values(["_sort", "SourceCell"] if "SourceCell" in temp else ["_sort"], kind="stable").iloc[-1]


def find_metric(data: pd.DataFrame, alias_key: str) -> pd.DataFrame:
    if data.empty:
        return data.copy()
    aliases = {normalize_metric(x) for x in KPI_ALIASES.get(alias_key, [alias_key])}
    temp = data.copy()
    temp["_metric_normalized"] = temp["Metric"].map(normalize_metric)
    # Exact normalized match first, then a conservative contains fallback.
    matched = temp[temp["_metric_normalized"].isin(aliases)]
    if matched.empty:
        matched = temp[temp["_metric_normalized"].map(lambda m: any(a in m or m in a for a in aliases if len(a) >= 3))]
    return matched.copy()


def style_figure(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        font=dict(color=COLORS["text"], family="Inter, Segoe UI, Arial"),
        margin=dict(l=38, r=24, t=58, b=38), hoverlabel=dict(bgcolor="#142635", font_color="#FFFFFF"),
        xaxis=dict(showgrid=False, linecolor=COLORS["grid"]),
        yaxis=dict(gridcolor=COLORS["grid"], zeroline=False),
        title_font=dict(size=17),
    )
    return fig


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=.5, y=.5, showarrow=False, font=dict(color=COLORS["muted"], size=15))
    fig.update_xaxes(visible=False); fig.update_yaxes(visible=False)
    return style_figure(fig)


def plot_metric_trend(data: pd.DataFrame, alias_key: str, title: str) -> go.Figure:
    metric = find_metric(data, alias_key)
    metric["ValueNumeric"] = pd.to_numeric(metric.get("ValueNumeric"), errors="coerce")
    metric = metric.dropna(subset=["ValueNumeric"])
    if metric.empty:
        return empty_figure(f"No {title} data available")
    metric["_sort"] = metric["Year"].map(year_sort_key)
    metric = metric.sort_values("_sort", kind="stable")
    is_pct = metric["ValueKind"].astype(str).str.lower().eq("percentage").any()
    y = metric["ValueNumeric"] * (100 if is_pct else 1)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=metric["Year"], y=y, mode="lines+markers", fill="tozeroy",
        fillcolor="rgba(32,227,210,.08)", line=dict(color=COLORS["cyan"], width=3),
        marker=dict(size=8, color=COLORS["cyan"], line=dict(color="#032B31", width=2)),
        hovertemplate="%{x}<br><b>%{y:,.2f}" + ("%" if is_pct else "") + "</b><extra></extra>"))
    fig.update_layout(title=title, yaxis_ticksuffix="%" if is_pct else "")
    return style_figure(fig)


def plot_asset_quality(stage_values: dict[str, float]) -> go.Figure:
    clean = {k: v for k, v in stage_values.items() if v is not None and pd.notna(v)}
    if not clean:
        return empty_figure("Stage 1/2/3 data is not available")
    vals = np.array(list(clean.values()), dtype=float)
    if np.nanmax(np.abs(vals)) <= 1.5: vals *= 100
    fig = go.Figure(go.Pie(labels=list(clean), values=vals, hole=.68,
        marker=dict(colors=[COLORS["green"], COLORS["amber"], COLORS["red"]], line=dict(color=COLORS["surface"], width=3)),
        textinfo="label+percent", hovertemplate="%{label}<br><b>%{value:.2f}%</b><extra></extra>"))
    fig.update_layout(title="Asset Quality Mix", annotations=[dict(text="STAGES", x=.5, y=.5, showarrow=False, font=dict(size=14, color=COLORS["muted"]))])
    return style_figure(fig)


def plot_peer_heatmap(peer_data: pd.DataFrame, selected_company: str) -> go.Figure:
    if peer_data.empty: return empty_figure("No peer data available")
    metrics = [c for c in peer_data.columns if c != "Company"]
    raw = peer_data[metrics].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    scores = np.full_like(raw, np.nan)
    for j, metric in enumerate(metrics):
        rank = pd.Series(raw[:, j]).rank(pct=True).to_numpy()
        scores[:, j] = 1-rank if metric in LOWER_IS_BETTER else rank
    text = [["" if np.isnan(v) else f"{v:.2f}%" for v in row] for row in raw]
    labels = [f"● {c}" if c == selected_company else c for c in peer_data["Company"]]
    fig = go.Figure(go.Heatmap(z=scores, x=metrics, y=labels, text=text, texttemplate="%{text}",
        zmin=0, zmax=1, colorscale=[[0,"#6F2638"],[.5,"#7A5A20"],[1,"#126B4B"]],
        xgap=3, ygap=3, colorbar=dict(title="Peer score"), hovertemplate="%{y}<br>%{x}: %{text}<extra></extra>"))
    fig.update_layout(title="Latest Peer Comparison")
    return style_figure(fig, max(400, 42*len(peer_data)))
