"""KPI 計算ロジック。

- 応対記録ベースの KPI（解約率、継続応援成功率、VOC系）
- 月次レートベースの KPI（応答率・完了率の期間加重平均）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from data_loader import (
    BANSHAKU_ORDER,
    REQUEST_MAIN_CATEGORIES,
    REQUEST_OTHER_LABEL,
    SUBSCRIPTION_ORDER,
    explode_multi,
)


@dataclass
class Kpi:
    label: str
    value: str
    help: Optional[str] = None
    ratio: Optional[float] = None
    delta: Optional[str] = None


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_pct(x: Optional[float]) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x * 100:.1f}%"


def safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator == 0:
        return None
    return numerator / denominator


# ─────────────────────────────────────────────
# 応対記録ベース KPI
# ─────────────────────────────────────────────

def basic_kpis(df: pd.DataFrame, prev_df: Optional[pd.DataFrame] = None) -> list[Kpi]:
    total = len(df)
    cancels = int(df["is_cancel"].sum())
    cancel_rate = safe_ratio(cancels, total)
    first_time = int(df["is_first_time_cancel"].sum())

    def delta_int(cur: int, key: str) -> Optional[str]:
        if prev_df is None:
            return None
        prev_val = int(prev_df[key].sum()) if key in prev_df.columns else 0
        return f"{cur - prev_val:+,}"

    def delta_len(cur: int) -> Optional[str]:
        if prev_df is None:
            return None
        return f"{cur - len(prev_df):+,}"

    return [
        Kpi("総応対件数", _fmt_int(total), delta=delta_len(total)),
        Kpi("解約件数", _fmt_int(cancels), delta=delta_int(cancels, "is_cancel")),
        Kpi("解約率", _fmt_pct(cancel_rate), help="解約件数 / 総応対件数"),
        Kpi(
            "新規初回解約", _fmt_int(first_time),
            help="定期回数=初回 かつ 解約希望の件数",
            delta=delta_int(first_time, "is_first_time_cancel"),
        ),
    ]


def retention_kpi(df: pd.DataFrame) -> Kpi:
    valid = df[df["retention_valid"]]
    success = int(valid["retention_success"].sum())
    rate = safe_ratio(success, len(valid))
    return Kpi(
        "継続応援 成功率", _fmt_pct(rate),
        help=f"成功 {success} 件 / 有効応対 {len(valid)} 件（未案内は分母から除外）",
    )


def center_kpis(df: pd.DataFrame) -> list[Kpi]:
    total = max(len(df), 1)
    entries = [
        ("センターワードあり", int(df["voc_center_word"].sum()), "VOC='消費者センターワードあり'"),
        ("センター職員入電", int(df["voc_center_staff"].sum()), "VOC='消費者センター職員からの入電'"),
        ("消費者庁", int(df["voc_shohisho"].sum()), "VOC に '消費者庁' を含む（現状データにはなし・将来向け）"),
        ("温度感上昇", int(df["is_escalation"].sum()), "温度感が上がってしまった原因が入力された行"),
        ("嬉しい声", int(df["voc_positive"].sum()), "VOC='嬉しいお声'"),
    ]
    return [
        Kpi(label, _fmt_int(count), help=h, ratio=count / total)
        for label, count, h in entries
    ]


def retention_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    valid = df[df["retention_valid"]].copy()
    if valid.empty:
        return pd.DataFrame(columns=[column, "success", "fail", "total_valid", "rate"])
    valid[column] = valid[column].replace("", "（未入力）").fillna("（未入力）")
    grp = valid.groupby(column, dropna=False).agg(
        success=("retention_success", "sum"),
        total_valid=("retention_success", "size"),
    )
    grp["fail"] = grp["total_valid"] - grp["success"]
    grp["rate"] = grp["success"] / grp["total_valid"]
    grp = grp.reset_index()
    if column == "subscription_count":
        grp[column] = pd.Categorical(
            grp[column], categories=SUBSCRIPTION_ORDER + ["（未入力）"], ordered=True
        )
        grp = grp.sort_values(column)
    else:
        grp = grp.sort_values("total_valid", ascending=False)
    return grp.reset_index(drop=True)


def retention_by_reason(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["retention_valid"]]
    if valid.empty:
        return pd.DataFrame(columns=["cancel_reason", "success", "fail", "total_valid", "rate"])
    exploded = explode_multi(valid, "cancel_reason")
    grp = exploded.groupby("cancel_reason").agg(
        success=("retention_success", "sum"),
        total_valid=("retention_success", "size"),
    )
    grp["fail"] = grp["total_valid"] - grp["success"]
    grp["rate"] = grp["success"] / grp["total_valid"]
    grp = grp.reset_index().sort_values("total_valid", ascending=False)
    return grp.reset_index(drop=True)


def request_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    ex = explode_multi(df, "request")
    if ex.empty:
        return pd.DataFrame(columns=["request", "count"])
    grp = ex.groupby("request").size().reset_index(name="count")
    return grp.sort_values("count", ascending=False).reset_index(drop=True)


def request_share(df: pd.DataFrame) -> pd.DataFrame:
    """問い合わせ内容カテゴリの % 表示用。主要12カテゴリ + その他 に集約。

    戻り値: columns = ['category', 'count', 'share']
    """
    if df.empty or "request_category" not in df.columns:
        return pd.DataFrame(columns=["category", "count", "share"])
    sub = df[df["request_category"] != ""].copy()
    grp = (
        sub.groupby("request_category").size().reset_index(name="count")
        .rename(columns={"request_category": "category"})
    )
    total = grp["count"].sum() or 1
    grp["share"] = grp["count"] / total
    order = REQUEST_MAIN_CATEGORIES + [REQUEST_OTHER_LABEL]
    grp["_ord"] = grp["category"].map({c: i for i, c in enumerate(order)}).fillna(999)
    grp = grp.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)
    return grp


def cancel_by_subscription(df: pd.DataFrame) -> pd.DataFrame:
    canc = df[df["is_cancel"]].copy()
    if canc.empty:
        return pd.DataFrame(columns=["subscription_count", "count"])
    canc["subscription_count"] = canc["subscription_count"].replace("", "（未入力）")
    grp = canc.groupby("subscription_count").size().reset_index(name="count")
    grp["subscription_count"] = pd.Categorical(
        grp["subscription_count"],
        categories=SUBSCRIPTION_ORDER + ["（未入力）"], ordered=True,
    )
    return grp.sort_values("subscription_count").reset_index(drop=True)


def product_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    ex = explode_multi(df, "product")
    if ex.empty:
        return pd.DataFrame(columns=["product", "count"])
    grp = ex.groupby("product").size().reset_index(name="count")
    return grp.sort_values("count", ascending=False).reset_index(drop=True)


def cancel_reason_top(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    canc = df[df["is_cancel"]]
    ex = explode_multi(canc, "cancel_reason")
    if ex.empty:
        return pd.DataFrame(columns=["cancel_reason", "count"])
    grp = ex.groupby("cancel_reason").size().reset_index(name="count")
    return grp.sort_values("count", ascending=False).head(top_n).reset_index(drop=True)


def center_breakdown(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    center = df[df["voc_center_word"] | df["voc_center_staff"]].copy()
    if center.empty:
        return pd.DataFrame(columns=[group_col, "count"])
    if group_col == "cancel_reason":
        ex = explode_multi(center, "cancel_reason")
        grp = ex.groupby("cancel_reason").size().reset_index(name="count")
    else:
        center[group_col] = center[group_col].replace("", "（未入力）")
        grp = center.groupby(group_col).size().reset_index(name="count")
        if group_col == "subscription_count":
            grp[group_col] = pd.Categorical(
                grp[group_col],
                categories=SUBSCRIPTION_ORDER + ["（未入力）"], ordered=True,
            )
            return grp.sort_values(group_col).reset_index(drop=True)
    return grp.sort_values("count", ascending=False).reset_index(drop=True)


def time_series(df: pd.DataFrame, granularity: str = "date") -> pd.DataFrame:
    if granularity not in ("date", "week", "month"):
        raise ValueError(granularity)
    if df.empty:
        return pd.DataFrame(columns=[granularity, "total", "cancels", "retention_rate"])
    grp = df.groupby(granularity, as_index=False).agg(
        total=("timestamp", "size"),
        cancels=("is_cancel", "sum"),
        retention_valid=("retention_valid", "sum"),
        retention_success=("retention_success", "sum"),
    )
    grp["retention_rate"] = grp.apply(
        lambda r: (r["retention_success"] / r["retention_valid"])
        if r["retention_valid"] > 0 else None,
        axis=1,
    )
    return grp.sort_values(granularity).reset_index(drop=True)


def time_series_by(
    df: pd.DataFrame, group_col: str, granularity: str = "date"
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[granularity, group_col, "count"])
    grp = (
        df.groupby([granularity, group_col], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    return grp.sort_values(granularity).reset_index(drop=True)


def compare_by(
    ops_df: pd.DataFrame,
    rates_df: pd.DataFrame,
    group_col: str,
) -> pd.DataFrame:
    """コールセンター or オペレーターごとの比較表。

    列: 対象, 応対件数, 解約件数, 解約率, 新規初回解約, 継続応援成功率,
        センターワード, センター職員, 完了率, 応答率
    完了率・応答率は rates_df から取得（オペレーター単位ではデータがないため NaN）。
    """
    if ops_df.empty:
        return pd.DataFrame()
    agg = ops_df.groupby(group_col).agg(
        応対件数=("timestamp", "size"),
        解約件数=("is_cancel", "sum"),
        新規初回解約=("is_first_time_cancel", "sum"),
        _reten_ok=("retention_success", "sum"),
        _reten_valid=("retention_valid", "sum"),
        センターワード=("voc_center_word", "sum"),
        センター職員=("voc_center_staff", "sum"),
    ).reset_index()
    agg["解約率"] = agg["解約件数"] / agg["応対件数"]
    agg["継続応援成功率"] = agg.apply(
        lambda r: (r["_reten_ok"] / r["_reten_valid"]) if r["_reten_valid"] > 0 else None,
        axis=1,
    )
    agg = agg.drop(columns=["_reten_ok", "_reten_valid"])

    # レートはコールセンター単位でのみ結合
    if group_col == "call_center" and not rates_df.empty:
        r_all = rates_df[rates_df["team"] == "全体"].groupby("call_center").agg(
            _tot=("total_dispatch", "sum"),
            _cmp=("completion_count", "sum"),
            _inc=("incoming_count", "sum"),
            _rsp=("response_count", "sum"),
        )
        r_all["完了率"] = r_all["_cmp"] / r_all["_tot"]
        r_all["応答率"] = r_all["_rsp"] / r_all["_inc"]
        agg = agg.merge(
            r_all[["完了率", "応答率"]].reset_index(),
            on="call_center", how="left",
        )

    agg = agg.rename(columns={group_col: "対象"})
    return agg.sort_values("応対件数", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────
# 晩酌応援コース
# ─────────────────────────────────────────────

def banshaku_scope(df: pd.DataFrame) -> pd.DataFrame:
    """晩酌応援コースの行だけ切り出す。"""
    if df.empty:
        return df
    return df[df["course"] == "晩酌応援コース"].copy()


def banshaku_kpis(df: pd.DataFrame) -> list[Kpi]:
    ban = banshaku_scope(df)
    total = len(ban)
    if total == 0:
        return [
            Kpi("晩酌 応対件数", "0"),
            Kpi("継続了承・成功", "0"),
            Kpi("解約 (満了・途中)", "0"),
            Kpi("継続成功率", "—", help="対象データなし"),
        ]
    counts = ban["banshaku_category"].value_counts().to_dict()
    reten = sum(counts.get(c, 0) for c in ("満了未満継続了承", "満了継続応援成功"))
    canc = sum(counts.get(c, 0) for c in ("満了解約", "差額あり途中解約", "差額なし途中解約"))
    denom = reten + canc
    rate = safe_ratio(reten, denom)
    return [
        Kpi("晩酌 応対件数", _fmt_int(total)),
        Kpi(
            "継続了承・成功", _fmt_int(reten),
            help="満了未満継続了承 + 満了継続応援成功",
        ),
        Kpi(
            "解約 (満了・途中)", _fmt_int(canc),
            help="満了解約 + 差額あり途中解約 + 差額なし途中解約",
        ),
        Kpi(
            "継続成功率", _fmt_pct(rate),
            help=f"継続 {reten} / (継続+解約 {denom})",
        ),
    ]


def banshaku_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """晩酌応援コース対応内容の 5 カテゴリ内訳。"""
    ban = banshaku_scope(df)
    ban = ban[ban["banshaku_category"] != ""]
    if ban.empty:
        return pd.DataFrame(columns=["category", "count", "share"])
    grp = ban.groupby("banshaku_category").size().reset_index(name="count")
    total = grp["count"].sum() or 1
    grp["share"] = grp["count"] / total
    grp = grp.rename(columns={"banshaku_category": "category"})
    grp["_o"] = grp["category"].map({c: i for i, c in enumerate(BANSHAKU_ORDER + [REQUEST_OTHER_LABEL])}).fillna(999)
    return grp.sort_values("_o").drop(columns="_o").reset_index(drop=True)


# ─────────────────────────────────────────────
# 嬉しい声ハイライト
# ─────────────────────────────────────────────

def positive_highlights(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    """最新の嬉しい声 N 件（本文入り）を返す。"""
    if df.empty or "note_positive" not in df.columns:
        return pd.DataFrame(columns=["timestamp", "call_center", "agent", "note_positive", "positive_kind"])
    sub = df[df["note_positive"].fillna("").str.strip() != ""].copy()
    return (
        sub[["timestamp", "call_center", "agent", "note_positive", "positive_kind"]]
        .sort_values("timestamp", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )


def free_text_records(
    df: pd.DataFrame, kind: str, keyword: str = ""
) -> pd.DataFrame:
    assert kind in ("negative", "positive")
    if kind == "negative":
        text_col = "note_negative"
        extra_cols = ["escalation_cause"]
    else:
        text_col = "note_positive"
        extra_cols = ["positive_kind"]
    sub = df[df[text_col].fillna("").str.strip() != ""].copy()
    if keyword:
        sub = sub[sub[text_col].str.contains(keyword, na=False, case=False)]
    cols = [
        "timestamp", "call_center", "agent", "product", "course",
        "subscription_count", text_col,
    ] + extra_cols
    return sub[cols].sort_values("timestamp", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────
# 月次レート KPI（応答率・完了率）
# ─────────────────────────────────────────────

def _weighted_rate(numer_col: str, denom_col: str, df: pd.DataFrame) -> Optional[float]:
    if df.empty:
        return None
    n = df[numer_col].sum(skipna=True)
    d = df[denom_col].sum(skipna=True)
    if not d or pd.isna(d):
        return None
    return float(n) / float(d)


def rate_kpis(rates: pd.DataFrame, team: str = "全体") -> list[Kpi]:
    """期間内のレート KPI（team ごとに算出）。

    - 完了率 = SUM(完了数) / SUM(総発数)
    - ユニーク完了率 = SUM(ユニーク完了数) / SUM(ユニーク総発数)   ※ 全体チームのみ
    - 応答率 = SUM(応答数) / SUM(入電数)
    """
    df = rates[rates["team"] == team]
    if df.empty:
        return [
            Kpi("完了率", "—", help=f"{team}：期間内にデータなし"),
            Kpi("ユニーク完了率", "—", help=f"{team}：期間内にデータなし"),
            Kpi("応答率", "—", help=f"{team}：期間内にデータなし"),
            Kpi("総発数", "0"),
            Kpi("入電数", "0"),
        ]
    comp = _weighted_rate("completion_count", "total_dispatch", df)
    resp = _weighted_rate("response_count", "incoming_count", df)
    uniq_comp = (
        _weighted_rate("unique_completion_count", "unique_total_dispatch", df)
        if "unique_completion_count" in df.columns else None
    )
    total_dispatch = int(df["total_dispatch"].sum(skipna=True) or 0)
    incoming = int(df["incoming_count"].sum(skipna=True) or 0)
    return [
        Kpi("完了率", _fmt_pct(comp), help=f"{team}：完了数合計 / 総発数合計"),
        Kpi(
            "ユニーク完了率", _fmt_pct(uniq_comp),
            help=(
                f"{team}：ユニーク完了数 / ユニーク総発数"
                + ("（このチームはデータなし）" if uniq_comp is None and team != "全体" else "")
            ),
        ),
        Kpi("応答率", _fmt_pct(resp), help=f"{team}：応答数合計 / 入電数合計"),
        Kpi("総発数", _fmt_int(total_dispatch), help=f"{team}：期間合計"),
        Kpi("入電数", _fmt_int(incoming), help=f"{team}：期間合計"),
    ]


def rate_trend(rates: pd.DataFrame, team: str = "全体") -> pd.DataFrame:
    """日次の 応答率 / 完了率 推移。"""
    df = rates[rates["team"] == team]
    if df.empty:
        return pd.DataFrame(columns=["date", "completion_rate", "response_rate"])
    grp = df.groupby("date", as_index=False).agg(
        completion_rate=("completion_rate", "mean"),
        response_rate=("response_rate", "mean"),
        total_dispatch=("total_dispatch", "sum"),
        incoming_count=("incoming_count", "sum"),
    )
    return grp.sort_values("date").reset_index(drop=True)


def rate_by_team(rates: pd.DataFrame) -> pd.DataFrame:
    """チーム別（専任 / クロコスマルチ / 全体）の期間集計。"""
    if rates.empty:
        return pd.DataFrame(columns=["team", "completion_rate", "response_rate", "total_dispatch", "incoming_count"])
    records = []
    for team, sub in rates.groupby("team"):
        records.append(
            {
                "team": team,
                "completion_rate": _weighted_rate("completion_count", "total_dispatch", sub),
                "response_rate": _weighted_rate("response_count", "incoming_count", sub),
                "total_dispatch": int(sub["total_dispatch"].sum(skipna=True) or 0),
                "incoming_count": int(sub["incoming_count"].sum(skipna=True) or 0),
            }
        )
    out = pd.DataFrame.from_records(records)
    order = {"専任": 0, "クロコスマルチ": 1, "全体": 2}
    out["_o"] = out["team"].map(order).fillna(99)
    return out.sort_values("_o").drop(columns="_o").reset_index(drop=True)


def rate_trend_last_days(rates: pd.DataFrame, team: str = "全体", days: int = 30) -> pd.DataFrame:
    """レート推移を「直近 N 日」で切って返す。サイドバー期間フィルタとは独立に使う。

    「実データがある最新日」（total_dispatch > 0 の中で最大）から days 日前まで。
    月次タブは未来日の空行を含むが、それらは除外する。
    """
    df = rates[rates["team"] == team]
    if df.empty:
        return pd.DataFrame(columns=["date", "completion_rate", "response_rate"])
    active = df[df["total_dispatch"].fillna(0) > 0]
    if active.empty:
        return pd.DataFrame(columns=["date", "completion_rate", "response_rate"])
    latest = active["date"].max()
    cutoff = latest - pd.Timedelta(days=days - 1)
    sub = df[(df["date"] >= cutoff) & (df["date"] <= latest)]
    return rate_trend(sub, team=team)


def rate_by_call_center(rates: pd.DataFrame, team: str = "全体") -> pd.DataFrame:
    """コールセンター別（LU/N2）の期間集計。"""
    df = rates[rates["team"] == team]
    if df.empty:
        return pd.DataFrame(columns=["call_center", "completion_rate", "response_rate", "total_dispatch", "incoming_count"])
    records = []
    for cc, sub in df.groupby("call_center"):
        records.append(
            {
                "call_center": cc,
                "completion_rate": _weighted_rate("completion_count", "total_dispatch", sub),
                "response_rate": _weighted_rate("response_count", "incoming_count", sub),
                "total_dispatch": int(sub["total_dispatch"].sum(skipna=True) or 0),
                "incoming_count": int(sub["incoming_count"].sum(skipna=True) or 0),
            }
        )
    return pd.DataFrame.from_records(records)
