"""パスワード保護。`st.secrets["auth"]["password"]` と照合する。

社内限定運用のためのシンプルなゲート。ユーザーごとの識別はしない。
"""

from __future__ import annotations

import hmac
import time

import streamlit as st


def _get_configured_password() -> str | None:
    """secrets からパスワードを取得。未設定なら None。"""
    try:
        return st.secrets["auth"]["password"]
    except (KeyError, FileNotFoundError, AttributeError):
        return None


def require_password() -> bool:
    """認証済みなら True。未認証時はフォームを描画して False を返す。

    呼び出し側は `if not require_password(): st.stop()` の形で使う。
    """
    configured = _get_configured_password()
    if configured is None:
        st.error(
            "認証パスワードが設定されていません。"
            "`.streamlit/secrets.toml` に `[auth] password = \"...\"` を設定してください。"
        )
        return False

    if st.session_state.get("auth_ok"):
        return True

    # レートリミット（連続失敗時に少し待たせる）
    fails = st.session_state.get("auth_fails", 0)
    locked_until = st.session_state.get("auth_locked_until", 0)
    now = time.time()
    if locked_until and now < locked_until:
        wait = int(locked_until - now)
        st.error(f"連続失敗のため {wait} 秒お待ちください。")
        st.stop()

    st.markdown("## 🔒 社内ダッシュボード")
    st.caption("アクセスするにはパスワードを入力してください。")
    with st.form("auth_form", clear_on_submit=False):
        pw = st.text_input("パスワード", type="password", key="_pw_input")
        submitted = st.form_submit_button("ログイン")
    if submitted:
        if hmac.compare_digest(pw, configured):
            st.session_state["auth_ok"] = True
            st.session_state["auth_fails"] = 0
            st.rerun()
        else:
            fails += 1
            st.session_state["auth_fails"] = fails
            if fails >= 5:
                st.session_state["auth_locked_until"] = now + 60
                st.error("失敗が続いたため 60 秒ロックしました。")
            else:
                st.error(f"パスワードが違います（{fails}/5）。")
    return False
