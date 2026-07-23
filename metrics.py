"""KPI 計算ロジック。

- 応対記録ベースの KPI（解約率、継続応援成功率、VOC系）
- 月次レートベースの KPI（応答率・完了率の期間加重平均）
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from data_loader import (
    AGE_BUCKET_ORDER,
    AGE_GROUP_ORDER,
    BANSHAKU_CANCEL_SET,
    BANSHAKU_COURSE_CHANGE_SET,
    BANSHAKU_ORDER,
    BANSHAKU_RETENTION_SET,
    PREDEFINED_CANCEL_REASONS,
    REQUEST_MAIN_CATEGORIES,
    REQUEST_OTHER_LABEL,
    SUBSCRIPTION_ORDER,
    classify_free_cancel_reason,
    explode_multi,
)


class Kpi:
    """KPI 表示用の値持ちオブジェクト（Python 3.14 の dataclass 互換性問題を避けるため素のクラスで実装）。"""

    __slots__ = ("label", "value", "help", "ratio", "delta")

    def __init__(
        self,
        label: str,
        value: str,
        help: Optional[str] = None,
        ratio: Optional[float] = None,
        delta: Optional[str] = None,
    ) -> None:
        self.label = label
        self.value = value
        self.help = help
        self.ratio = ratio
        self.delta = delta


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


def other_cancel_reason_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """事前定義19カテゴリに含まれない解約理由（自由記述）をキーワード分類して集計。

    戻り値: columns = ['category', 'count', 'sample_texts']
      - category: キーワード分類ラベル（家族関係 / 認識違い・誤注文 / 期待違い ほか）
      - count:    そのカテゴリに落ちた自由記述の件数
      - sample_texts: 該当した自由記述のうち上位5件を "/" 連結で参考表示
    """
    empty = pd.DataFrame(columns=["category", "count", "sample_texts"])
    if df.empty:
        return empty
    canc = df[df["is_cancel"]]
    ex = explode_multi(canc, "cancel_reason")
    if ex.empty:
        return empty
    free = ex[~ex["cancel_reason"].isin(PREDEFINED_CANCEL_REASONS)].copy()
    if free.empty:
        return empty
    free["category"] = free["cancel_reason"].map(classify_free_cancel_reason)
    free = free[free["category"] != ""]
    if free.empty:
        return empty
    grp = free.groupby("category").agg(
        count=("cancel_reason", "size"),
        sample_texts=(
            "cancel_reason",
            lambda s: " / ".join(list(dict.fromkeys(s))[:5]),
        ),
    ).reset_index()
    return grp.sort_values("count", ascending=False).reset_index(drop=True)


def has_child_age_data(df: pd.DataFrame) -> bool:
    """Co-HeartCS 用: `child_age_bucket` 列に有効なデータがあるか。"""
    if df.empty or "child_age_bucket" not in df.columns:
        return False
    return bool((df["child_age_bucket"].fillna("") != "").any())


def _ordered_age_group_col(series: pd.Series) -> pd.Categorical:
    """学校区分列を規定順に並べる Categorical に変換。"""
    return pd.Categorical(series, categories=AGE_GROUP_ORDER, ordered=True)


def _ordered_age_label_col(series: pd.Series) -> pd.Categorical:
    """個別年齢ラベル列 ("0歳", "1歳", ..., "不明") を数値順に並べる Categorical。"""
    labels = series.dropna().unique().tolist()
    def _sort_key(v):
        if v == "不明" or not isinstance(v, str):
            return 999
        m = re.match(r"(\d{1,2})", v)
        return int(m.group(1)) if m else 999
    ordered = sorted(labels, key=_sort_key)
    return pd.Categorical(series, categories=ordered, ordered=True)


def _order_age_col(series: pd.Series, age_col: str) -> pd.Categorical:
    """age_col の種類に応じて適切な順序で Categorical 化。"""
    if age_col == "child_age_bucket":
        return _ordered_age_group_col(series)
    return _ordered_age_label_col(series)


def apply_age_group_filter(
    df: pd.DataFrame, groups: Optional[list[str]] = None
) -> pd.DataFrame:
    """学校区分（child_age_bucket）で絞り込む。空・None なら全件返す。"""
    if not groups or df.empty or "child_age_bucket" not in df.columns:
        return df
    return df[df["child_age_bucket"].isin(groups)].reset_index(drop=True)


def child_age_distribution(df: pd.DataFrame, age_col: str = "child_age_bucket") -> pd.DataFrame:
    """年齢 × 応対件数。age_col で個別年齢/学校区分を切替。

    戻り値: columns=[age, count]
    """
    if not has_child_age_data(df) or age_col not in df.columns:
        return pd.DataFrame(columns=["age", "count"])
    sub = df[df[age_col].fillna("") != ""].copy()
    if sub.empty:
        return pd.DataFrame(columns=["age", "count"])
    grp = sub[age_col].value_counts().reset_index()
    grp.columns = ["age", "count"]
    grp["age"] = _order_age_col(grp["age"], age_col)
    return grp.sort_values("age").reset_index(drop=True)


def child_age_cross(
    df: pd.DataFrame,
    group_col: str,
    *,
    age_col: str = "child_age_bucket",
    exploded: bool = False,
    top_n: Optional[int] = None,
    filter_cancel: bool = False,
) -> pd.DataFrame:
    """年齢（age_col）× 任意カラム のクロス集計。

    Args:
        group_col: グループ化する列名（request_category, product, course, cancel_reason ...）
        age_col:   'child_age_bucket'（学校区分）or 'child_age_label'（個別年齢）
        exploded:  複数選択セル（カンマ区切り）を展開してから集計するか
        top_n:     集計後に上位 N 個の group_col 値のみを残す
        filter_cancel: True なら is_cancel の行だけを対象にする
    戻り値: columns=[age, <group_col>, count]
    """
    empty = pd.DataFrame(columns=["age", group_col, "count"])
    if not has_child_age_data(df) or age_col not in df.columns:
        return empty
    sub = df[df[age_col].fillna("") != ""].copy()
    if filter_cancel:
        sub = sub[sub["is_cancel"]]
    if sub.empty:
        return empty
    if exploded:
        sub = explode_multi(sub, group_col)
    else:
        sub = sub[sub[group_col].fillna("") != ""]
    if sub.empty:
        return empty
    if top_n:
        top_vals = sub[group_col].value_counts().head(top_n).index.tolist()
        sub = sub[sub[group_col].isin(top_vals)]
    cross = (
        sub.groupby([age_col, group_col])
        .size().reset_index(name="count")
        .rename(columns={age_col: "age"})
    )
    cross["age"] = _order_age_col(cross["age"], age_col)
    return cross.sort_values(["age", "count"], ascending=[True, False]).reset_index(drop=True)


def child_age_summary(df: pd.DataFrame, age_col: str = "child_age_bucket") -> pd.DataFrame:
    """年齢別の総合サマリ（横断KPI表）。age_col で単位を選択。

    列: 年齢 / 応対件数 / 解約件数 / 解約率 / 継続応援成功率 /
        新規初回解約 / センターワード / 温度感上昇 / 嬉しい声
    """
    cols = [
        "年齢", "応対件数", "解約件数", "解約率", "継続応援成功率",
        "新規初回解約", "センターワード", "温度感上昇", "嬉しい声",
    ]
    empty = pd.DataFrame(columns=cols)
    if not has_child_age_data(df) or age_col not in df.columns:
        return empty
    sub = df[df[age_col].fillna("") != ""].copy()
    if sub.empty:
        return empty
    agg = sub.groupby(age_col).agg(
        応対件数=("timestamp", "size"),
        解約件数=("is_cancel", "sum"),
        新規初回解約=("is_first_time_cancel", "sum"),
        _reten_ok=("retention_success", "sum"),
        _reten_valid=("retention_valid", "sum"),
        センターワード=("voc_center_word", "sum"),
        温度感上昇=("is_escalation", "sum"),
        嬉しい声=("voc_positive", "sum"),
    ).reset_index().rename(columns={age_col: "年齢"})
    agg["解約率"] = agg["解約件数"] / agg["応対件数"]
    agg["継続応援成功率"] = agg.apply(
        lambda r: (r["_reten_ok"] / r["_reten_valid"]) if r["_reten_valid"] > 0 else None,
        axis=1,
    )
    agg = agg.drop(columns=["_reten_ok", "_reten_valid"])
    # 順序
    agg["年齢"] = _order_age_col(agg["年齢"], age_col)
    return agg.sort_values("年齢").reset_index(drop=True)[cols]


def child_age_retention(df: pd.DataFrame, age_col: str = "child_age_bucket") -> pd.DataFrame:
    """年齢別の継続応援成功率。age_col で単位切替。

    戻り値: columns=[age, success, total_valid, rate]
    """
    empty = pd.DataFrame(columns=["age", "success", "total_valid", "rate"])
    if not has_child_age_data(df) or age_col not in df.columns:
        return empty
    valid = df[(df[age_col].fillna("") != "") & df["retention_valid"]]
    if valid.empty:
        return empty
    grp = valid.groupby(age_col).agg(
        success=("retention_success", "sum"),
        total_valid=("retention_success", "size"),
    ).reset_index().rename(columns={age_col: "age"})
    grp["rate"] = grp["success"] / grp["total_valid"]
    grp["age"] = _order_age_col(grp["age"], age_col)
    return grp.sort_values("age").reset_index(drop=True)


def other_cancel_reason_raw(df: pd.DataFrame) -> pd.DataFrame:
    """事前定義外の自由記述解約理由の生一覧（監査用・全文表示）。

    戻り値: columns = ['text', 'count', 'classified']
    """
    empty = pd.DataFrame(columns=["text", "count", "classified"])
    if df.empty:
        return empty
    canc = df[df["is_cancel"]]
    ex = explode_multi(canc, "cancel_reason")
    if ex.empty:
        return empty
    free = ex[~ex["cancel_reason"].isin(PREDEFINED_CANCEL_REASONS)].copy()
    if free.empty:
        return empty
    counts = free["cancel_reason"].value_counts().reset_index()
    counts.columns = ["text", "count"]
    counts["classified"] = counts["text"].map(classify_free_cancel_reason)
    return counts


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

def detect_special_course_name(df: pd.DataFrame) -> str:
    """特別コース（晩酌応援 / すまいる応援）の実データ上の名称を自動検出。

    banshaku_category が入っている行のうち最も多い course 名を返す。
    データが無ければデフォルト表記を返す。
    """
    if df.empty or "banshaku_category" not in df.columns:
        return "対応内容"
    sub = df[df["banshaku_category"].fillna("") != ""]
    if sub.empty:
        return "対応内容"
    top = sub["course"].value_counts()
    return top.index[0] if len(top) else "対応内容"


def banshaku_scope(df: pd.DataFrame) -> pd.DataFrame:
    """特別コース（晩酌応援 / すまいる応援）の行だけ切り出す。

    course 名で絞らず、banshaku_category（対応内容分類）が入力されている行を対象にする。
    こうすることでブランドをまたいで自動対応できる。
    """
    if df.empty:
        return df
    return df[df["banshaku_category"].fillna("") != ""].copy()


def banshaku_kpis(df: pd.DataFrame) -> list[Kpi]:
    """特別コースの主要 KPI。ブランドに応じて表示ラベルを変える。"""
    ban = banshaku_scope(df)
    total = len(ban)
    course_name = detect_special_course_name(df)
    # 表示用の短縮ラベル（「◯◯応援コース」→「◯◯」）
    short = course_name.replace("応援コース", "").replace("コース", "") or course_name
    if total == 0:
        return [
            Kpi(f"{short} 応対件数", "0"),
            Kpi("継続了承・成功", "0"),
            Kpi("解約", "0"),
            Kpi("継続成功率", "—", help="対象データなし"),
        ]
    counts = ban["banshaku_category"].value_counts().to_dict()
    reten = sum(counts.get(c, 0) for c in BANSHAKU_RETENTION_SET)
    canc = sum(counts.get(c, 0) for c in BANSHAKU_CANCEL_SET)
    change = sum(counts.get(c, 0) for c in BANSHAKU_COURSE_CHANGE_SET)
    denom = reten + canc
    rate = safe_ratio(reten, denom)
    kpis = [
        Kpi(f"{short} 応対件数", _fmt_int(total)),
        Kpi(
            "継続了承・成功", _fmt_int(reten),
            help=" + ".join(sorted(BANSHAKU_RETENTION_SET)),
        ),
        Kpi(
            "解約", _fmt_int(canc),
            help=" + ".join(sorted(BANSHAKU_CANCEL_SET)),
        ),
        Kpi(
            "継続成功率", _fmt_pct(rate),
            help=f"継続 {reten} / (継続+解約 {denom})　※コース変更は分母から除外",
        ),
    ]
    # スマイル開始前コース変更が存在する場合のみ4枚目に追加
    if change > 0:
        kpis.append(
            Kpi(
                "スマイル開始前 コース変更", _fmt_int(change),
                help="スマイル開始前にコース変更した件数（継続・解約とは別カウント）",
            )
        )
    return kpis


def banshaku_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """特別コース対応内容のカテゴリ内訳（実データにあるカテゴリのみ表示）。"""
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
