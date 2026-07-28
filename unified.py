"""4ブランド統合ダッシュボード用のエントリポイント。

Streamlit Community Cloud は `(repo, branch, main_file)` の一意性を要求するため、
既存の 3 個の単一ブランドデプロイ（`app.py` = hajuCS / `main.py` = Co-HeartCS /
`main2.py` = TOARUHI）と衝突しないよう、統合版はこのファイルをメインに指定する。

中身は `app.py` を丸ごと実行するだけ。
Secrets に `[brands.<key>]` セクションを複数書けば、
サイドバーにブランド切替 selectbox が自動表示される（マルチブランドモード）。
"""

from pathlib import Path

_APP_PY = Path(__file__).with_name("app.py")
exec(
    compile(_APP_PY.read_text(encoding="utf-8"), str(_APP_PY), "exec"),
    {"__name__": "__main__", "__file__": str(_APP_PY)},
)
