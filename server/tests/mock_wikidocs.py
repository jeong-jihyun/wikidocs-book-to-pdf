"""시험용 가짜 위키독스 서버.

실제 위키독스의 HTML 구조(a.toc-item[data-id], div.page-content, pre>code>button 등)를 흉내 냅니다.
내용은 직접 지어낸 글이며 실제 책의 내용을 복사하지 않았습니다.
"""
from __future__ import annotations

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

BOOK_ID = "9999"
# (id, 제목, depth, parent)
TOC = [
    ("1001", "01 시작하기", 0, ""),
    ("1002", "설치 방법", 1, "1001"),
    ("1003", "첫 번째 예제", 1, "1001"),
    ("1004", "고급 설정 (옵션 ✅)", 2, "1003"),
    ("1005", "02 활용하기", 0, ""),
    ("1006", "표와 목록", 1, "1005"),
    ("1007", "없는 페이지 (404 시험)", 1, "1005"),
    ("1008", "그림이 깨진 페이지", 1, "1005"),
]


def _png(w=1600, h=900) -> bytes:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for x in range(0, w, 4):
        for y in range(0, h, 4):
            px[x, y] = (x * 255 // w, y * 255 // h, 128)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


PNG = _png()


def toc_html() -> str:
    links = "".join(
        f'<a href="/{pid}" class="list-group-item toc-item " data-wikidocs-reader-link="" '
        f'data-id="{pid}" data-parent-id="{par}" data-depth="{d}"><span style="white-space:nowrap">{title}</span></a>'
        for pid, title, d, par in TOC
    )
    return (
        '<!DOCTYPE html><html lang="ko"><head><meta property="og:title" content="시험용 가상 책">'
        "<title>시험용 가상 책 - WikiDocs</title></head><body>"
        f'<div class="scrollable-content">{links}</div></body></html>'
    )


def page_html(pid: str) -> str:
    title = next((t for i, t, _, _ in TOC if i == pid), "알 수 없음")
    body = {
        "1002": (
            "<p>이 문서는 <strong>설치 방법</strong>을 설명합니다. 한글과 English 가 섞여 있어도 잘 보여야 합니다.</p>"
            "<h2>1. 준비물</h2><ul><li>파이썬 3.12</li><li>인터넷 연결</li></ul>"
            '<pre><code class="hljs language-bash"><button class="md-csc-button btn"><span class="copymsg">Copy</span></button>'
            'pip install <span class="hljs-string">"weasyprint"</span>\npython main.py --help</code></pre>'
            '<script>alert("나쁜 스크립트")</script>'
        ),
        "1003": (
            "<h2>예제</h2><p>가로로 아주 긴 줄도 넘치지 않고 줄바꿈 되어야 합니다: "
            + "긴문장" * 40
            + "</p>"
            f'<img src="/img/big.png" alt="큰 그림"><blockquote><p>인용문도 보입니다.</p></blockquote>'
        ),
        "1004": "<h3>세부 항목</h3><p>이모지 ✅ 와 기호 → 도 확인합니다.</p>",
        "1006": (
            "<table><thead><tr><th>이름</th><th>설명</th></tr></thead>"
            "<tbody><tr><td>가</td><td>첫째</td></tr><tr><td>나</td><td>둘째</td></tr></tbody></table>"
            "<ol><li>하나</li><li>둘</li></ol>"
        ),
        "1008": '<p>그림이 없는 경우:</p><img src="/img/missing.png" alt="없는 그림"><p>뒷 문장.</p>',
    }.get(pid, "")
    return (
        '<!DOCTYPE html><html lang="ko"><head><title>x</title></head><body>'
        '<nav>메뉴 광고 로그인</nav><div class="container"><h1>'
        f"{title}</h1>"
        f'<div class="page-content tex2jax_process">{body}</div></div><footer>푸터</footer></body></html>'
    )


class Handler(BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *a):  # 조용히
        pass

    def _send(self, code: int, data: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        Handler.hits.append(self.path)
        p = self.path.split("?")[0]
        if p == "/robots.txt":
            return self._send(200, b"User-agent: *\nDisallow: /accounts/\nDisallow: /admin/\n", "text/plain")
        if p == f"/book/{BOOK_ID}":
            return self._send(200, toc_html().encode(), "text/html; charset=utf-8")
        if p == "/img/big.png":
            return self._send(200, PNG, "image/png")
        if p.startswith("/img/"):
            return self._send(404, b"no", "text/plain")
        pid = p.strip("/")
        if pid == "1007":
            return self._send(404, b"not found", "text/plain")
        if pid.isdigit() and any(pid == t[0] for t in TOC):
            return self._send(200, page_html(pid).encode(), "text/html; charset=utf-8")
        self._send(404, b"?", "text/plain")


def start() -> tuple[ThreadingHTTPServer, str]:
    Handler.hits = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
