"""Plotly ベースのグラフ生成。"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

GRANULARITY_LABEL = {"date": "日次", "week": "週次", "month": "月次"}


def _empty_fig(message: str = "データがありません") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False, font=dict(size=14, color="gray")
    )
    fig.update_layout(height=280, xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def trend_total_and_cancel(ts: pd.DataFrame, granularity: str) -> go.Figure:
    """応対件数と解約件数を重ねた折れ線グラフ。"""
    if ts.empty:
        return _empty_fig()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ts[granularity], y=ts["total"], mode="lines+markers",
            name="応対件数", line=dict(width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ts[granularity], y=ts["cancels"], mode="lines+markers",
            name="解約件数", line=dict(width=3, dash="dot"),
        )
    )
    fig.update_layout(
        title=f"応対件数・解約件数の推移（{GRANULARITY_LABEL[granularity]}）",
        xaxis_title="", yaxis_title="件数",
        height=360, hovermode="x unified", legend=dict(orientation="h", y=-0.2),
    )
    return fig


def trend_retention_rate(ts: pd.DataFrame, granularity: str) -> go.Figure:
    """継続応援 成功率の推移。"""
    if ts.empty or ts["retention_rate"].dropna().empty:
        return _empty_fig("有効な継続応援データがありません")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ts[granularity], y=ts["retention_rate"] * 100,
            mode="lines+markers", name="成功率", line=dict(width=3, color="#2e7d32"),
        )
    )
    fig.update_layout(
        title=f"継続応援 成功率の推移（{GRANULARITY_LABEL[granularity]}）",
        xaxis_title="", yaxis_title="成功率 (%)", yaxis=dict(range=[0, 100]),
        height=320, hovermode="x unified",
    )
    return fig


def trend_stacked_area(
    ts_by: pd.DataFrame, group_col: str, granularity: str, title: str
) -> go.Figure:
    """担当者別・コールセンター別の山型（積み上げ area）。"""
    if ts_by.empty:
        return _empty_fig()
    fig = px.area(
        ts_by, x=granularity, y="count", color=group_col,
        title=f"{title}（{GRANULARITY_LABEL[granularity]}）",
    )
    fig.update_layout(
        xaxis_title="", yaxis_title="件数", height=360,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def horizontal_bar(
    df: pd.DataFrame, x: str, y: str, title: str,
    color: str | None = None, text: str | None = None,
) -> go.Figure:
    if df.empty:
        return _empty_fig()
    fig = px.bar(
        df, x=x, y=y, orientation="h", title=title,
        text=text if text else x, color=color,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        height=max(320, 24 * len(df) + 120),
        xaxis_title="", yaxis_title="",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=40, t=60, b=40),
    )
    return fig


def vertical_bar(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    if df.empty:
        return _empty_fig()
    fig = px.bar(df, x=x, y=y, title=title, text=y)
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(height=340, xaxis_title="", yaxis_title="件数")
    return fig


def share_bar(df: pd.DataFrame, category_col: str, title: str) -> go.Figure:
    """% 表示の横棒（`share` 列を x 軸に、`category_col` を y 軸に）。"""
    if df.empty:
        return _empty_fig()
    fig = px.bar(
        df, x="share", y=category_col, orientation="h",
        text=[f"{s * 100:.1f}%" for s in df["share"]],
        title=title,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        height=max(320, 26 * len(df) + 120),
        xaxis=dict(tickformat=".0%", range=[0, min(1.0, df["share"].max() * 1.4)]),
        xaxis_title="占有率", yaxis_title="",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=10, r=80, t=60, b=40),
    )
    return fig


BANSHAKU_COLORS = {
    "満了解約": "#c62828",
    "差額あり途中解約": "#ef6c00",
    "差額なし途中解約": "#f9a825",
    "満了未満継続了承": "#2e7d32",
    "満了継続応援成功": "#1565c0",
    "その他": "#9e9e9e",
}


def banshaku_bar(df: pd.DataFrame) -> go.Figure:
    """晩酌応援コース 5 カテゴリ内訳（件数+%）。"""
    if df.empty:
        return _empty_fig("晩酌応援コースの対応内容がありません")
    fig = px.bar(
        df, x="category", y="count",
        color="category", color_discrete_map=BANSHAKU_COLORS,
        text=[f"{c}<br>{s * 100:.1f}%" for c, s in zip(df["count"], df["share"])],
        title="晩酌応援コース 対応内容の内訳",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        xaxis_title="", yaxis_title="件数", height=400,
        showlegend=False,
    )
    return fig


def rate_trend_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """応答率・完了率の日次推移（2 本折れ線）。"""
    if df.empty or df[["completion_rate", "response_rate"]].dropna(how="all").empty:
        return _empty_fig("期間内にレートデータがありません")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"], y=df["completion_rate"] * 100, mode="lines+markers",
            name="完了率", line=dict(width=3, color="#1976d2"),
            connectgaps=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"], y=df["response_rate"] * 100, mode="lines+markers",
            name="応答率", line=dict(width=3, color="#e65100"),
            connectgaps=False,
        )
    )
    fig.update_layout(
        title=title, xaxis_title="", yaxis_title="%",
        yaxis=dict(range=[0, 105]), height=360,
        hovermode="x unified", legend=dict(orientation="h", y=-0.2),
    )
    return fig


def rate_by_team_bar(df: pd.DataFrame) -> go.Figure:
    """チーム別 応答率・完了率の並列棒。"""
    if df.empty:
        return _empty_fig()
    long = df.melt(
        id_vars="team",
        value_vars=["completion_rate", "response_rate"],
        var_name="metric", value_name="rate",
    )
    long["metric"] = long["metric"].map(
        {"completion_rate": "完了率", "response_rate": "応答率"}
    )
    long["rate_pct"] = long["rate"] * 100
    fig = px.bar(
        long, x="team", y="rate_pct", color="metric", barmode="group",
        text=long["rate_pct"].round(1).astype(str) + "%",
        title="チーム別 完了率・応答率（期間加重平均）",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        yaxis=dict(range=[0, 110]), yaxis_title="%",
        xaxis_title="", height=360,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def rate_by_cc_bar(df: pd.DataFrame) -> go.Figure:
    """コールセンター別（LU/N2）の完了率・応答率。"""
    if df.empty:
        return _empty_fig()
    long = df.melt(
        id_vars="call_center",
        value_vars=["completion_rate", "response_rate"],
        var_name="metric", value_name="rate",
    )
    long["metric"] = long["metric"].map(
        {"completion_rate": "完了率", "response_rate": "応答率"}
    )
    long["rate_pct"] = long["rate"] * 100
    fig = px.bar(
        long, x="call_center", y="rate_pct", color="metric", barmode="group",
        text=long["rate_pct"].round(1).astype(str) + "%",
        title="コールセンター別 完了率・応答率（期間加重平均）",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(
        yaxis=dict(range=[0, 110]), yaxis_title="%",
        xaxis_title="", height=340,
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def retention_rate_bar(df: pd.DataFrame, group_col: str, title: str) -> go.Figure:
    """継続応援 成功率のブレークダウン棒（成功件数と成功率を併記）。"""
    if df.empty:
        return _empty_fig()
    label = df[group_col].astype(str)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=label, x=df["rate"] * 100, orientation="h",
            text=[
                f"{r * 100:.1f}%  ({s}/{t})"
                for r, s, t in zip(df["rate"], df["success"], df["total_valid"])
            ],
            textposition="outside", name="成功率",
            marker=dict(color="#1976d2"),
        )
    )
    fig.update_layout(
        title=title, xaxis_title="成功率 (%)", yaxis_title="",
        xaxis=dict(range=[0, max(df["rate"].max() * 100 * 1.4, 20)]),
        yaxis=dict(autorange="reversed"),
        height=max(320, 28 * len(df) + 120),
        margin=dict(l=10, r=80, t=60, b=40),
    )
    return fig
