"""서버 전체 흐름 시험 (가짜 위키독스 사용).  실행: cd server && python -m pytest -q"""
import io
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import mock_wikidocs as mock  # noqa: E402

KEY = {"X-API-Key": "testkey"}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    srv, base = mock.start()
    mp = pytest.MonkeyPatch()
    mp.setenv("WIKIDOCS_BASE", base)
    mp.setenv("API_KEY", "testkey")
    mp.setenv("MIN_DELAY_SEC", "0")
    mp.setenv("WORK_DIR", str(tmp_path_factory.mktemp("work")))
    mp.setenv("GOOGLE_CLIENT_ID", "cid")
    mp.setenv("GOOGLE_CLIENT_SECRET", "secret")
    mp.setenv("PUBLIC_BASE_URL", "https://example.onrender.com")
    yield base
    mp.undo()
    srv.shutdown()


@pytest.fixture(scope="module")
def client(env):
    from app.main import app

    return TestClient(app)


def wait_done(client, jid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/jobs/{jid}", headers=KEY).json()
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("시간 초과")


# ── 설정값 ──
def test_config_validation(env):
    from app.step2_config import JobConfig

    ok = JobConfig(book_url=f"{env}/book/9999/", output_name='a/b:c*.txt')
    assert ok.book_url == f"{env}/book/9999"
    assert ok.output_name.endswith(".pdf") and "/" not in ok.output_name and ":" not in ok.output_name
    for bad in ["https://evil.com/book/1", f"{env}/12345", f"{env}/book/abc", "javascript:alert(1)"]:
        with pytest.raises(Exception):
            JobConfig(book_url=bad)


# ── 파서 ──
def test_parsers(env):
    from app.step3_crawler import parse_page, parse_toc

    title, items = parse_toc(mock.toc_html(), env)
    assert title == "시험용 가상 책"
    assert [i.id for i in items][:2] == ["1001", "1002"]
    assert items[3].depth == 2 and items[3].parent_id == "1003"

    p = parse_page(mock.page_html("1002"), env + "/1002")
    assert p.title == "설치 방법"
    assert "Copy" not in p.html and "<script" not in p.html and "alert" not in p.html
    assert "hljs-string" in p.html and "pip install" in p.html
    assert "메뉴 광고" not in p.html  # 본문 밖 영역은 제외

    p = parse_page(mock.page_html("1003"), env + "/1003")
    assert p.images == [env + "/img/big.png"]


def test_parse_page_without_content_area_fails_loudly():
    from app.step3_crawler import CrawlError, parse_page

    with pytest.raises(CrawlError):
        parse_page("<html><body><h1>x</h1><p>본문 영역 없음</p></body></html>", "http://x/1")


# ── 인증 ──
def test_auth(client):
    assert client.get("/health").json()["ok"] is True
    assert client.get("/ping").status_code == 401
    assert client.get("/ping", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/ping", headers=KEY).status_code == 200
    r = client.post("/jobs", json={"book_url": "https://evil.com/book/1"}, headers=KEY)
    assert r.status_code == 422


# ── 전체 흐름 ──
def test_full_job(client, env):
    r = client.post("/jobs", headers=KEY, json={
        "book_url": f"{env}/book/9999", "output_name": "시험 책", "delay_sec": 0,
    })
    assert r.status_code == 200
    jid = r.json()["id"]
    j = wait_done(client, jid)
    assert j["status"] == "done", j
    assert j["total"] == 8 and j["book_title"] == "시험용 가상 책"
    assert j["failed_count"] == 1 and "404" in j["failed"][0]["reason"]
    assert j["pdf"]["name"] == "시험 책.pdf" and j["pdf"]["pages"] >= 10

    pdf = client.get(f"/jobs/{jid}/pdf", headers=KEY)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    rd = PdfReader(io.BytesIO(pdf.content))
    assert len(rd.pages) == j["pdf"]["pages"]

    text = "\n".join(p.extract_text() for p in rd.pages)
    for must in ["시험용 가상 책", "목 차", "설치 방법", "첫 번째 예제", "pip install", "인용문도 보입니다", "첫째", "둘째"]:
        assert must in text, must
    assert "Copy" not in text and "나쁜 스크립트" not in text
    assert "불러오지 못했습니다" in text          # 404 페이지 → 안내문
    assert "그림을 불러오지 못했습니다" in text    # 깨진 그림 → 대체 문구

    # 북마크 계층: 최상위 2개(01, 02), 첫째 아래에 2개
    top = [o for o in rd.outline if not isinstance(o, list)]
    assert [o.title for o in top] == ["01 시작하기", "02 활용하기"]
    # 큰 그림이 들어갔는지(그림 XObject 존재) + 축소되었는지
    found = []
    for p in rd.pages:
        xo = p["/Resources"].get("/XObject", {}) if "/Resources" in p else {}
        for k in xo:
            o = xo[k].get_object()
            if o.get("/Subtype") == "/Image":
                found.append((int(o["/Width"]), int(o["/Height"])))
    assert found and max(w for w, _ in found) <= 1100, found

    # 쪽 번호와 목차 번호: 표지 제외, 목차가 1쪽
    assert "1" in rd.pages[1].extract_text()

    # 서버가 위키독스 외 주소에 접속하지 않았는지는 mock 로그로 확인
    assert all(h.startswith(("/robots.txt", "/book/", "/img/", "/10")) for h in mock.Handler.hits)

    # 삭제
    assert client.delete(f"/jobs/{jid}", headers=KEY).status_code == 200
    assert client.get(f"/jobs/{jid}", headers=KEY).status_code == 404


def test_max_pages_and_no_toc_no_images(client, env):
    r = client.post("/jobs", headers=KEY, json={
        "book_url": f"{env}/book/9999", "max_pages": 2, "delay_sec": 0, "include_toc": False, "include_images": False,
    })
    j = wait_done(client, r.json()["id"])
    assert j["status"] == "done" and j["total"] == 2
    assert j["pdf"]["pages"] == 1 + 2 or j["pdf"]["pages"] >= 3  # 표지 + 장들(목차 없음)


def test_cancel(client, env):
    r = client.post("/jobs", headers=KEY, json={"book_url": f"{env}/book/9999", "delay_sec": 3})
    jid = r.json()["id"]
    time.sleep(1.0)
    client.delete(f"/jobs/{jid}", headers=KEY)
    j = wait_done(client, jid, timeout=30)
    assert j["status"] == "cancelled"


def test_missing_book_reports_error(client, env):
    r = client.post("/jobs", headers=KEY, json={"book_url": f"{env}/book/1234", "delay_sec": 0})
    j = wait_done(client, r.json()["id"])
    assert j["status"] == "error" and "404" in j["message"]


# ── 구글 로그인·드라이브 (구글 서버 대신 가짜 응답) ──
class FakeResp:
    def __init__(self, status=200, json=None, headers=None, text=""):
        self.status_code, self._j, self.headers, self.text = status, json or {}, headers or {}, text or str(json)

    def json(self):
        return self._j


def test_google_flow(client, tmp_path, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    from app import step6_drive as d

    r = client.post("/auth/google/start", headers=KEY).json()
    q = parse_qs(urlparse(r["url"]).query)
    assert q["client_id"] == ["cid"] and q["redirect_uri"] == ["https://example.onrender.com/auth/google/callback"]
    assert "https://www.googleapis.com/auth/drive" in q["scope"][0]
    sid, state = r["session_id"], q["state"][0]
    assert client.get(f"/auth/session/{sid}", headers=KEY).json()["signed_in"] is False

    calls = []

    def fake_post(url, **kw):
        calls.append(("POST", url, kw))
        if url == d.TOKEN_URL:
            return FakeResp(json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
        if url == d.UPLOAD:
            return FakeResp(headers={"Location": "https://upload.example/session1"})
        raise AssertionError(url)

    def fake_get(url, **kw):
        calls.append(("GET", url, kw))
        return FakeResp(json={"email": "me@example.com"})

    def fake_request(method, url, **kw):
        calls.append((method, url, kw))
        if url.endswith("/files") and method == "GET":
            return FakeResp(json={"files": [{"id": "f1", "name": "문서"}, {"id": "f2", "name": "책"}]})
        return FakeResp(json={"name": "문서"})

    def fake_put(url, data=None, **kw):
        calls.append(("PUT", url, kw))
        data.read()
        return FakeResp(json={"id": "file9", "name": "x.pdf", "webViewLink": "https://drive.google.com/file/d/file9"})

    monkeypatch.setattr(d.requests, "post", fake_post)
    monkeypatch.setattr(d.requests, "get", fake_get)
    monkeypatch.setattr(d.requests, "request", fake_request)
    monkeypatch.setattr(d.requests, "put", fake_put)

    # 잘못된 state → 거부
    assert client.get("/auth/google/callback?code=abc&state=nope").status_code == 400
    ok = client.get(f"/auth/google/callback?code=abc&state={state}")
    assert ok.status_code == 200 and "로그인 완료" in ok.text
    assert client.get(f"/auth/session/{sid}", headers=KEY).json() == {"signed_in": True, "email": "me@example.com"}
    # 같은 state 재사용 → 거부
    assert client.get(f"/auth/google/callback?code=abc&state={state}").status_code == 400

    f = client.get("/drive/folders", params={"session": sid, "parent": "root"}, headers=KEY).json()
    assert f["name"] == "내 드라이브" and [x["name"] for x in f["folders"]] == ["문서", "책"]
    list_q = [c for c in calls if c[0] == "GET" and c[1].endswith("/files")][-1][2]["params"]["q"]
    assert "'root' in parents" in list_q and "trashed = false" in list_q
    bad = client.get("/drive/folders", params={"session": sid, "parent": "x' or '1'='1"}, headers=KEY)
    assert bad.status_code == 400

    # 업로드: 작업을 하나 만들어 완료시킨 뒤
    jr = client.post("/jobs", headers=KEY, json={"book_url": f"{mock.start.__module__ and os.environ['WIKIDOCS_BASE']}/book/9999",
                                                    "max_pages": 1, "delay_sec": 0, "include_images": False})
    jid = jr.json()["id"]
    j = wait_done(client, jid)
    assert j["status"] == "done"
    r = client.post(f"/jobs/{jid}/drive", headers=KEY, json={"session_id": sid, "folder_id": "f2"})
    assert r.status_code == 200
    for _ in range(50):
        st = client.get(f"/jobs/{jid}", headers=KEY).json()["drive"]
        if st["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert st["status"] == "done" and st["file_id"] == "file9", st
    init = [c for c in calls if c[0] == "POST" and c[1] == d.UPLOAD][-1][2]
    assert init["json"]["parents"] == ["f2"] and init["json"]["name"] == j["output_name"]
