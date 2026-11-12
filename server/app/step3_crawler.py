"""3단계(앞부분). 크롤러

- 책 메인 페이지에서 목차를 읽고
- 각 페이지에서 본문(div.page-content)만 뽑아 안전한 HTML 로 정리합니다.

위키독스 실제 구조(2026-11 확인)
  목차  : <a class="toc-item" data-id="278668" data-depth="0" data-parent-id="" href="https://wikidocs.net/278668">
  본문  : <div class="page-content"> ... </div>   (제목 h1 은 그 바깥)
  코드  : <pre><code class="hljs language-bash"><button class="md-csc-button">Copy</button> ... </code></pre>
         → 'Copy' 버튼 글자가 코드 안에 섞여 있어서 반드시 지워야 함
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Comment

USER_AGENT = "Mozilla/5.0 (compatible; wikidocs-book-to-pdf/1.0; personal-use pdf converter)"


class CrawlError(Exception):
    """사용자에게 그대로 보여줘도 되는 오류 메시지를 담습니다."""


class Cancelled(Exception):
    pass


@dataclass
class TocItem:
    id: str
    title: str
    depth: int
    parent_id: str
    url: str


@dataclass
class PageContent:
    title: str
    html: str  # 정리된 본문 HTML (이미지 주소는 아직 원본 그대로)
    images: list[str] = field(default_factory=list)


# ───────────────────────── HTTP ─────────────────────────
class WikiClient:
    def __init__(self, base: str, delay: float, cancel_check: Optional[Callable[[], None]] = None):
        self.base = base.rstrip("/")
        self.delay = delay
        self.cancel_check = cancel_check or (lambda: None)
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5"}
        )
        self._last = 0.0
        self._robots = self._load_robots()

    def _load_robots(self) -> RobotFileParser:
        rp = RobotFileParser()
        try:
            r = self.session.get(self.base + "/robots.txt", timeout=15)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp.parse([])  # 없으면 제한 없음
        except requests.RequestException:
            rp.parse([])
        return rp

    def allowed(self, url: str) -> bool:
        return self._robots.can_fetch(USER_AGENT, url)

    def _wait(self) -> None:
        gap = self.delay - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    def get_html(self, url: str) -> str:
        if urlparse(url).netloc != urlparse(self.base).netloc:
            raise CrawlError("위키독스 주소만 가져올 수 있습니다.")
        if not self.allowed(url):
            raise CrawlError("사이트의 robots.txt 가 이 주소의 수집을 허용하지 않습니다.")
        last_err = ""
        for attempt in range(3):
            self.cancel_check()
            self._wait()
            try:
                r = self.session.get(url, timeout=(10, 30))
            except requests.RequestException as e:
                last_err = f"접속 실패: {type(e).__name__}"
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200:
                r.encoding = "utf-8"
                return r.text
            if r.status_code == 404:
                raise CrawlError("페이지를 찾을 수 없습니다(404).")
            if r.status_code in (401, 403):
                raise CrawlError(f"접근이 거부되었습니다({r.status_code}). 로그인이 필요한 책이거나 서버 접속이 차단된 것입니다.")
            if r.status_code == 429:
                wait = min(int(r.headers.get("Retry-After", "10") or 10), 60)
                last_err = "요청이 너무 많다는 응답(429)"
                time.sleep(wait)
                continue
            last_err = f"서버 응답 {r.status_code}"
            time.sleep(2 * (attempt + 1))
        raise CrawlError(last_err or "알 수 없는 오류")


# ───────────────────────── 목차 ─────────────────────────
_JS_PAGE = re.compile(r"javascript:page\((\d+)\)")


def parse_toc(html: str, base: str) -> tuple[str, list[TocItem]]:
    soup = BeautifulSoup(html, "lxml")

    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        book_title = og["content"].strip()
    elif soup.title:
        book_title = re.sub(r"\s*-\s*WikiDocs\s*$", "", soup.title.get_text(strip=True))
    else:
        book_title = "WikiDocs Book"

    items: list[TocItem] = []
    seen: set[str] = set()

    def add(pid: str, title: str, depth: int = 0, parent: str = "") -> None:
        if pid in seen or not title:
            return
        seen.add(pid)
        items.append(TocItem(pid, title, depth, parent, f"{base}/{pid}"))

    # 1순위: 실제 구조 (data-id / data-depth)
    for a in soup.select("a.toc-item[data-id]"):
        try:
            depth = int(a.get("data-depth") or 0)
        except ValueError:
            depth = 0
        add(a["data-id"], a.get_text(" ", strip=True), depth, a.get("data-parent-id") or "")

    # 2순위: javascript:page(ID) 형식 (다른 화면 방식 대비)
    if not items:
        for a in soup.find_all("a", href=_JS_PAGE):
            add(_JS_PAGE.search(a["href"]).group(1), a.get_text(" ", strip=True))

    # 3순위: /숫자 형식의 일반 링크
    if not items:
        pat = re.compile(r"^(?:" + re.escape(base) + r")?/(\d+)/?$")
        for a in soup.find_all("a", href=pat):
            add(pat.match(a["href"]).group(1), a.get_text(" ", strip=True))

    return book_title, items


# ───────────────────────── 본문 ─────────────────────────
_ALLOWED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "pre", "code", "blockquote",
    "hr", "br", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "img", "a", "strong", "b", "em", "i", "u", "s", "del", "ins", "sup", "sub", "span", "div",
    "figure", "figcaption", "dl", "dt", "dd", "kbd", "mark", "small", "details", "summary",
}
_DROP_TAGS = ["script", "style", "button", "form", "iframe", "object", "embed", "noscript",
              "input", "select", "textarea", "svg", "canvas", "video", "audio", "link", "meta"]
_KEEP_CLASS = re.compile(r"^(hljs|language-)")


def _content_root(soup: BeautifulSoup):
    for sel in ("div.page-content", "#load_content .page-content", "div.wikidocs-reader-main"):
        node = soup.select_one(sel)
        if node:
            return node
    return None


def parse_page(html: str, page_url: str, fallback_title: str = "") -> PageContent:
    soup = BeautifulSoup(html, "lxml")
    root = _content_root(soup)
    if root is None:
        raise CrawlError("본문 영역(div.page-content)을 찾지 못했습니다. 사이트 구조가 바뀌었을 수 있습니다.")

    h1 = soup.find("h1")
    title = (h1.get_text(" ", strip=True) if h1 else "") or fallback_title or page_url

    for c in root.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in root.find_all(_DROP_TAGS):
        t.decompose()
    for t in root.select(".md-csc-button, .copymsg, ins.adsbygoogle, .adsbygoogle"):
        t.decompose()

    images: list[str] = []
    for tag in list(root.find_all(True)):
        name = tag.name
        if name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue

        attrs: dict[str, str] = {}
        if name == "a":
            href = (tag.get("href") or "").strip()
            if href and not href.lower().startswith(("javascript:", "#")):
                attrs["href"] = urljoin(page_url, href)
        elif name == "img":
            src = (tag.get("src") or tag.get("data-src") or tag.get("data-original") or "").strip()
            if not src:
                tag.decompose()
                continue
            src = src if src.startswith("data:") else urljoin(page_url, src)
            attrs["src"] = src
            if not src.startswith("data:"):
                images.append(src)
            if tag.get("alt"):
                attrs["alt"] = tag["alt"]
        elif name in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if tag.get(k, "").isdigit():
                    attrs[k] = tag[k]
        if name in ("code", "span", "pre"):
            cls = [c for c in (tag.get("class") or []) if _KEEP_CLASS.match(c)]
            if cls:
                attrs["class"] = " ".join(cls)
        tag.attrs = attrs

    return PageContent(title=title, html=root.decode_contents(), images=images)
