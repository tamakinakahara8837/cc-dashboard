# LU / N2 応対ダッシュボード

社内向けの Streamlit ダッシュボード。Google スプレッドシートから
LU / N2 の 2 シート（応対記録＋月次レート）を取得して可視化する。

## 機能サマリ

- **基本 KPI**: 応対件数 / 解約件数 / 解約率 / 新規初回解約
- **継続応援・センター系 KPI**: 継続応援 成功率、消費者センターワード、センター職員入電、消費者庁（0/将来向け）、温度感上昇、嬉しい声
- **🆚 コールセンター / オペレーター 比較**: 応対件数・解約率・継続応援成功率・センター件数・完了率・応答率
- **📞 発信・応答レート**: 完了率 / ユニーク完了率 / 応答率、**直近30日** 推移、チーム別（専任/クロコスマルチ/全体）、CC別
- **📈 推移**: 応対＋解約重ね折れ線、継続応援成功率、CC別・担当者別 山型
- **📊 内訳**: 問い合わせ内容カテゴリ(%表示・主要12＋その他) / 定期回数×解約 / 商品 / 解約理由 TOP15
- **🎯 継続応援 成功率の内訳**: コース / 定期回数 / 解約理由 / コールセンター / オペレーター
- **🌙 晩酌応援コース 内訳**: 満了解約 / 差額あり途中解約 / 差額なし途中解約 / 満了未満継続了承 / 満了継続応援成功
- **⚠️ センター系 件数の内訳**: 理由 / コース / 定期回数
- **💬 自由記述**: ネガ / ポジ タブ + キーワード検索
- **フィルタ**: 期間（日/週/月＋カスタム）、コールセンター、担当者、商品、コース、問い合わせ内容、定期回数
- **前期比**: KPI の delta 表示

## データソース

`data_loader.py` の `SHEETS` に登録済み:

```python
SHEETS = {
    "LU": ".../2PACX-1vTWiegDekNpBX51UlMNzcfdDolAalIj1vFFm5CZvsazIVIdqxyFYGxf2RjXuo_4y0lN4fjpzIyU7y8M",
    "N2": ".../2PACX-1vThXucwZtFi5pgYC0IODHVjgIAXJYy8Ntcip7YAqXOv5jmsEhmY02yD9YGWcs58qrRnpabFtpDbjOOx",
}
```

- **応対記録**タブから生ログを取得
- **月次タブ** (`YYYY年M月` パターン) は `/pubhtml` から**自動発見**。
  新しい月次タブを追加してもコード変更不要（次のリロードで拾う）
- `st.cache_data(ttl=600)` で 10 分キャッシュ。サイドバー「最新データに更新」で強制リロード

### スプレッドシート側の前提

- 「ファイル → 共有 → **ウェブに公開**」で全タブを公開
- タブ名は変更しない（`応対記録` / `YYYY年M月`）
- 月次タブは 3 行目にセクション見出し（専任 / クロコスマルチ / 全体）、
  4 行目にサブヘッダ（日付 / 曜日 / 完了率 / 総発数 / 完了数 / 応答率 / 入電数 / 応答数 / …）

## 認証について

**現在パスワード保護は無効**（誰でも URL からアクセス可能）です。
「URL を知っている人だけが入れる」運用を前提としています。

- URL は Slack など**社内限定チャネル**でのみ共有してください
- 公開が広がりすぎたと感じたら、以下のいずれかで復活可能:
  1. `app.py` 冒頭で `from auth import require_password` を追加し、`if not require_password(): st.stop()` を書く
  2. Streamlit Cloud の **Secrets** に `[auth] password = "..."` を追加

## ローカルで動かす

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

`http://localhost:8501` を開くだけで表示（パスワード不要）。

## Streamlit Community Cloud にデプロイ（推奨・無料）

### 1. GitHub にコードを push

このリポジトリ（`lu-dashboard/`）をそのまま GitHub に push します。

```bash
cd /Users/omoya223/lu-dashboard

# 初回のみ: リポジトリ初期化
git init
git add .
git commit -m "Initial commit: LU/N2 dashboard"

# GitHub にリポジトリを作成
# 方法A: GitHub CLI が入っている場合
gh repo create lu-dashboard --private --source=. --push

# 方法B: GitHub Web でリポジトリを作成 → 表示された URL をコピー
git remote add origin https://github.com/<YOUR_ACCOUNT>/lu-dashboard.git
git branch -M main
git push -u origin main
```

**リポジトリは private 推奨**（コードにスプレッドシート URL が含まれるため）。

### 2. Streamlit Community Cloud に接続

1. https://share.streamlit.io/ にアクセスして GitHub でサインイン
2. 右上「**Create app**」→「**Deploy a public app from GitHub**」
3. リポジトリ: `<YOUR_ACCOUNT>/lu-dashboard`
4. Branch: `main`
5. Main file path: `app.py`
6. 「**Deploy**」を押下

数分でビルドが完了し、`https://<好きな名前>.streamlit.app` の URL が発行されます。

### 3. 共有

発行された URL を Slack など社内チャネルで共有するだけ。ログイン不要でダッシュボードが開きます。

### 更新の運用

- コードを更新 → `git push` → Streamlit Cloud が自動的に再デプロイ
- 月次タブの追加はスプレッドシート側だけで完結（コード変更不要）

## Cloud Run にデプロイ（社内網限定・SSO 必須の場合）

Dockerfile 同梱済み。IAP や IAM で社内アクセス制限をかけたい場合に向く。

```bash
export PROJECT_ID=your-project
export REGION=asia-northeast1
export SERVICE=lu-dashboard

gcloud builds submit --tag "$REGION-docker.pkg.dev/$PROJECT_ID/apps/$SERVICE:latest"

gcloud run deploy $SERVICE \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/apps/$SERVICE:latest" \
  --region $REGION --platform managed \
  --no-allow-unauthenticated
```

- `--no-allow-unauthenticated` で公開せず、IAP を有効化して Google SSO / 社内 IP 制限
- Cloud IAM で `roles/run.invoker` を特定のアカウントに付与

## リポジトリ構成

```
lu-dashboard/
├── app.py                    # Streamlit エントリ／レイアウト
├── data_loader.py            # CSV 取得・キャッシュ・タブ自動発見・月次パース
├── metrics.py                # KPI 計算（応対記録・レート・比較・晩酌）
├── charts.py                 # Plotly チャート
├── auth.py                   # パスワードゲート（現在は未使用・任意で再有効化）
├── requirements.txt
├── Dockerfile                # Cloud Run 用
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example  # 認証復活時のテンプレ
├── .gitignore
└── README.md
```

## トラブルシューティング

**「応答率・完了率データを取得できませんでした」と出る**
- スプレッドシートの月次タブがウェブ公開されているか
- タブ名が `2026年7月` 形式（`YYYY年M月`）になっているか
- サイドバーの「最新データに更新」でキャッシュクリア

**ブラウザで日本語ラベルが変な単語に化ける**
- Chrome / Edge の自動翻訳がオンになっている可能性
- 右クリック → 「日本語に翻訳」のチェックを外す、または翻訳アイコンから「元の表示に戻す」

**シート構造が変わった**
- `data_loader.py` の `COLUMN_RENAME`（応対記録）、`MONTHLY_METRICS`、`TEAMS` を確認
