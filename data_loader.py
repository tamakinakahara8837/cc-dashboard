"""スプレッドシート取得・前処理。

対象は LU / N2 の 2 シート。それぞれに
- 「応対記録」タブ（1行1応対の生データ）
- 「YYYY年M月」タブ（日次の 応答率・完了率などの集計、月ごとに追加される）
がある。タブ一覧は `/pubhtml` を parse して自動発見するので、
月次タブが増えても設定変更は不要。

すべての取得は `st.cache_data(ttl=600)` で 10 分キャッシュ。
サイドバーの「最新に更新」ボタンから `st.cache_data.clear()` で強制リロードできる。
"""

from __future__ import annotations

import io
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
# シート定義
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# シート定義（デフォルトは hajuCS。他ブランドは Streamlit Cloud の Secrets で上書き）
# ─────────────────────────────────────────────

_DEFAULT_SHEETS: dict[str, str] = {
    "LU": (
        "https://docs.google.com/spreadsheets/d/e/"
        "2PACX-1vTWiegDekNpBX51UlMNzcfdDolAalIj1vFFm5CZvsazIVIdqxyFYGxf2RjXuo_4y0lN4fjpzIyU7y8M"
    ),
    "N2": (
        "https://docs.google.com/spreadsheets/d/e/"
        "2PACX-1vThXucwZtFi5pgYC0IODHVjgIAXJYy8Ntcip7YAqXOv5jmsEhmY02yD9YGWcs58qrRnpabFtpDbjOOx"
    ),
}

DEFAULT_BRAND_NAME = "hajuCS"


def _load_sheets_from_secrets() -> "dict[str, str]":
    """`st.secrets["sheets"]` からシート URL を読む。無ければデフォルトを返す。

    Secrets の書式例:
        [sheets]
        LU = "https://docs.google.com/spreadsheets/d/e/xxxxx"
        N2 = "https://docs.google.com/spreadsheets/d/e/yyyyy"

    Streamlit のバージョンにより `st.secrets` の挙動が異なるため、
    どの例外が飛んでも安全にデフォルトへフォールバックする。
    """
    default = dict(_DEFAULT_SHEETS)
    try:
        secrets_obj = getattr(st, "secrets", None)
        if secrets_obj is None:
            return default
        try:
            cfg = secrets_obj["sheets"]
        except Exception:
            return default
        if not cfg:
            return default
        result: dict[str, str] = {}
        try:
            for k, v in cfg.items():
                if v:
                    result[str(k)] = str(v)
        except Exception:
            return default
        return result if result else default
    except BaseException:
        return default


def load_brand_name() -> str:
    """`st.secrets["brand"]["name"]` からブランド名を読む。無ければデフォルト。"""
    try:
        secrets_obj = getattr(st, "secrets", None)
        if secrets_obj is None:
            return DEFAULT_BRAND_NAME
        try:
            name = secrets_obj["brand"]["name"]
        except Exception:
            return DEFAULT_BRAND_NAME
        return str(name) if name else DEFAULT_BRAND_NAME
    except BaseException:
        return DEFAULT_BRAND_NAME


# モジュール読み込み時に呼ぶが、内部で全例外を捕まえるので落ちない
SHEETS: dict[str, str] = _load_sheets_from_secrets()

OPS_TAB_NAME = "応対記録"
MONTHLY_TAB_PATTERN = re.compile(r"^\s*(\d{4})年\s*(\d{1,2})月\s*$")

# 応対記録タブの列名 → 英字キー
COLUMN_RENAME = {
    "タイムスタンプ": "timestamp",
    "担当者": "agent",
    "顧客番号　※未購入者・不明は「なし」": "customer_id",
    "商品名": "product",
    "お客様のご希望された内容を選択してください": "request",
    "ご注文いただいているコースを選択してください": "course",
    "定期回数をご選択ください": "subscription_count",
    "継続応援は行いましたか？": "retention_result",
    "晩酌対応内容": "banshaku_action",
    "対応内容": "banshaku_action",  # N2 側は「対応内容」表記
    "すまいる応援対応内容": "banshaku_action",  # Co-HeartCS はスマイル応援コース
    "解約希望理由を選択してください(複数選択可)": "cancel_reason",
    "VOCの入力があればお願いします！": "voc",
    "温度感が上がってしまった原因の選択をお願いします(複数選択可)": "escalation_cause",
    "内容を簡単にご記載ください(ネガ)": "note_negative",
    "嬉しい内容をご選択ください(複数選択可)": "positive_kind",
    "内容を簡単にご記載ください(ポジ)": "note_positive",
    "自薦する場合はリレーションのURLを貼ってください(しない場合は空欄で送信)": "relation_url",
}

SUBSCRIPTION_ORDER = ["初回", "2回目", "3回目", "4回目", "5回以上"]

TEAMS = ["専任", "クロコスマルチ", "全体"]

# 問い合わせ内容の主要カテゴリ（月次シート 4 行目の見出しに合わせる）。
# これに含まれない値はすべて「その他」に丸める。
REQUEST_MAIN_CATEGORIES: list[str] = [
    "解約",
    "新規注文",
    "発送日関連",
    "コース変更",
    "注文内容コース内容確認",
    "再開",
    "商品について",
    "支払い関連",
    "停止済み",
    "登録情報変更",
    "初回受取前停止不可",
    "即切りまちがいいたずら",
]
REQUEST_OTHER_LABEL = "その他"

# 特別コース対応内容カテゴリ
# hajuCS: 晩酌応援コース → 満了系5カテゴリ
# Co-HeartCS: すまいる応援コース → 満了系5 + スマイル開始前系3
BANSHAKU_ORDER: list[str] = [
    # 解約系
    "満了解約",
    "差額あり途中解約",
    "差額なし途中解約",
    "スマイル開始前解約",
    # 継続系
    "満了未満継続了承",
    "満了継続応援成功",
    "スマイル開始前継続了承",
    # 開始前ムーブ（コース変更）
    "スマイル開始前コース変更",
]
BANSHAKU_CANCEL_SET: set[str] = {
    "満了解約", "差額あり途中解約", "差額なし途中解約", "スマイル開始前解約",
}
BANSHAKU_RETENTION_SET: set[str] = {
    "満了未満継続了承", "満了継続応援成功", "スマイル開始前継続了承",
}
BANSHAKU_COURSE_CHANGE_SET: set[str] = {"スマイル開始前コース変更"}


# ─────────────────────────────────────────────
# 内部ユーティリティ
# ─────────────────────────────────────────────

def _normalize_header(h: str) -> str:
    """列名の先頭に混入している 'ß' などの記号を吸収するため、比較キーを正規化する。"""
    if h is None:
        return ""
    h = unicodedata.normalize("NFKC", h)
    return re.sub(r"^[^\w　-鿿]+", "", h).strip()


def _apply_rename(df: pd.DataFrame) -> pd.DataFrame:
    normalized_map = {_normalize_header(k): v for k, v in COLUMN_RENAME.items()}
    new_cols: dict[str, str] = {}
    for c in df.columns:
        key = _normalize_header(c)
        if key in normalized_map:
            new_cols[c] = normalized_map[key]
    return df.rename(columns=new_cols)


def _normalize_agent(agent: str) -> str:
    """担当者名の表記ゆれを吸収する。

    - 先頭の「ルー」「るう」（カタカナ・ひらがな）を「LU 」に置換
    - 前後の空白トリム
    """
    if not isinstance(agent, str):
        return ""
    s = agent.strip()
    s = re.sub(r"^(?:ルー|るう)\s*", "LU ", s)
    return s


def _extract_agent_display(agent: str) -> str:
    """担当者名（コールセンターのプレフィックスは call_center 列で持つので落とす）。"""
    if not isinstance(agent, str):
        return ""
    return re.sub(r"^(LU|N2)\s*", "", agent.strip())


def _categorize_request(request: str) -> str:
    """お客様のご希望を主要カテゴリに丸める。複数選択（カンマ区切り）の場合は最初に該当したカテゴリを採用。"""
    if not isinstance(request, str) or not request.strip():
        return ""
    for part in (p.strip() for p in request.split(",")):
        if part in REQUEST_MAIN_CATEGORIES:
            return part
    return REQUEST_OTHER_LABEL


def _categorize_banshaku(value: str) -> str:
    """特別コース（晩酌応援 / すまいる応援）対応内容を分類。

    共通カテゴリ:
      - 満了解約
      - 差額あり途中解約 / 差額なし途中解約 （満了未満途中解約から派生）
      - 満了未満継続了承
      - 満了継続応援成功

    Co-HeartCS 固有:
      - スマイル開始前解約
      - スマイル開始前継続了承
      - スマイル開始前コース変更
    """
    if not isinstance(value, str) or not value.strip():
        return ""
    v = value.strip()
    # 共通カテゴリ
    if v == "満了解約":
        return "満了解約"
    if v == "満了未満継続了承":
        return "満了未満継続了承"
    if v == "満了継続応援成功":
        return "満了継続応援成功"
    if "満了未満途中解約" in v:
        return "差額なし途中解約" if "差額なし" in v else "差額あり途中解約"
    # Co-HeartCS 固有（スマイル開始前）
    if "スマイル開始前" in v or "すまいる開始前" in v:
        if "解約" in v:
            return "スマイル開始前解約"
        if "継続了承" in v or "継続" in v:
            return "スマイル開始前継続了承"
        if "コース変更" in v or "変更" in v:
            return "スマイル開始前コース変更"
    return REQUEST_OTHER_LABEL


def _parse_pct(s: str) -> Optional[float]:
    """'99.11%' → 0.9911。 '-' / 空 は None。"""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s == "-":
        return None
    s = s.rstrip("%")
    try:
        return float(s) / 100.0
    except ValueError:
        return None


def _parse_int(s: str) -> Optional[int]:
    if s is None:
        return None
    s = str(s).strip()
    if not s or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _http_get(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8")


# ─────────────────────────────────────────────
# タブ発見
# ─────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def discover_tabs(pub_base: str) -> dict[str, str]:
    """公開シートの `/pubhtml` を parse して {タブ名: gid} を返す。"""
    html = _http_get(f"{pub_base}/pubhtml")
    entries = re.findall(r'items\.push\(\{name:\s*"([^"]+)",[^}]*gid:\s*"(\d+)"', html)
    return {name.strip(): gid for name, gid in entries}


def _csv_url(pub_base: str, gid: str) -> str:
    return f"{pub_base}/pub?gid={gid}&single=true&output=csv"


# ─────────────────────────────────────────────
# 応対記録タブ
# ─────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _load_ops_one(pub_base: str, gid: str, call_center: str) -> pd.DataFrame:
    df = pd.read_csv(_csv_url(pub_base, gid), dtype=str, keep_default_na=False)
    df = _apply_rename(df)
    keep = [c for c in df.columns if c in set(COLUMN_RENAME.values())]
    df = df[keep].copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)
    df["date"] = df["timestamp"].dt.normalize()
    df["week"] = df["timestamp"].dt.to_period("W-MON").dt.start_time
    df["month"] = df["timestamp"].dt.to_period("M").dt.start_time

    df["call_center"] = call_center
    df["agent"] = df["agent"].map(_normalize_agent)
    df["agent_name"] = df["agent"].map(_extract_agent_display)

    df["request_category"] = df["request"].map(_categorize_request)
    df["banshaku_category"] = df["banshaku_action"].map(_categorize_banshaku)

    df["is_cancel"] = df["request"].fillna("").str.contains("解約", na=False)
    df["is_first_time_cancel"] = df["is_cancel"] & (df["subscription_count"] == "初回")
    df["is_banshaku_retention"] = df["banshaku_category"].isin(BANSHAKU_RETENTION_SET)
    df["is_banshaku_cancel"] = df["banshaku_category"].isin(BANSHAKU_CANCEL_SET)

    df["retention_valid"] = df["retention_result"].isin(["成功", "失敗"])
    df["retention_success"] = df["retention_result"] == "成功"

    df["voc_center_word"] = df["voc"] == "消費者センターワードあり"
    df["voc_center_staff"] = df["voc"] == "消費者センター職員からの入電"
    df["voc_shohisho"] = df["voc"].fillna("").str.contains("消費者庁", na=False)
    df["voc_positive"] = df["voc"] == "嬉しいお声"
    df["voc_escalation"] = df["voc"] == "温度感高いなど難しかった応対"

    df["is_escalation"] = df["escalation_cause"].fillna("").str.strip() != ""

    return df


# ─────────────────────────────────────────────
# 月次タブ（応答率・完了率）
# ─────────────────────────────────────────────

# 各チームブロックの列オフセット（row3 の「日付/曜日」の後に続く）
# section header, sub header ペアで抽出するため、実際のパースでは行3のサブヘッダを使う
MONTHLY_METRICS = {
    "完了率": "completion_rate",
    "総発数": "total_dispatch",
    "完了数": "completion_count",
    "応答率": "response_rate",
    "入電数": "incoming_count",
    "応答数": "response_count",
    # ユニーク系（月次シート上は「全体」チームのみに存在）
    "ユニーク完了率": "unique_completion_rate",
    "ユニーク総発数": "unique_total_dispatch",
    "ユニーク完了数": "unique_completion_count",
}


@st.cache_data(ttl=600, show_spinner=False)
def _load_monthly_one(pub_base: str, gid: str, call_center: str, tab_name: str) -> pd.DataFrame:
    """月次タブ 1 個を長形式 DataFrame に変換する。

    各行: date, call_center, team(専任/クロコスマルチ/全体), completion_rate, response_rate, ...
    """
    raw = _http_get(_csv_url(pub_base, gid))
    rows = list(csv_reader_from_string(raw))
    if len(rows) < 5:
        return pd.DataFrame()

    section_row = rows[2]
    sub_row = rows[3]
    # マージセル想定でセクションを前方埋め
    filled_section: list[str] = []
    last = ""
    for s in section_row:
        s = (s or "").strip()
        if s:
            last = s
        filled_section.append(last)

    # (team, metric) → col_index
    col_map: dict[tuple[str, str], int] = {}
    for i, (sec, sub) in enumerate(zip(filled_section, sub_row)):
        sub = (sub or "").strip()
        if sec in TEAMS and sub in MONTHLY_METRICS:
            col_map[(sec, sub)] = i

    records: list[dict] = []
    for r in rows[4:]:
        if not r or not r[0]:
            continue
        # 日付は "2026年07月01日" 形式
        m = re.match(r"^\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", r[0])
        if not m:
            continue
        y, mo, d = map(int, m.groups())
        date = pd.Timestamp(year=y, month=mo, day=d)
        for team in TEAMS:
            row: dict = {
                "date": date,
                "call_center": call_center,
                "team": team,
                "source_tab": tab_name,
            }
            for jp_name, en_name in MONTHLY_METRICS.items():
                idx = col_map.get((team, jp_name))
                if idx is None or idx >= len(r):
                    row[en_name] = None
                    continue
                if jp_name.endswith("率"):
                    row[en_name] = _parse_pct(r[idx])
                else:
                    row[en_name] = _parse_int(r[idx])
            records.append(row)

    return pd.DataFrame.from_records(records)


def csv_reader_from_string(text: str):
    """CSV 文字列を row リストとして返す（csv モジュールを import せずに使うためのショートカット）。"""
    import csv
    return csv.reader(io.StringIO(text))


# ─────────────────────────────────────────────
# 統合ローダ
# ─────────────────────────────────────────────

@dataclass
class LoadResult:
    ops: pd.DataFrame          # 応対記録 (両シート結合、call_center 列付き)
    rates: pd.DataFrame        # 月次 応答率・完了率 (長形式)
    loaded_at: pd.Timestamp
    monthly_tabs: dict[str, list[str]]   # シート名 → 月次タブ名リスト


@st.cache_data(ttl=600, show_spinner="スプレッドシートを取得中…")
def load_data() -> LoadResult:
    ops_frames: list[pd.DataFrame] = []
    rate_frames: list[pd.DataFrame] = []
    monthly_tabs: dict[str, list[str]] = {}

    for cc, base in SHEETS.items():
        tabs = discover_tabs(base)

        # 応対記録
        ops_gid = tabs.get(OPS_TAB_NAME)
        if ops_gid:
            ops_frames.append(_load_ops_one(base, ops_gid, cc))

        # 月次タブ
        monthlys = [
            (name, gid) for name, gid in tabs.items()
            if MONTHLY_TAB_PATTERN.match(name)
        ]
        # 名前順（YYYY年M月）でソート
        def _key(item):
            m = MONTHLY_TAB_PATTERN.match(item[0])
            return (int(m.group(1)), int(m.group(2)))
        monthlys.sort(key=_key)
        monthly_tabs[cc] = [name for name, _ in monthlys]

        for name, gid in monthlys:
            frame = _load_monthly_one(base, gid, cc, name)
            if not frame.empty:
                rate_frames.append(frame)

    ops = (
        pd.concat(ops_frames, ignore_index=True)
        if ops_frames else pd.DataFrame()
    )
    rates = (
        pd.concat(rate_frames, ignore_index=True)
        if rate_frames else pd.DataFrame()
    )

    return LoadResult(
        ops=ops,
        rates=rates,
        loaded_at=pd.Timestamp.now(tz="Asia/Tokyo"),
        monthly_tabs=monthly_tabs,
    )


# ─────────────────────────────────────────────
# フィルタ / 補助
# ─────────────────────────────────────────────

def explode_multi(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """カンマ区切りの複数選択セルを行に展開。"""
    if column not in df.columns or df.empty:
        return df.iloc[0:0].copy() if not df.empty else pd.DataFrame(columns=[column])
    tmp = df.copy()
    tmp[column] = tmp[column].fillna("").str.split(r"\s*,\s*")
    tmp = tmp.explode(column)
    tmp[column] = tmp[column].str.strip()
    return tmp[tmp[column] != ""].reset_index(drop=True)


def apply_ops_filters(
    df: pd.DataFrame,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
    call_centers: Optional[list[str]] = None,
    agents: Optional[list[str]] = None,
    products: Optional[list[str]] = None,
    courses: Optional[list[str]] = None,
    requests: Optional[list[str]] = None,
    subscription_counts: Optional[list[str]] = None,
) -> pd.DataFrame:
    out = df
    if date_from is not None:
        out = out[out["date"] >= pd.Timestamp(date_from)]
    if date_to is not None:
        end = pd.Timestamp(date_to) + pd.Timedelta(days=1)
        out = out[out["timestamp"] < end]
    if call_centers:
        out = out[out["call_center"].isin(call_centers)]
    if agents:
        out = out[out["agent"].isin(agents)]
    if courses:
        out = out[out["course"].isin(courses)]
    if requests:
        # request_category（主要カテゴリに丸めた値）で一致判定
        out = out[out["request_category"].isin(requests)]
    if subscription_counts:
        out = out[out["subscription_count"].isin(subscription_counts)]
    if products:
        pat = "|".join(re.escape(p) for p in products)
        out = out[out["product"].fillna("").str.contains(pat, regex=True)]
    return out.reset_index(drop=True)


def apply_rate_filters(
    df: pd.DataFrame,
    *,
    date_from: Optional[pd.Timestamp] = None,
    date_to: Optional[pd.Timestamp] = None,
    call_centers: Optional[list[str]] = None,
    teams: Optional[list[str]] = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if date_from is not None:
        out = out[out["date"] >= pd.Timestamp(date_from)]
    if date_to is not None:
        out = out[out["date"] <= pd.Timestamp(date_to)]
    if call_centers:
        out = out[out["call_center"].isin(call_centers)]
    if teams:
        out = out[out["team"].isin(teams)]
    return out.reset_index(drop=True)


def previous_period(
    date_from: pd.Timestamp, date_to: pd.Timestamp
) -> tuple[pd.Timestamp, pd.Timestamp]:
    date_from = pd.Timestamp(date_from)
    date_to = pd.Timestamp(date_to)
    length = date_to - date_from
    prev_to = date_from - pd.Timedelta(days=1)
    prev_from = prev_to - length
    return prev_from, prev_to
