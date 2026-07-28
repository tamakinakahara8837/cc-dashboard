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

from typing import Optional

import pandas as pd
import streamlit as st

import charts
import metrics
from data_loader import (
    AGE_GROUP_ORDER,
    REQUEST_MAIN_CATEGORIES,
    REQUEST_OTHER_LABEL,
    SHEETS,
    SUBSCRIPTION_ORDER,
    TEAMS,
    apply_ops_filters,
    apply_rate_filters,
    explode_multi,
    load_brand_name,
    load_brands_config,
    load_data,
    load_shared_config,
    load_special_course_name,
    load_theme_name,
    previous_period,
)

# ─────────────────────────────────────────────
# マルチブランド or 単一ブランドを判定
# `[brands.*]` があればマルチブランドモード、無ければ従来の単一ブランドモード
# ─────────────────────────────────────────────
_BRANDS_CONFIG: dict[str, dict] = load_brands_config()
_MULTI_BRAND: bool = len(_BRANDS_CONFIG) > 0

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
    "blue": {
        "h1_text": "#0d47a1",
        "h1_grad_start": "#bbdefb",
        "h1_grad_end": "#e3f2fd",
        "h1_border": "#1976d2",
        "h3_text": "#1565c0",
        "h3_border": "rgba(25, 118, 210, 0.4)",
        "metric_border": "rgba(25, 118, 210, 0.2)",
        "metric_hover": "rgba(25, 118, 210, 0.2)",
        "sidebar_bg": "#e3f2fd",
        "sidebar_border": "rgba(25, 118, 210, 0.2)",
        "sidebar_h3": "#1565c0",
        "sidebar_h3_border": "rgba(25, 118, 210, 0.35)",
        "hr_border": "rgba(25, 118, 210, 0.45)",
        "tab_active": "#1565c0",
        "tab_highlight": "#1976d2",
        "df_border": "rgba(25, 118, 210, 0.2)",
        "expander_bg": "rgba(187, 222, 251, 0.5)",
        "caption": "#0d47a1",
    },
    "red": {
        "h1_text": "#7f1d1d",
        "h1_grad_start": "#fecaca",
        "h1_grad_end": "#fef2f2",
        "h1_border": "#dc2626",
        "h3_text": "#991b1b",
        "h3_border": "rgba(220, 38, 38, 0.4)",
        "metric_border": "rgba(220, 38, 38, 0.18)",
        "metric_hover": "rgba(220, 38, 38, 0.22)",
        "sidebar_bg": "#fef2f2",
        "sidebar_border": "rgba(220, 38, 38, 0.18)",
        "sidebar_h3": "#991b1b",
        "sidebar_h3_border": "rgba(220, 38, 38, 0.35)",
        "hr_border": "rgba(220, 38, 38, 0.45)",
        "tab_active": "#b91c1c",
        "tab_highlight": "#dc2626",
        "df_border": "rgba(220, 38, 38, 0.18)",
        "expander_bg": "rgba(254, 202, 202, 0.4)",
        "caption": "#991b1b",
    },
}
# ─────────────────────────────────────────────
# ブランドコンテキスト決定
# マルチブランドモード: `st.session_state["selected_brand"]` を参照
#   （サイドバーの selectbox が同じキーで書き込む → 選択変更で自動反映）
# 単一ブランドモード:  従来通り Secrets から直接読む
# ─────────────────────────────────────────────
_special_course_override: Optional[str] = None
_sheets_key: tuple = ()

if _MULTI_BRAND:
    _brand_keys: list[str] = list(_BRANDS_CONFIG.keys())
    _default_brand_key = _brand_keys[0]
    _selected_brand_key = st.session_state.get("selected_brand", _default_brand_key)
    if _selected_brand_key not in _BRANDS_CONFIG:
        _selected_brand_key = _default_brand_key
    _current = _BRANDS_CONFIG[_selected_brand_key]
    BRAND = _current["display_name"]
    _theme_name = _current.get("theme", "gold")
    _special_course_override = _current.get("special_course")
    # sheets_key はハッシュ可能な tuple にして cache_data のキーに使う
    _sheets_key = tuple(sorted(_current["sheets"].items()))
else:
    BRAND = load_brand_name()
    _theme_name = load_theme_name()
    _special_course_override = load_special_course_name()

DASHBOARD_TITLE = f"{BRAND}ダッシュボード"
T = THEME_PALETTES.get(_theme_name, THEME_PALETTES["gold"])

st.set_page_config(
    page_title=DASHBOARD_TITLE, page_icon="📊", layout="wide",
)

# マルチブランドではブランド切替時に set_page_config で設定した page_title が
# 更新できないため、JS でブラウザタブ名を動的に上書きする
if _MULTI_BRAND:
    st.markdown(
        f"<script>document.title = {DASHBOARD_TITLE!r};</script>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# カスタム CSS（デザイン仕上げ）
# ─────────────────────────────────────────────
st.markdown(
    f"""
<style>
/* Google Fonts: 数字は Inter、和文はヒラギノ系 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap');

/* 全体タイポグラフィ */
html, body, [class*="css"], .stApp, .stApp * {{
    font-family: "Inter", "Hiragino Sans", "Hiragino Kaku Gothic ProN",
                 "Yu Gothic", "Meiryo", "Segoe UI", sans-serif;
    font-feature-settings: "palt", "cv11";
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}

/* 背景: 極めてサトルなグラデ + わずかなアクセント */
.stApp {{
    background:
        radial-gradient(ellipse 1400px 700px at 12% -8%, {T["h1_grad_start"]}22 0%, transparent 55%),
        radial-gradient(ellipse 900px 500px at 95% 105%, {T["h1_border"]}0d 0%, transparent 55%),
        #fafafa;
}}

/* メインコンテンツエリアに余白を強化 */
.stApp .main .block-container {{
    padding-top: 3rem !important;
    padding-bottom: 4rem !important;
    max-width: 1400px;
}}

/* ─── h1: エディトリアル風の大タイトル ─── */
.stApp h1 {{
    font-family: "Space Grotesk", "Inter", sans-serif !important;
    color: {T["h1_text"]};
    letter-spacing: -0.035em;
    font-weight: 700 !important;
    font-size: 42px !important;
    padding: 28px 36px;
    background: linear-gradient(135deg, {T["h1_grad_start"]} 0%, {T["h1_grad_end"]} 100%);
    border: none;
    border-left: 4px solid {T["h1_border"]};
    border-radius: 6px;
    box-shadow: 0 1px 30px -12px {T["h1_border"]}55;
    margin-top: 8px !important;
    margin-bottom: 20px !important;
    position: relative;
    overflow: hidden;
    line-height: 1.15;
}}
/* h1 の右下に極細アクセント */
.stApp h1::after {{
    content: "";
    position: absolute;
    top: 20%;
    right: 6%;
    width: 60px;
    height: 60px;
    border: 2px solid {T["h1_border"]}33;
    border-radius: 50%;
    pointer-events: none;
}}
.stApp h1::before {{
    content: "";
    position: absolute;
    bottom: 20%;
    right: 12%;
    width: 24px;
    height: 24px;
    background: {T["h1_border"]}22;
    border-radius: 50%;
    pointer-events: none;
}}

/* ─── h3: ミニマルなアクセントバー + 大文字風 ─── */
.stApp h3 {{
    font-family: "Space Grotesk", "Inter", sans-serif !important;
    color: {T["h3_text"]};
    font-weight: 600 !important;
    font-size: 22px !important;
    letter-spacing: -0.02em;
    margin-top: 40px !important;
    margin-bottom: 18px !important;
    padding: 0 0 0 16px !important;
    border-bottom: none !important;
    position: relative;
    line-height: 1.3;
}}
.stApp h3::before {{
    content: "";
    position: absolute;
    top: 6px;
    bottom: 6px;
    left: 0;
    width: 4px;
    background: linear-gradient(180deg, {T["h1_border"]} 0%, {T["h3_border"]} 100%);
    border-radius: 2px;
}}

/* ─── KPI カード: フラット + シャープ ─── */
div[data-testid="stMetric"] {{
    background: white;
    padding: 22px 24px 20px 24px;
    border-radius: 8px;
    border: 1px solid rgba(0,0,0,0.06);
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    transition: transform 0.25s cubic-bezier(0.2,0.8,0.2,1), box-shadow 0.25s, border-color 0.2s;
    position: relative;
    overflow: hidden;
}}
/* 左サイドの縦アクセントバー（極細） */
div[data-testid="stMetric"]::before {{
    content: "";
    position: absolute;
    left: 0;
    top: 12px;
    bottom: 12px;
    width: 3px;
    background: {T["h1_border"]};
    border-radius: 0 2px 2px 0;
    opacity: 0.9;
}}
div[data-testid="stMetric"]:hover {{
    transform: translateY(-2px);
    border-color: {T["h1_border"]}44;
    box-shadow: 0 20px 40px -20px {T["h1_border"]}55, 0 4px 12px -4px rgba(0,0,0,0.05);
}}
/* KPI 値: エディトリアル風の巨大数字 */
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    font-family: "Space Grotesk", "Inter", sans-serif !important;
    font-size: 40px !important;
    font-weight: 700 !important;
    letter-spacing: -0.04em;
    color: {T["h1_text"]};
    line-height: 1.05;
    margin-top: 6px !important;
}}
/* KPI ラベル: 小さく、控えめに */
div[data-testid="stMetric"] label {{
    font-size: 11px !important;
    font-weight: 600 !important;
    color: rgba(0,0,0,0.55) !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}
/* Delta */
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {{
    font-weight: 600 !important;
    font-size: 12px !important;
    margin-top: 4px;
}}

/* ─── サイドバー: 洗練されたパネル ─── */
section[data-testid="stSidebar"] {{
    background: {T["sidebar_bg"]} !important;
    border-right: 1px solid rgba(0,0,0,0.06);
    box-shadow: none;
}}
section[data-testid="stSidebar"] h3 {{
    font-family: "Space Grotesk", "Inter", sans-serif !important;
    color: {T["sidebar_h3"]} !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    border-bottom: none !important;
    padding: 0 !important;
    margin-top: 20px !important;
    margin-bottom: 12px !important;
}}
section[data-testid="stSidebar"] h3::before {{
    display: none !important;
}}
section[data-testid="stSidebar"] h3::after {{
    display: none !important;
}}

/* ─── 区切り線 hr: 超極細 ─── */
hr {{
    border: none !important;
    height: 1px !important;
    background: rgba(0,0,0,0.06) !important;
    margin: 40px 0 !important;
}}

/* ─── Tab: シャープなアンダーライン ─── */
button[data-baseweb="tab"] {{
    font-weight: 500 !important;
    font-size: 14px !important;
    letter-spacing: 0.02em;
    padding: 12px 4px !important;
    margin-right: 24px !important;
    color: rgba(0,0,0,0.5) !important;
    transition: color 0.15s;
}}
button[data-baseweb="tab"]:hover {{
    color: {T["tab_active"]} !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    color: {T["tab_active"]} !important;
    font-weight: 700 !important;
}}
div[data-baseweb="tab-highlight"] {{
    background-color: {T["tab_highlight"]} !important;
    height: 2px !important;
    border-radius: 0 !important;
}}
div[data-baseweb="tab-border"] {{
    background-color: rgba(0,0,0,0.06) !important;
}}

/* ─── データフレーム: シャープ ─── */
div[data-testid="stDataFrame"] {{
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(0,0,0,0.06);
    box-shadow: none;
}}

/* ─── Expander: フラットカード ─── */
details {{
    border: 1px solid rgba(0,0,0,0.06) !important;
    border-radius: 8px !important;
    overflow: hidden;
    background: white;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}}
details summary {{
    background-color: white !important;
    border-radius: 8px !important;
    padding: 14px 18px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    letter-spacing: 0.02em;
    transition: background-color 0.15s;
    color: {T["h3_text"]};
}}
details summary:hover {{
    background-color: {T["h1_grad_end"]}66 !important;
}}
details[open] summary {{
    border-bottom: 1px solid rgba(0,0,0,0.06);
    border-radius: 8px 8px 0 0 !important;
}}

/* ─── Caption ─── */
.stCaption, div[data-testid="stCaptionContainer"] {{
    color: rgba(0,0,0,0.5) !important;
    font-size: 12px !important;
    letter-spacing: 0.02em;
    line-height: 1.5;
}}

/* ─── ボタン全般 ─── */
.stApp button[kind="secondary"],
.stApp button[kind="primary"] {{
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    letter-spacing: 0.02em;
    padding: 10px 20px !important;
    transition: transform 0.1s, box-shadow 0.15s;
    border: 1px solid rgba(0,0,0,0.08) !important;
}}
.stApp button[kind="secondary"]:hover,
.stApp button[kind="primary"]:hover {{
    transform: translateY(-1px);
    box-shadow: 0 6px 16px -6px rgba(0,0,0,0.12);
    border-color: {T["h1_border"]}66 !important;
}}
.stApp button[kind="primary"] {{
    background-color: {T["h1_border"]} !important;
    color: white !important;
    border: none !important;
}}

/* ─── multiselect / selectbox のタグ ─── */
[data-baseweb="tag"] {{
    background-color: {T["h1_border"]} !important;
    color: white !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    letter-spacing: 0.02em;
}}

/* ─── multiselect / selectbox のコンテナ ─── */
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {{
    border-radius: 6px !important;
    border-color: rgba(0,0,0,0.1) !important;
    transition: border-color 0.15s, box-shadow 0.15s;
}}
div[data-baseweb="select"]:hover > div,
div[data-baseweb="input"]:hover > div {{
    border-color: {T["h1_border"]}66 !important;
}}
div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="input"] > div:focus-within {{
    border-color: {T["h1_border"]} !important;
    box-shadow: 0 0 0 3px {T["h1_border"]}22 !important;
}}

/* ─── Plotly グラフをフラットカード化 ─── */
div[data-testid="stPlotlyChart"] {{
    border-radius: 10px;
    padding: 12px;
    background: white;
    border: 1px solid rgba(0,0,0,0.06);
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    margin-bottom: 12px;
    transition: box-shadow 0.2s;
}}
div[data-testid="stPlotlyChart"]:hover {{
    box-shadow: 0 10px 30px -12px rgba(0,0,0,0.1);
}}

/* ─── ラジオ・チェックボックス ─── */
div[data-baseweb="radio"] label,
div[data-testid="stCheckbox"] label {{
    font-size: 13px !important;
    font-weight: 500 !important;
}}

/* ─── コード / タイムスタンプ的な要素 ─── */
code {{
    background-color: rgba(0,0,0,0.04) !important;
    color: {T["h1_text"]} !important;
    border-radius: 4px !important;
    padding: 2px 6px !important;
    font-family: "SF Mono", "Menlo", "Monaco", "Consolas", monospace !important;
    font-size: 90% !important;
}}

/* ─── ブランド切替ピル: エディトリアル / モノクロベース ─── */
.st-key-selected_brand {{
    margin-bottom: 32px !important;
    margin-top: 4px !important;
}}
.st-key-selected_brand [data-baseweb="button-group"],
.st-key-selected_brand [role="radiogroup"],
.st-key-selected_brand [role="group"],
.st-key-selected_brand > div:first-child {{
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 10px !important;
    justify-content: flex-start !important;
}}
.st-key-selected_brand button,
.st-key-selected_brand [role="button"],
.st-key-selected_brand [data-testid*="stBaseButton"] {{
    font-family: "Space Grotesk", "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 600 !important;
    padding: 14px 28px !important;
    min-width: 130px !important;
    height: auto !important;
    border-radius: 6px !important;
    letter-spacing: 0.02em;
    background: white !important;
    color: rgba(0,0,0,0.65) !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
    box-shadow: none;
    transition: all 0.18s cubic-bezier(0.2,0.8,0.2,1);
    line-height: 1.2 !important;
    white-space: nowrap !important;
    overflow: visible !important;
    text-overflow: clip !important;
    position: relative;
}}
.st-key-selected_brand button *,
.st-key-selected_brand [role="button"] * {{
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: nowrap !important;
    max-width: none !important;
    font-size: inherit !important;
    font-weight: inherit !important;
}}
.st-key-selected_brand button:hover,
.st-key-selected_brand [role="button"]:hover {{
    transform: translateY(-1px);
    border-color: {T["h1_border"]}88 !important;
    color: {T["h1_text"]} !important;
    box-shadow: 0 8px 20px -8px {T["h1_border"]}55;
}}
/* 選択中: ブランド色で塗る */
.st-key-selected_brand button[aria-pressed="true"],
.st-key-selected_brand button[aria-checked="true"],
.st-key-selected_brand [role="button"][aria-pressed="true"],
.st-key-selected_brand [kind="primary"] {{
    background: linear-gradient(135deg, {T["h1_border"]} 0%, {T["h1_border"]}dd 100%) !important;
    color: white !important;
    border-color: {T["h1_border"]} !important;
    box-shadow:
        0 1px 2px rgba(0,0,0,0.06),
        0 12px 24px -8px {T["h1_border"]}88 !important;
}}
.st-key-selected_brand button[aria-pressed="true"]:hover,
.st-key-selected_brand button[aria-checked="true"]:hover,
.st-key-selected_brand [role="button"][aria-pressed="true"]:hover {{
    transform: translateY(-2px);
    color: white !important;
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
result = load_data(sheets_key=_sheets_key)
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
    # 選択中ブランドのシート（マルチブランド時）or 従来 SHEETS
    if _MULTI_BRAND:
        cc_options = list(_current["sheets"].keys())
    else:
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

    # TV 購入フィルタ（HAN.d などの列があるブランドのみ表示）
    tv_opt: list[str] = []
    if "tv_purchase" in ops_all.columns:
        tv_opt = sorted(v for v in ops_all["tv_purchase"].dropna().unique() if v)
    tv_sel: list[str] = st.multiselect(
        "TV購入", tv_opt,
        help='"TV" / "TV以外" の絞り込み（該当列があるブランドのみ）',
    ) if tv_opt else []

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
    tv_purchase=tv_sel or None,
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
        tv_purchase=tv_sel or None,
    )

# ─────────────────────────────────────────────
# 🏷 ブランド切替（マルチブランド時のみページ最上部にピル型で表示）
# ─────────────────────────────────────────────
if _MULTI_BRAND:
    # segmented_control は Streamlit 1.42+。widget は key="selected_brand" で
    # session_state に書き込むので、次リランで冒頭のコンテキスト決定処理が拾う。
    _picker = getattr(st, "segmented_control", None) or getattr(st, "pills", None)
    if _picker is not None:
        _picker(
            "ブランド",
            _brand_keys,
            format_func=lambda k: _BRANDS_CONFIG[k]["display_name"],
            default=_selected_brand_key,
            selection_mode="single",
            key="selected_brand",
            label_visibility="collapsed",
            help="4ブランド切替。初回選択時のみ読込み、以降10分キャッシュで即表示。",
        )
    else:
        # 極古 Streamlit のフォールバック
        st.radio(
            "ブランド", _brand_keys,
            index=_brand_keys.index(_selected_brand_key),
            format_func=lambda k: _BRANDS_CONFIG[k]["display_name"],
            key="selected_brand", horizontal=True, label_visibility="collapsed",
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

# ─────────────────────────────────────────────
# 🔌 回線管理表（全ブランド共通・Secrets の [shared] に URL を書いた時のみ表示）
# 曜日×時間帯の複雑な集計表は Google Sheets の見た目そのままが読みやすいので iframe 埋め込み
# ─────────────────────────────────────────────
_shared_cfg: dict = load_shared_config()
_line_mgmt_url: str = _shared_cfg.get("line_management_url", "")
if _line_mgmt_url:
    with st.expander("🔌 全ブランド共通 回線管理表を開く"):
        # pubhtml URL に `?widget=true&headers=false` を付けると余白の少ないビューになる
        _embed_url = _line_mgmt_url
        if "widget=true" not in _embed_url:
            _sep = "&" if "?" in _embed_url else "?"
            _embed_url = f"{_embed_url}{_sep}widget=true&headers=false"
        import streamlit.components.v1 as _components
        _components.iframe(_embed_url, height=650, scrolling=True)
        st.caption(
            f"※ 元シートを直接開く: [Google Sheets で見る]({_line_mgmt_url})"
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
# 特別コース名: secrets 明示指定 > データから自動検出 の順で採用
_special_course = _special_course_override or metrics.detect_special_course_name(fdf)
_emoji = (
    "🌙" if "晩酌" in _special_course
    else "🌈" if ("すまいる" in _special_course or "スマイル" in _special_course)
    else "💎" if ("プレミアム" in _special_course or "シークレット" in _special_course)
    else "🌟"
)
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
        "お子様の年齢（数値入力）を分析します。**表示単位**で「個別年齢（0歳・1歳…）」と "
        "「学校区分（0-2歳 / 幼稚園 / 小学校低学年・高学年 / 中学生 / 高校生以上）」を切替でき、"
        "**学校区分フィルタ**で特定の年齢層に絞った深掘りも可能です。"
    )

    # ─────────────── 切替 UI ───────────────
    _ui_cols = st.columns([2, 3])
    with _ui_cols[0]:
        _age_view = st.radio(
            "表示単位",
            options=["個別年齢", "学校区分"],
            horizontal=True,
            index=0,
            key="age_view_mode",
        )
    with _ui_cols[1]:
        _group_filter = st.multiselect(
            "学校区分で絞り込み（空 = 全区分）",
            options=[g for g in AGE_GROUP_ORDER if g != "不明"] + ["不明"],
            default=[],
            key="age_group_filter",
        )

    _age_col = "child_age_label" if _age_view == "個別年齢" else "child_age_bucket"
    # 学校区分フィルタを事前適用（両モード共通）
    _fdf_age = metrics.apply_age_group_filter(fdf, _group_filter or None)

    if not metrics.has_child_age_data(_fdf_age):
        st.info("このフィルタでは年齢データがありません。")
    else:
        def _grouped_bar(cross_df, group_col, title, height=380, x_angle=-30):
            if cross_df.empty:
                st.caption(f"{title}: 該当データがまだありません。")
                return
            _fig = _px.bar(
                cross_df.astype({"age": str, group_col: str}),
                x=group_col, y="count", color="age",
                barmode="group",
                title=title,
                labels={group_col: group_col, "count": "件数", "age": "年齢"},
            )
            _fig.update_layout(
                height=height, xaxis_tickangle=x_angle,
                legend=dict(orientation="h", y=-0.25),
            )
            st.plotly_chart(_fig, use_container_width=True)

        def _cross_table(cross_df, group_col):
            if cross_df.empty:
                return
            pivot = cross_df.pivot(
                index="age", columns=group_col, values="count"
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
            c1, c2 = st.columns([1, 1])
            with c1:
                st.plotly_chart(
                    charts.vertical_bar(
                        metrics.child_age_distribution(_fdf_age, age_col=_age_col)
                            .rename(columns={"age": "年齢"}),
                        "年齢", "count",
                        f"{_age_view} 別 応対件数",
                    ),
                    use_container_width=True,
                )
            with c2:
                _age_reten = metrics.child_age_retention(_fdf_age, age_col=_age_col)
                if not _age_reten.empty:
                    st.plotly_chart(
                        charts.retention_rate_bar(
                            _age_reten.rename(columns={"age": "年齢"}),
                            "年齢",
                            f"{_age_view} 別 継続応援 成功率",
                        ),
                        use_container_width=True,
                    )
                else:
                    st.info("継続応援の有効データがまだありません。")

            st.markdown(f"#### {_age_view} 別 総合サマリ")
            _summary = metrics.child_age_summary(_fdf_age, age_col=_age_col)
            if not _summary.empty:
                _show = _summary.copy()
                _show["解約率"] = _show["解約率"].apply(
                    lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "—"
                )
                _show["継続応援成功率"] = _show["継続応援成功率"].apply(
                    lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "—"
                )
                for c in ("応対件数", "解約件数", "新規初回解約",
                          "センターワード", "温度感上昇", "嬉しい声"):
                    _show[c] = _show[c].apply(lambda v: f"{int(v):,}")
                st.dataframe(_show, use_container_width=True, hide_index=True)

        # === 解約 ===
        with tab_age[1]:
            _cross = metrics.child_age_cross(
                _fdf_age, "cancel_reason",
                age_col=_age_col, exploded=True, top_n=15, filter_cancel=True,
            )
            _grouped_bar(_cross, "cancel_reason", f"{_age_view} × 解約理由 TOP15", height=440)
            with st.expander("📋 表で見る"):
                _cross_table(_cross, "cancel_reason")

        # === 定期回数 ===
        with tab_age[2]:
            _cross = metrics.child_age_cross(_fdf_age, "subscription_count", age_col=_age_col)
            if not _cross.empty:
                _cross["subscription_count"] = pd.Categorical(
                    _cross["subscription_count"],
                    categories=SUBSCRIPTION_ORDER, ordered=True,
                )
                _cross = _cross.sort_values(["subscription_count", "age"])
            _grouped_bar(_cross, "subscription_count", f"{_age_view} × 定期回数", x_angle=0)
            with st.expander("📋 表で見る"):
                _cross_table(_cross, "subscription_count")

        # === 問い合わせ内容 ===
        with tab_age[3]:
            _cross = metrics.child_age_cross(_fdf_age, "request_category", age_col=_age_col)
            _grouped_bar(_cross, "request_category", f"{_age_view} × 問い合わせ内容")
            with st.expander("📋 表で見る"):
                _cross_table(_cross, "request_category")

        # === 商品 ===
        with tab_age[4]:
            _cross = metrics.child_age_cross(
                _fdf_age, "product", age_col=_age_col, exploded=True, top_n=10,
            )
            _grouped_bar(_cross, "product", f"{_age_view} × 商品 TOP10", height=420)
            with st.expander("📋 表で見る"):
                _cross_table(_cross, "product")

        # === コース ===
        with tab_age[5]:
            _cross = metrics.child_age_cross(_fdf_age, "course", age_col=_age_col)
            _grouped_bar(_cross, "course", f"{_age_view} × コース", x_angle=0)
            with st.expander("📋 表で見る"):
                _cross_table(_cross, "course")

        # === すまいる応援 対応内容 ===
        with tab_age[6]:
            _cross = metrics.child_age_cross(_fdf_age, "banshaku_category", age_col=_age_col)
            _grouped_bar(_cross, "banshaku_category",
                         f"{_age_view} × すまいる応援対応内容", height=400)
            with st.expander("📋 表で見る"):
                _cross_table(_cross, "banshaku_category")

        # === VOC・センター系 ===
        with tab_age[7]:
            _cross_voc = metrics.child_age_cross(_fdf_age, "voc", age_col=_age_col)
            _grouped_bar(_cross_voc, "voc", f"{_age_view} × VOC", height=380)

            _cross_esc = metrics.child_age_cross(
                _fdf_age, "escalation_cause",
                age_col=_age_col, exploded=True, top_n=10,
            )
            _grouped_bar(_cross_esc, "escalation_cause",
                         f"{_age_view} × 温度感上昇 原因 TOP10", height=380)

            with st.expander("📋 表で見る"):
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
