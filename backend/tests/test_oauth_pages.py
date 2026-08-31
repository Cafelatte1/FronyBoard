"""Rendered output of the OAuth browser pages (oauth_pages.py).

The only file that asserts on their wording — a copy change should break
nothing but this. The flow tests (test_oauth.py) check status codes and the
`class='result <kind>'` markers instead.
"""

from aira import oauth_pages


def _text(response):
    return response.body.decode()


def test_form_page_renders_login_and_deny_forms():
    page = oauth_pages.form_page("txn123", "Claude")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    text = _text(page)
    assert "Claude가<br>Frony 연결을 요청합니다" in text
    assert "Frony 계정으로 로그인" in text
    assert text.count("name='txn' value='txn123'") == 2  # login and deny both carry the txn
    assert "승인하고 연결" in text and "거부" in text
    assert "class='err'" not in text  # no error block on a fresh form


def test_form_page_shows_the_error_and_josa_follows_the_name():
    text = _text(oauth_pages.form_page("t", "구글", error="아이디 또는 비밀번호가 맞지 않아요. (1/5)"))
    assert "class='err'" in text and "(1/5)" in text
    assert "구글이<br>" in text  # final consonant -> '이'


def test_result_page_done_hands_the_browser_back():
    page = oauth_pages.result_page(
        "done", "Claude", "연결 완료", "Claude로 돌아가는 중입니다.", "→ app.example/cb?code=…",
        redirect="https://app.example/cb?code=s3cret&state=xyz")
    assert page.status_code == 200
    text = _text(page)
    assert "class='result done'" in text
    assert "content='1;url=https://app.example/cb?code=s3cret&amp;state=xyz'" in text
    assert "연결 완료" in text and "→ app.example/cb?code=…" in text


def test_result_page_terminal_kinds_and_status_codes():
    for kind, status in (("denied", 200), ("expired", 400), ("locked", 429)):
        page = oauth_pages.result_page(kind, None, "제목", "본문", "detail", status)
        assert page.status_code == status
        text = _text(page)
        assert f"class='result {kind}'" in text
        assert "http-equiv='refresh'" not in text  # no hand-off unless a redirect is given
        assert "앱이<br>" in text  # client_name=None falls back to '앱'


def test_pages_escape_what_they_are_given():
    text = _text(oauth_pages.form_page("'><script>", "<Evil&Co>"))
    assert "value=''><script>'" not in text  # the txn cannot break out of its attribute
    assert "value='&#x27;&gt;&lt;script&gt;'" in text
    assert "&lt;Evil&amp;Co&gt;" in text
    text = _text(oauth_pages.result_page("done", "x", "<b>제목</b>", "본문&", "<i>detail</i>"))
    assert "<b>" not in text and "<i>" not in text


def test_redirect_detail_masks_the_code():
    assert oauth_pages.redirect_detail(
        "https://app.example/cb?code=s3cret&state=xyz") == "→ app.example/cb?code=…"
    assert oauth_pages.redirect_detail(
        "https://app.example/cb?error=access_denied&state=xyz") == "→ app.example/cb?error=access_denied"
