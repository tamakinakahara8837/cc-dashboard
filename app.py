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
    load_data,
    previous_period,
)

st.set_page_config(
    page_title="hajuCSダッシュボード", page_icon="📊", layout="wide",
)

# ─────────────────────────────────────────────
# カスタム CSS（デザイン仕上げ）
# ─────────────────────────────────────────────
st.markdown(
    """
<style>
/* 全体フォント */
html, body, [class*="css"] {
    font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                 "Yu Gothic", "Meiryo", sans-serif;
}

/* h1 のアクセント帯 */
.stApp h1 {
    color: #7a4f00;
    letter-spacing: 0.02em;
    padding: 12px 20px;
    background: linear-gradient(90deg, #fff2b3 0%, #fffbe6 100%);
    border-left: 6px solid #e0a800;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

/* セクション見出し h3 の下線とスペース */
.stApp h3 {
    color: #5d3f00;
    margin-top: 28px !important;
    margin-bottom: 12px !important;
    padding: 4px 0 8px 0 !important;
    border-bottom: 2px solid rgba(224, 168, 0, 0.35) !important;
}

/* KPI カードを浮き上がらせる */
div[data-testid="stMetric"] {
    background-color: rgba(255, 255, 255, 0.7);
    padding: 14px 18px;
    border-radius: 12px;
    border: 1px solid rgba(224, 168, 0, 0.15);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
    transition: box-shadow 0.15s ease-in-out, transform 0.15s;
}
div[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 10px rgba(224, 168, 0, 0.15);
    transform: translateY(-1px);
}

/* サイドバーをキャラメル系に */
section[data-testid="stSidebar"] {
    background-color: #fff5d1 !important;
    border-right: 1px solid rgba(224, 168, 0, 0.15);
}
section[data-testid="stSidebar"] h3 {
    color: #5d3f00 !important;
    border-bottom: 1px solid rgba(224, 168, 0, 0.3) !important;
}

/* 区切り線 hr を薄いゴールドに */
hr {
    border: none !important;
    border-top: 1px dashed rgba(224, 168, 0, 0.4) !important;
    margin: 24px 0 !important;
}

/* Tab のアクティブラベルにアクセント */
button[data-baseweb="tab"] {
    font-weight: 500;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #b8860b !important;
}
div[data-baseweb="tab-highlight"] {
    background-color: #e0a800 !important;
}

/* データフレームの罫線を柔らかく */
div[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(224, 168, 0, 0.15);
}

/* Expander のヘッダを少し華やかに */
details summary {
    background-color: rgba(255, 245, 209, 0.5) !important;
    border-radius: 6px !important;
}

/* Metric caption（全体の◯%） */
.stCaption, div[data-testid="stCaptionContainer"] {
    color: #8a6b1a !important;
}
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
st.title("📊 hajuCSダッシュボード")
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
# 🌙 晩酌応援コース 内訳
# ─────────────────────────────────────────────
st.markdown("### 🌙 晩酌応援コース 内訳")
st.caption(
    "解約系（満了解約 / 差額あり途中解約 / 差額なし途中解約）＋ "
    "継続系（満了未満継続了承 / 満了継続応援成功）で分類。"
)
banshaku_kpis = metrics.banshaku_kpis(fdf)
cols = st.columns(len(banshaku_kpis))
for c, k in zip(cols, banshaku_kpis):
    c.metric(k.label, k.value, help=k.help)

ban_df = metrics.banshaku_breakdown(fdf)
if not ban_df.empty:
    st.plotly_chart(charts.banshaku_bar(ban_df), use_container_width=True)
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
# 💬 自由記述
# ─────────────────────────────────────────────
st.markdown("### 💬 自由記述の詳細")
tab_neg, tab_pos = st.tabs(["🔥 ネガティブ", "🌸 ポジティブ（嬉しい声）"])
with tab_neg:
    kw = st.text_input("キーワード検索（ネガ）", key="kw_neg", placeholder="例: 消費者センター")
    neg = metrics.free_text_records(fdf, "negative", keyword=kw)
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
    kw = st.text_input("キーワード検索（ポジ）", key="kw_pos", placeholder="例: 効果")
    pos = metrics.free_text_records(fdf, "positive", keyword=kw)
    st.caption(f"該当 {len(pos):,} 件（すべての嬉しい声を全文表示）")
    # 種別ごとの件数サマリ
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
