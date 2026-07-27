"""マルチブランドデプロイ用の代替エントリポイント（3ブランド目）。

Streamlit Community Cloud は「同一リポジトリ + 同一ブランチ + 同一メインファイル」
の組み合わせでアプリを2個以上作れない仕様のため、
プレミアム系ブランドはこのファイルをメインとして指定する。

中身は `app.py` を丸ごと実行するだけ。
"""

from pathlib import Path

_APP_PY = Path(__file__).with_name("app.py")
exec(
    compile(_APP_PY.read_text(encoding="utf-8"), str(_APP_PY), "exec"),
    {"__name__": "__main__", "__file__": str(_APP_PY)},
)
