"""社内ダッシュボード（LU / N2 応対＋発信レート可視化）。

セクション:
1. 基本 KPI（応対 / 解約 / 解約率 / 新規初回解約）
2. 継続応援・センター系 KPI + 嬉しい声ハイライト
3. 🆚 コールセンター / オペレーター 比較
4. 📞 発信・応答レート（完了率 / ユニーク完了率 / 応答率、直近30日推移、チーム比較、CC比較）
5. 📈 応対・解約・継続応援 の推移（サイドバーの粒度・期間に従う）
6. 📊 内訳（問い合わせ内容 % / 定期回数×解約 / 商品 / 解約理由 TOP15）
7. 🎯 継続応援 成功率の内訳（コース / 定期回数 / 解約理由 / CC / オペレーター）
8. 🌙 晩酌応援コース 内訳
9. ⚠️ センター系 件数の内訳
10. 💬 自由記述（ネガ / ポジ）＋キーワード検索
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
import metrics
from data_loader import (
    REQUEST_MAIN_CATEGORIES,
    REQUEST_OTHER_LABEL,
    SHEETS,
    SUBSCRIPTION_ORDER,
    TEAMS,
    apply_ops_filters,
    apply_rate_filters,
    explode_multi,
    load_brand_name,
    load_data,
    load_theme_name,
    previous_period,
)

BRAND = load_brand_name()
DASHBOARD_TITLE = f"{BRAND}ダッシュボード"

# ─────────────────────────────────────────────
# テーマパレット（Secrets で "gold" or "green" を指定）
# ─────────────────────────────────────────────
THEME_PALETTES: dict[str, dict[str, str]] = {
    "gold": {
        "h1_text": "#7a4f00",
        "h1_grad_start": "#fff2b3",
        "h1_grad_end": "#fffbe6",
        "h1_border": "#e0a800",
        "h3_text": "#5d3f00",
        "h3_border": "rgba(224, 168, 0, 0.35)",
        "metric_border": "rgba(224, 168, 0, 0.15)",
        "metric_hover": "rgba(224, 168, 0, 0.15)",
        "sidebar_bg": "#fff5d1",
        "sidebar_border": "rgba(224, 168, 0, 0.15)",
        "sidebar_h3": "#5d3f00",
        "sidebar_h3_border": "rgba(224, 168, 0, 0.3)",
        "hr_border": "rgba(224, 168, 0, 0.4)",
        "tab_active": "#b8860b",
        "tab_highlight": "#e0a800",
        "df_border": "rgba(224, 168, 0, 0.15)",
        "expander_bg": "rgba(255, 245, 209, 0.5)",
        "caption": "#8a6b1a",
    },
    "green": {
        "h1_text": "#1b5e20",
        "h1_grad_start": "#c5e1a5",
        "h1_grad_end": "#f1f8e9",
        "h1_border": "#7cb342",
        "h3_text": "#2e7d32",
        "h3_border": "rgba(124, 179, 66, 0.4)",
        "metric_border": "rgba(124, 179, 66, 0.2)",
        "metric_hover": "rgba(124, 179, 66, 0.2)",
        "sidebar_bg": "#e8f5e9",
        "sidebar_border": "rgba(124, 179, 66, 0.2)",
        "sidebar_h3": "#2e7d32",
        "sidebar_h3_border": "rgba(124, 179, 66, 0.35)",
        "hr_border": "rgba(124, 179, 66, 0.45)",
        "tab_active": "#558b2f",
        "tab_highlight": "#7cb342",
        "df_border": "rgba(124, 179, 66, 0.2)",
        "expander_bg": "rgba(220, 237, 200, 0.5)",
        "caption": "#33691e",
    },
}
_theme_name = load_theme_name()
T = THEME_PALETTES.get(_theme_name, THEME_PALETTES["gold"])

st.set_page_config(
    page_title=DASHBOARD_TITLE, page_icon="📊", layout="wide",
)

# ─────────────────────────────────────────────
# カスタム CSS（デザイン仕上げ）
# ─────────────────────────────────────────────
st.markdown(
    f"""
<style>
/* 全体フォント */
html, body, [class*="css"] {{
    font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                 "Yu Gothic", "Meiryo", sans-serif;
}}

/* h1 のアクセント帯 */
.stApp h1 {{
    color: {T["h1_text"]};
    letter-spacing: 0.02em;
    padding: 12px 20px;
    background: linear-gradient(90deg, {T["h1_grad_start"]} 0%, {T["h1_grad_end"]} 100%);
    border-left: 6px solid {T["h1_border"]};
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}}

/* セクション見出し h3 */
.stApp h3 {{
    color: {T["h3_text"]};
    margin-top: 28px !important;
    margin-bottom: 12px !important;
    padding: 4px 0 8px 0 !important;
    border-bottom: 2px solid {T["h3_border"]} !important;
}}

/* KPI カード */
div[data-testid="stMetric"] {{
    background-color: rgba(255, 255, 255, 0.7);
    padding: 14px 18px;
    border-radius: 12px;
    border: 1px solid {T["metric_border"]};
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.15s ease-in-out, transform 0.15s;
}}
div[data-testid="stMetric"]:hover {{
    box-shadow: 0 4px 10px {T["metric_hover"]};
    transform: translateY(-1px);
}}

/* サイドバー */
section[data-testid="stSidebar"] {{
    background-color: {T["sidebar_bg"]} !important;
    border-right: 1px solid {T["sidebar_border"]};
}}
section[data-testid="stSidebar"] h3 {{
    color: {T["sidebar_h3"]} !important;
    border-bottom: 1px solid {T["sidebar_h3_border"]} !important;
}}

/* 区切り線 hr */
hr {{
    border: none !important;
    border-top: 1px dashed {T["hr_border"]} !important;
    margin: 24px 0 !important;
}}

/* Tab のアクティブラベル */
button[data-baseweb="tab"] {{
    font-weight: 500;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    color: {T["tab_active"]} !important;
}}
div[data-baseweb="tab-highlight"] {{
    background-color: {T["tab_highlight"]} !important;
}}

/* データフレームの罫線 */
div[data-testid="stDataFrame"] {{
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid {T["df_border"]};
}}

/* Expander */
details summary {{
    background-color: {T["expander_bg"]} !important;
    border-radius: 6px !important;
}}

/* Caption */
.stCaption, div[data-testid="stCaptionContainer"] {{
    color: {T["caption"]} !important;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ※ パスワード保護は無効化しています（URL を知っている人のみアクセス）。
#    復活させたい場合は auth.py の require_password() を再度呼び出してください。

# ─────────────────────────────────────────────
# データ取得
# ─────────────────────────────────────────────
result = load_data()
ops_all = result.ops
rates_all = result.rates

# ─────────────────────────────────────────────
# サイドバー
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔄 データ")
    st.caption(f"最終取得: {result.loaded_at.strftime('%Y-%m-%d %H:%M:%S')} (JST)")
    st.caption(
        f"応対記録: {len(ops_all):,} 件 ／ "
        f"月次レコード: {len(rates_all):,} 行"
    )
    for cc, tabs in result.monthly_tabs.items():
        if tabs:
            st.caption(f"{cc} 月次タブ: {', '.join(tabs)}")
    if st.button("最新データに更新", use_container_width=True):
        load_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("### 🔍 フィルタ")

    # コールセンター
    cc_options = list(SHEETS.keys())
    call_centers = st.multiselect(
        "コールセンター", cc_options, default=cc_options,
    )

    # 期間
    if not ops_all.empty:
        min_date = ops_all["date"].min().date()
        max_date = ops_all["date"].max().date()
    else:
        today = pd.Timestamp.today().date()
        min_date = max_date = today

    preset = st.selectbox(
        "期間プリセット",
        ["全期間", "直近7日", "直近30日", "今月", "先月", "カスタム"],
        index=0,
    )
    if preset == "全期間":
        date_from, date_to = min_date, max_date
    elif preset == "直近7日":
        date_to = max_date
        date_from = max(min_date, (pd.Timestamp(max_date) - pd.Timedelta(days=6)).date())
    elif preset == "直近30日":
        date_to = max_date
        date_from = max(min_date, (pd.Timestamp(max_date) - pd.Timedelta(days=29)).date())
    elif preset == "今月":
        cur_month_start = pd.Timestamp(max_date).replace(day=1).date()
        date_from = max(min_date, cur_month_start)
        date_to = max_date
    elif preset == "先月":
        cur_month_start = pd.Timestamp(max_date).replace(day=1)
        last_month_end = (cur_month_start - pd.Timedelta(days=1)).date()
        last_month_start = pd.Timestamp(last_month_end).replace(day=1).date()
        date_from = max(min_date, last_month_start)
        date_to = min(max_date, last_month_end)
    else:
        rng = st.date_input(
            "期間（開始・終了）", value=(min_date, max_date),
            min_value=min_date, max_value=max_date,
        )
        if isinstance(rng, tuple) and len(rng) == 2:
            date_from, date_to = rng
        else:
            date_from, date_to = min_date, max_date

    granularity = st.radio(
        "推移の粒度", options=["date", "week", "month"],
        format_func=lambda x: charts.GRANULARITY_LABEL[x],
        horizontal=True, index=0,
    )

    agents_opt = sorted(ops_all["agent"].dropna().unique().tolist()) if not ops_all.empty else []
    products_opt = sorted(
        [p for p in ops_all["product"].fillna("").unique() if p]
    ) if not ops_all.empty else []
    courses_opt = sorted([c for c in ops_all["course"].unique() if c]) if not ops_all.empty else []
    # 問い合わせ内容カテゴリ（丸め済み）
    if not ops_all.empty:
        cats_available = set(ops_all["request_category"].unique()) - {""}
        request_options = [c for c in REQUEST_MAIN_CATEGORIES if c in cats_available]
        if REQUEST_OTHER_LABEL in cats_available:
            request_options.append(REQUEST_OTHER_LABEL)
    else:
        request_options = []
    subs_opt = (
        [s for s in SUBSCRIPTION_ORDER if s in ops_all["subscription_count"].unique()]
        if not ops_all.empty else []
    )

    agents = st.multiselect("担当者", agents_opt)
    products = st.multiselect("商品", products_opt)
    courses = st.multiselect("コース", courses_opt)
    requests_sel = st.multiselect(
        "問い合わせ内容", request_options,
        help="月次シート 4 行目の主要カテゴリ ＋ 未該当は「その他」に集約",
    )
    subs = st.multiselect("定期回数", subs_opt)

    show_prev = st.checkbox("前期比を表示", value=True)

# ─────────────────────────────────────────────
# フィルタ適用
# ─────────────────────────────────────────────
fdf = apply_ops_filters(
    ops_all,
    date_from=pd.Timestamp(date_from), date_to=pd.Timestamp(date_to),
    call_centers=call_centers or None,
    agents=agents or None, products=products or None,
    courses=courses or None, requests=requests_sel or None,
    subscription_counts=subs or None,
)

frates = apply_rate_filters(
    rates_all,
    date_from=pd.Timestamp(date_from), date_to=pd.Timestamp(date_to),
    call_centers=call_centers or None,
)

# レート推移は「サイドバー期間フィルタに介さず、常に直近30日」用のデータも保持
rates_last30_scope = rates_all[
    rates_all["call_center"].isin(call_centers)
] if call_centers else rates_all

prev_df: pd.DataFrame | None = None
prev_from = prev_to = None
if show_prev:
    prev_from, prev_to = previous_period(pd.Timestamp(date_from), pd.Timestamp(date_to))
    prev_df = apply_ops_filters(
        ops_all,
        date_from=prev_from, date_to=prev_to,
        call_centers=call_centers or None,
        agents=agents or None, products=products or None,
        courses=courses or None, requests=requests_sel or None,
        subscription_counts=subs or None,
    )

# ─────────────────────────────────────────────
# ヘッダ
# ─────────────────────────────────────────────
st.title(f"📊 {DASHBOARD_TITLE}")
st.caption(
    f"期間: {date_from} 〜 {date_to} ／ 対象 {len(fdf):,} 件 ／ "
    f"コールセンター: {', '.join(call_centers) if call_centers else '（未選択）'}"
    + (
        f" ／ 前期({prev_from.date()} 〜 {prev_to.date()}): {len(prev_df):,} 件"
        if prev_df is not None else ""
    )
)

if not call_centers:
    st.warning("コールセンターを 1 つ以上選択してください。")
    st.stop()

if fdf.empty:
    st.warning("この条件に一致する応対記録がありません。フィルタを見直してください。")

# ─────────────────────────────────────────────
# 基本 KPI
# ─────────────────────────────────────────────
if not fdf.empty:
    st.markdown("### 基本 KPI")
    basic = metrics.basic_kpis(fdf, prev_df=prev_df)
    cols = st.columns(len(basic))
    for c, k in zip(cols, basic):
        c.metric(k.label, k.value, delta=k.delta, help=k.help)

    st.markdown("### 継続応援・センター系 KPI")
    reten_kpi = metrics.retention_kpi(fdf)
    center = metrics.center_kpis(fdf)
    kpi_row = [reten_kpi] + center
    cols = st.columns(len(kpi_row))
    for c, k in zip(cols, kpi_row):
        with c:
            st.metric(k.label, k.value, help=k.help)
            if k.ratio is not None:
                st.caption(f"全体の {k.ratio * 100:.1f}%")

    st.markdown("---")

# ─────────────────────────────────────────────
# 🆚 コールセンター / オペレーター 比較
# ─────────────────────────────────────────────
if not fdf.empty:
    st.markdown("### 🆚 コールセンター / オペレーター 比較")
    st.caption(
        "現在のフィルタ条件下での比較。完了率・応答率は月次タブの「全体」チーム加重平均。"
        "オペレーター単位ではレート系データを持たないため空欄になります。"
    )

    def _fmt_compare(df: pd.DataFrame) -> pd.DataFrame:
        show = df.copy()
        for c in ["解約率", "継続応援成功率", "完了率", "応答率"]:
            if c in show.columns:
                show[c] = show[c].apply(
                    lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "—"
                )
        for c in ["応対件数", "解約件数", "新規初回解約", "センターワード", "センター職員"]:
            if c in show.columns:
                show[c] = show[c].apply(lambda v: f"{int(v):,}")
        return show

    tab_cc, tab_ag = st.tabs(["コールセンター別", "オペレーター別"])
    with tab_cc:
        cmp_cc = metrics.compare_by(fdf, frates, "call_center")
        st.dataframe(_fmt_compare(cmp_cc), use_container_width=True, hide_index=True)
    with tab_ag:
        cmp_ag = metrics.compare_by(fdf, frates, "agent")
        st.dataframe(_fmt_compare(cmp_ag), use_container_width=True, hide_index=True, height=380)

    st.markdown("---")

# ─────────────────────────────────────────────
# 📞 発信・応答レート
# ─────────────────────────────────────────────
st.markdown("### 📞 発信・応答レート")
if frates.empty and rates_last30_scope.empty:
    st.info(
        "月次タブ（YYYY年M月）から応答率・完了率データを取得できませんでした。"
        "選択期間・コールセンターに該当データがない可能性があります。"
    )
else:
    team_pick = st.radio(
        "表示するチーム", TEAMS, index=TEAMS.index("全体"), horizontal=True,
        key="rate_team",
    )
    rate_kpis = metrics.rate_kpis(frates, team=team_pick)
    cols = st.columns(len(rate_kpis))
    for c, k in zip(cols, rate_kpis):
        c.metric(k.label, k.value, help=k.help)

    st.caption("📅 下の日次推移はサイドバーの期間フィルタと**独立**に、常に直近 30 日を表示します。")
    rt30 = metrics.rate_trend_last_days(rates_last30_scope, team=team_pick, days=30)
    st.plotly_chart(
        charts.rate_trend_chart(rt30, f"{team_pick}：完了率・応答率の日次推移（直近30日）"),
        use_container_width=True,
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(
            charts.rate_by_team_bar(metrics.rate_by_team(frates)),
            use_container_width=True,
        )
    with col_b:
        st.plotly_chart(
            charts.rate_by_cc_bar(metrics.rate_by_call_center(frates, team=team_pick)),
            use_container_width=True,
        )

    with st.expander("📄 月次レートデータ（フィルタ後）"):
        show = frates.copy()
        for c in ("completion_rate", "response_rate", "unique_completion_rate"):
            if c in show.columns:
                show[c] = (show[c] * 100).round(2)
        st.dataframe(
            show.rename(
                columns={
                    "date": "日付", "call_center": "コールセンター", "team": "チーム",
                    "completion_rate": "完了率(%)", "response_rate": "応答率(%)",
                    "unique_completion_rate": "ユニーク完了率(%)",
                    "total_dispatch": "総発数", "completion_count": "完了数",
                    "incoming_count": "入電数", "response_count": "応答数",
                    "unique_total_dispatch": "ユニーク総発数",
                    "unique_completion_count": "ユニーク完了数",
                    "source_tab": "元タブ",
                }
            ),
            use_container_width=True, hide_index=True, height=320,
        )

st.markdown("---")

if fdf.empty:
    st.stop()

# ─────────────────────────────────────────────
# 📈 応対・解約・継続応援 の推移
# ─────────────────────────────────────────────
st.markdown("### 📈 応対件数・解約・継続応援 の推移")
ts = metrics.time_series(fdf, granularity=granularity)
st.plotly_chart(
    charts.trend_total_and_cancel(ts, granularity), use_container_width=True
)
col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(
        charts.trend_retention_rate(ts, granularity), use_container_width=True
    )
with col_b:
    cc_ts = metrics.time_series_by(fdf, "call_center", granularity=granularity)
    st.plotly_chart(
        charts.trend_stacked_area(
            cc_ts, "call_center", granularity, "コールセンター別 応対件数"
        ),
        use_container_width=True,
    )
ag_ts = metrics.time_series_by(fdf, "agent", granularity=granularity)
st.plotly_chart(
    charts.trend_stacked_area(ag_ts, "agent", granularity, "担当者別 応対件数"),
    use_container_width=True,
)

st.markdown("---")

# ─────────────────────────────────────────────
# 📊 内訳
# ─────────────────────────────────────────────
st.markdown("### 📊 内訳")
c1, c2 = st.columns(2)
with c1:
    share_df = metrics.request_share(fdf)
    st.plotly_chart(
        charts.share_bar(
            share_df, "category",
            "問い合わせ内容カテゴリ内訳（% 表示・主要12カテゴリ ＋ その他）",
        ),
        use_container_width=True,
    )
    prod_df = metrics.product_breakdown(fdf)
    st.plotly_chart(
        charts.horizontal_bar(prod_df, "count", "product", "商品別件数"),
        use_container_width=True,
    )
with c2:
    canc_sub = metrics.cancel_by_subscription(fdf)
    st.plotly_chart(
        charts.vertical_bar(
            canc_sub, "subscription_count", "count", "定期回数別 解約件数"
        ),
        use_container_width=True,
    )
    reason_top = metrics.cancel_reason_top(fdf, top_n=15)
    st.plotly_chart(
        charts.horizontal_bar(reason_top, "count", "cancel_reason", "解約理由 TOP15"),
        use_container_width=True,
    )

st.markdown("---")

# ─────────────────────────────────────────────
# 🗂 その他解約理由 集計（Google Form の19事前定義カテゴリに含まれない自由記述をキーワード分類）
# ─────────────────────────────────────────────
st.markdown("### 🗂 その他解約理由 集計")
st.caption(
    "Google Form の事前定義19カテゴリに該当しない**自由記述**の解約理由を、"
    "キーワードで分類して集計します。"
    "例: 「勘違いして注文した」→ **認識違い・誤注文** / "
    "「ご主人が飲まない」→ **家族関係** など。"
)

_other = metrics.other_cancel_reason_breakdown(fdf)
if _other.empty:
    st.info("この条件では自由記述の解約理由がありません。")
else:
    _o_cols = st.columns([2, 3])
    with _o_cols[0]:
        st.plotly_chart(
            charts.horizontal_bar(
                _other[["category", "count"]], "count", "category",
                "その他解約理由 カテゴリ別",
            ),
            use_container_width=True,
        )
    with _o_cols[1]:
        st.markdown('**カテゴリ別の代表テキスト（上位5件を "/" で連結）**')
        st.dataframe(
            _other.rename(columns={
                "category": "分類",
                "count": "件数",
                "sample_texts": "サンプル記述",
            }),
            use_container_width=True, hide_index=True, height=360,
        )

    with st.expander("📋 自由記述の全件リスト（分類確認用）"):
        _raw = metrics.other_cancel_reason_raw(fdf)
        st.caption(f"該当 {len(_raw)} 種類の自由記述。**分類が「その他(分類不能)」のものは、キーワード辞書に追加検討 🔍**")
        st.dataframe(
            _raw.rename(columns={
                "text": "本文",
                "count": "件数",
                "classified": "分類結果",
            }),
            use_container_width=True, hide_index=True, height=420,
        )

st.markdown("---")

# ─────────────────────────────────────────────
# 🎯 継続応援 成功率の内訳
# ─────────────────────────────────────────────
st.markdown("### 🎯 継続応援 成功率の内訳")
tab_course, tab_subs, tab_reason, tab_cc2, tab_ag2 = st.tabs(
    ["コース別", "定期回数別", "解約理由別", "コールセンター別", "オペレーター別"]
)
with tab_course:
    r_course = metrics.retention_by(fdf, "course")
    st.plotly_chart(
        charts.retention_rate_bar(r_course, "course", "コース × 継続応援 成功率"),
        use_container_width=True,
    )
    st.dataframe(
        r_course.assign(rate=lambda d: (d["rate"] * 100).round(1).astype(str) + "%"),
        use_container_width=True, hide_index=True,
    )
with tab_subs:
    r_subs = metrics.retention_by(fdf, "subscription_count")
    st.plotly_chart(
        charts.retention_rate_bar(
            r_subs, "subscription_count", "定期回数 × 継続応援 成功率"
        ),
        use_container_width=True,
    )
    st.dataframe(
        r_subs.assign(rate=lambda d: (d["rate"] * 100).round(1).astype(str) + "%"),
        use_container_width=True, hide_index=True,
    )
with tab_reason:
    st.caption("解約理由は複数選択のため、行は理由ごとに分割集計しています。")
    r_reason = metrics.retention_by_reason(fdf).head(20)
    st.plotly_chart(
        charts.retention_rate_bar(
            r_reason, "cancel_reason", "解約理由 × 継続応援 成功率（TOP20）"
        ),
        use_container_width=True,
    )
    st.dataframe(
        r_reason.assign(rate=lambda d: (d["rate"] * 100).round(1).astype(str) + "%"),
        use_container_width=True, hide_index=True,
    )
with tab_cc2:
    r_cc = metrics.retention_by(fdf, "call_center")
    st.plotly_chart(
        charts.retention_rate_bar(
            r_cc, "call_center", "コールセンター × 継続応援 成功率"
        ),
        use_container_width=True,
    )
    st.dataframe(
        r_cc.assign(rate=lambda d: (d["rate"] * 100).round(1).astype(str) + "%"),
        use_container_width=True, hide_index=True,
    )
with tab_ag2:
    r_ag = metrics.retention_by(fdf, "agent")
    st.plotly_chart(
        charts.retention_rate_bar(r_ag, "agent", "オペレーター × 継続応援 成功率"),
        use_container_width=True,
    )
    st.dataframe(
        r_ag.assign(rate=lambda d: (d["rate"] * 100).round(1).astype(str) + "%"),
        use_container_width=True, hide_index=True,
    )

st.markdown("---")

# ─────────────────────────────────────────────
# 🌟 特別コース 内訳（hajuCS: 晩酌応援 / Co-HeartCS: すまいる応援 など、実データから自動検出）
# ─────────────────────────────────────────────
_special_course = metrics.detect_special_course_name(fdf)
_emoji = "🌙" if "晩酌" in _special_course else ("🌈" if "すまいる" in _special_course or "スマイル" in _special_course else "🌟")
st.markdown(f"### {_emoji} {_special_course} 内訳")
st.caption(
    "対応内容の分類。解約系（満了解約 / 途中解約 / スマイル開始前解約など）＋ "
    "継続系（満了未満継続了承 / 満了継続応援成功 / スマイル開始前継続了承）で集計します。"
)
banshaku_kpis = metrics.banshaku_kpis(fdf)
cols = st.columns(len(banshaku_kpis))
for c, k in zip(cols, banshaku_kpis):
    c.metric(k.label, k.value, help=k.help)

ban_df = metrics.banshaku_breakdown(fdf)
if not ban_df.empty:
    st.plotly_chart(
        charts.banshaku_bar(ban_df, title=f"{_special_course} 対応内容の内訳"),
        use_container_width=True,
    )
    st.dataframe(
        ban_df.assign(share=lambda d: (d["share"] * 100).round(1).astype(str) + "%"),
        use_container_width=True, hide_index=True,
    )

st.markdown("---")

# ─────────────────────────────────────────────
# ⚠️ センター系の内訳
# ─────────────────────────────────────────────
st.markdown("### ⚠️ センター系 件数の内訳")
st.caption(
    "「消費者センターワードあり」＋「消費者センター職員からの入電」を"
    "センター系として集計しています。"
)
tc1, tc2, tc3 = st.tabs(["解約理由別", "コース別", "定期回数別"])
with tc1:
    st.plotly_chart(
        charts.horizontal_bar(
            metrics.center_breakdown(fdf, "cancel_reason").head(15),
            "count", "cancel_reason", "センター系 × 解約理由 TOP15",
        ),
        use_container_width=True,
    )
with tc2:
    st.plotly_chart(
        charts.vertical_bar(
            metrics.center_breakdown(fdf, "course"),
            "course", "count", "センター系 × コース",
        ),
        use_container_width=True,
    )
with tc3:
    st.plotly_chart(
        charts.vertical_bar(
            metrics.center_breakdown(fdf, "subscription_count"),
            "subscription_count", "count", "センター系 × 定期回数",
        ),
        use_container_width=True,
    )

st.markdown("---")

# ─────────────────────────────────────────────
# 👶 お子様の年齢分析（Co-HeartCS 用・データがある時のみ自動表示）
# ─────────────────────────────────────────────
if metrics.has_child_age_data(fdf):
    import plotly.express as _px

    st.markdown("### 👶 お子様の年齢分析")
    st.caption(
        "キッズ商品ご使用のお客様から聞き取った年齢を "
        "0-3歳 / 4-6歳 / 7-9歳 / 10-12歳 / 13歳以上 / 不明 の6バケットに集約。"
        "解約以外にも問い合わせ内容・商品・コース・VOC など多角的に分析できます。"
    )

    def _grouped_bar(cross_df, group_col, title, height=380, x_angle=-30):
        """年齢を色分けにしたグループ棒グラフのヘルパー。"""
        if cross_df.empty:
            st.caption(f"{title}: 該当データがまだありません。")
            return
        _fig = _px.bar(
            cross_df.astype({"age_bucket": str, group_col: str}),
            x=group_col, y="count", color="age_bucket",
            barmode="group",
            title=title,
            labels={group_col: group_col, "count": "件数", "age_bucket": "年齢"},
            category_orders={"age_bucket": [b for b in ["0-3歳","4-6歳","7-9歳","10-12歳","13歳以上","不明"]]},
        )
        _fig.update_layout(height=height, xaxis_tickangle=x_angle,
                           legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(_fig, use_container_width=True)

    def _cross_table(cross_df, group_col):
        """年齢 × カラムのピボット表を表示。"""
        if cross_df.empty:
            return
        pivot = cross_df.pivot(
            index="age_bucket", columns=group_col, values="count"
        ).fillna(0).astype(int)
        st.dataframe(pivot, use_container_width=True)

    tab_age = st.tabs([
        "📊 概要",
        "🚪 解約",
        "🔁 定期回数",
        "📞 問い合わせ内容",
        "🛍 商品",
        "☕ コース",
        "🌈 すまいる応援",
        "⚠️ VOC・センター系",
    ])

    # === 概要 ===
    with tab_age[0]:
        # 上段: 年齢分布 + 継続応援成功率
        c1, c2 = st.columns([1, 1])
        with c1:
            st.plotly_chart(
                charts.vertical_bar(
                    metrics.child_age_distribution(fdf).rename(columns={"age_bucket": "年齢"}),
                    "年齢", "count", "年齢バケット別 応対件数",
                ),
                use_container_width=True,
            )
        with c2:
            _age_reten = metrics.child_age_retention(fdf)
            if not _age_reten.empty:
                st.plotly_chart(
                    charts.retention_rate_bar(
                        _age_reten.rename(columns={"age_bucket": "年齢"}),
                        "年齢", "年齢別 継続応援 成功率",
                    ),
                    use_container_width=True,
                )
            else:
                st.info("継続応援の有効データがまだありません。")

        # 下段: 年齢別 総合KPI 表
        st.markdown("#### 年齢別 総合サマリ")
        _summary = metrics.child_age_summary(fdf)
        if not _summary.empty:
            _show = _summary.copy()
            _show["解約率"] = _show["解約率"].apply(
                lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "—"
            )
            _show["継続応援成功率"] = _show["継続応援成功率"].apply(
                lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "—"
            )
            for c in ("応対件数", "解約件数", "新規初回解約", "センターワード", "温度感上昇", "嬉しい声"):
                _show[c] = _show[c].apply(lambda v: f"{int(v):,}")
            st.dataframe(_show, use_container_width=True, hide_index=True)

    # === 解約 ===
    with tab_age[1]:
        _cross = metrics.child_age_cross(
            fdf, "cancel_reason", exploded=True, top_n=15, filter_cancel=True,
        )
        _grouped_bar(_cross, "cancel_reason", "年齢 × 解約理由 TOP15", height=440)
        with st.expander("📋 表で見る（年齢 × 解約理由）"):
            _cross_table(_cross, "cancel_reason")

    # === 定期回数 ===
    with tab_age[2]:
        _cross = metrics.child_age_cross(fdf, "subscription_count")
        # SUBSCRIPTION_ORDER 順に並べたいので、事前定義順で category 化
        if not _cross.empty:
            _cross["subscription_count"] = pd.Categorical(
                _cross["subscription_count"],
                categories=SUBSCRIPTION_ORDER,
                ordered=True,
            )
            _cross = _cross.sort_values(["subscription_count", "age_bucket"])
        _grouped_bar(_cross, "subscription_count", "年齢 × 定期回数", x_angle=0)
        with st.expander("📋 表で見る（年齢 × 定期回数）"):
            _cross_table(_cross, "subscription_count")

    # === 問い合わせ内容 ===
    with tab_age[3]:
        _cross = metrics.child_age_cross(fdf, "request_category")
        _grouped_bar(_cross, "request_category", "年齢 × 問い合わせ内容")
        with st.expander("📋 表で見る（年齢 × 問い合わせ内容）"):
            _cross_table(_cross, "request_category")

    # === 商品 ===
    with tab_age[4]:
        _cross = metrics.child_age_cross(fdf, "product", exploded=True, top_n=10)
        _grouped_bar(_cross, "product", "年齢 × 商品 TOP10", height=420)
        with st.expander("📋 表で見る（年齢 × 商品）"):
            _cross_table(_cross, "product")

    # === コース ===
    with tab_age[5]:
        _cross = metrics.child_age_cross(fdf, "course")
        _grouped_bar(_cross, "course", "年齢 × コース", x_angle=0)
        with st.expander("📋 表で見る（年齢 × コース）"):
            _cross_table(_cross, "course")

    # === すまいる応援 対応内容 ===
    with tab_age[6]:
        _cross = metrics.child_age_cross(fdf, "banshaku_category")
        _grouped_bar(_cross, "banshaku_category", "年齢 × すまいる応援対応内容", height=400)
        with st.expander("📋 表で見る（年齢 × すまいる応援）"):
            _cross_table(_cross, "banshaku_category")

    # === VOC・センター系 ===
    with tab_age[7]:
        # VOC 列で集計（消費者センターワード / 職員 / 嬉しい声 / 温度感 / なし ほか）
        _cross_voc = metrics.child_age_cross(fdf, "voc")
        _grouped_bar(_cross_voc, "voc", "年齢 × VOC（応対の質感）", height=380)

        # 温度感上昇の原因（複数選択・エスカレ深掘り）
        _cross_esc = metrics.child_age_cross(fdf, "escalation_cause", exploded=True, top_n=10)
        _grouped_bar(_cross_esc, "escalation_cause", "年齢 × 温度感上昇 原因 TOP10", height=380)

        with st.expander("📋 表で見る（年齢 × VOC / 温度感）"):
            st.caption("VOC 内訳")
            _cross_table(_cross_voc, "voc")
            st.caption("温度感上昇 原因")
            _cross_table(_cross_esc, "escalation_cause")

    st.markdown("---")

# ─────────────────────────────────────────────
# 💬 自由記述
# ─────────────────────────────────────────────
st.markdown("### 💬 自由記述の詳細")


def _filter_free_text(
    df: pd.DataFrame,
    products: list[str],
    courses: list[str],
    subs: list[str],
    kinds: list[str],
    kind_col: str,
) -> pd.DataFrame:
    """自由記述テーブルに 4 種類のフィルタを重ねる（複数選択セルは contains 判定）。"""
    if df.empty:
        return df
    out = df.copy()
    if products:
        import re as _re
        pat = "|".join(_re.escape(p) for p in products)
        out = out[out["product"].fillna("").str.contains(pat, regex=True)]
    if courses:
        out = out[out["course"].isin(courses)]
    if subs:
        out = out[out["subscription_count"].isin(subs)]
    if kinds and kind_col in out.columns:
        import re as _re
        pat = "|".join(_re.escape(k) for k in kinds)
        out = out[out[kind_col].fillna("").str.contains(pat, regex=True)]
    return out


tab_neg, tab_pos = st.tabs(["🔥 ネガティブ", "🌸 ポジティブ（嬉しい声）"])

with tab_neg:
    # 4 フィルタ列
    _neg_prod_opt = sorted(explode_multi(fdf, "product")["product"].unique().tolist())
    _neg_course_opt = sorted([c for c in fdf["course"].unique() if c])
    _neg_sub_opt = [s for s in SUBSCRIPTION_ORDER if s in fdf["subscription_count"].unique()]
    _neg_esc_opt = sorted(explode_multi(fdf, "escalation_cause")["escalation_cause"].unique().tolist())

    _nc = st.columns(4)
    with _nc[0]:
        f_neg_products = st.multiselect("商品", _neg_prod_opt, key="ft_neg_prod")
    with _nc[1]:
        f_neg_courses = st.multiselect("コース", _neg_course_opt, key="ft_neg_course")
    with _nc[2]:
        f_neg_subs = st.multiselect("定期回数", _neg_sub_opt, key="ft_neg_sub")
    with _nc[3]:
        f_neg_kinds = st.multiselect("温度感原因", _neg_esc_opt, key="ft_neg_kind")

    kw = st.text_input("キーワード検索（本文）", key="kw_neg", placeholder="例: 消費者センター")
    neg = metrics.free_text_records(fdf, "negative", keyword=kw)
    neg = _filter_free_text(
        neg, f_neg_products, f_neg_courses, f_neg_subs, f_neg_kinds,
        kind_col="escalation_cause",
    )
    st.caption(f"該当 {len(neg):,} 件")
    st.dataframe(
        neg.rename(
            columns={
                "timestamp": "日時", "call_center": "CC", "agent": "担当者",
                "product": "商品", "course": "コース", "subscription_count": "定期回数",
                "note_negative": "ネガ本文", "escalation_cause": "温度感原因",
            }
        ),
        use_container_width=True, hide_index=True, height=420,
    )

with tab_pos:
    _pos_prod_opt = sorted(explode_multi(fdf, "product")["product"].unique().tolist())
    _pos_course_opt = sorted([c for c in fdf["course"].unique() if c])
    _pos_sub_opt = [s for s in SUBSCRIPTION_ORDER if s in fdf["subscription_count"].unique()]
    _pos_kind_opt = sorted(explode_multi(fdf, "positive_kind")["positive_kind"].unique().tolist())

    _pc = st.columns(4)
    with _pc[0]:
        f_pos_products = st.multiselect("商品", _pos_prod_opt, key="ft_pos_prod")
    with _pc[1]:
        f_pos_courses = st.multiselect("コース", _pos_course_opt, key="ft_pos_course")
    with _pc[2]:
        f_pos_subs = st.multiselect("定期回数", _pos_sub_opt, key="ft_pos_sub")
    with _pc[3]:
        f_pos_kinds = st.multiselect("内容種別", _pos_kind_opt, key="ft_pos_kind")

    kw = st.text_input("キーワード検索（本文）", key="kw_pos", placeholder="例: 効果")
    pos = metrics.free_text_records(fdf, "positive", keyword=kw)
    pos = _filter_free_text(
        pos, f_pos_products, f_pos_courses, f_pos_subs, f_pos_kinds,
        kind_col="positive_kind",
    )
    st.caption(f"該当 {len(pos):,} 件")
    # 種別ごとの件数サマリ（絞込後）
    if not pos.empty:
        by_kind = pos["positive_kind"].value_counts()
        summary = "  ／  ".join([f"**{k}**: {v}" for k, v in by_kind.items() if k])
        if summary:
            st.markdown(f"内訳: {summary}")
    st.dataframe(
        pos.rename(
            columns={
                "timestamp": "日時", "call_center": "CC", "agent": "担当者",
                "product": "商品", "course": "コース", "subscription_count": "定期回数",
                "note_positive": "ポジ本文", "positive_kind": "内容種別",
            }
        ),
        use_container_width=True, hide_index=True, height=420,
    )

# ─────────────────────────────────────────────
# Raw
# ─────────────────────────────────────────────
with st.expander("🗂 対象データ（フィルタ後の応対記録 生データ）"):
    st.dataframe(fdf, use_container_width=True, hide_index=True, height=360)
    st.download_button(
        "CSV でダウンロード",
        data=fdf.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"lu_n2_dashboard_{date_from}_{date_to}.csv",
        mime="text/csv",
    )
