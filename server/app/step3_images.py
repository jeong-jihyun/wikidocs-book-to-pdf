"""3단계(중간). 이미지 내려받기

본문에 들어 있는 그림을 서버가 직접 받아 검사하고, 줄여서 data: 주소로 문서에 넣습니다.
이렇게 하면
  - PDF 를 만드는 단계에서 외부 접속이 전혀 필요 없고(서버가 엉뚱한 주소로 접속하는 일 차단),
  - 큰 그림 때문에 서버 메모리가 모자라는 일을 줄일 수 있습니다.
"""
from __future__ import annotations

import base64
import io
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

from .step3_crawler import USER_AGENT

MAX_BYTES = 8 * 1024 * 1024        # 그림 1장 최대 원본 크기
MAX_PX = 1100                      # 가로 최대 픽셀 (A4 본문 폭이면 충분)
TOTAL_CAP = 120 * 1024 * 1024      # 책 전체에 넣을 그림 총량 상한
MAX_REDIRECTS = 3


def _is_public_host(host: str, allow_hosts: set[str]) -> bool:
    if host in allow_hosts:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return False
    return bool(infos)


class ImageEmbedder:
    def __init__(self, base: str):
        self.allow_hosts = {urlparse(base).hostname or ""}
        self.cache: dict[str, str | None] = {}
        self.total = 0
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.skipped = 0

    def _download(self, url: str) -> tuple[bytes, str] | None:
        for _ in range(MAX_REDIRECTS + 1):
            p = urlparse(url)
            if p.scheme not in ("http", "https") or not p.hostname:
                return None
            if not _is_public_host(p.hostname, self.allow_hosts):
                return None
            r = self.session.get(url, stream=True, timeout=(8, 20), allow_redirects=False)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                url = urljoin(url, r.headers["Location"])
                r.close()
                continue
            if r.status_code != 200:
                r.close()
                return None
            ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                r.close()
                return None
            buf = bytearray()
            for chunk in r.iter_content(64 * 1024):
                buf.extend(chunk)
                if len(buf) > MAX_BYTES:
                    r.close()
                    return None
            return bytes(buf), ctype
        return None

    @staticmethod
    def _shrink(data: bytes, ctype: str) -> tuple[bytes, str] | None:
        if ctype == "image/svg+xml":
            return (data, ctype) if len(data) <= 512 * 1024 else None
        try:
            im = Image.open(io.BytesIO(data))
            im.load()
        except Exception:
            return None
        if im.width > MAX_PX:
            im = im.resize((MAX_PX, max(1, round(im.height * MAX_PX / im.width))), Image.LANCZOS)
        has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        out = io.BytesIO()
        if has_alpha or ctype in ("image/png", "image/gif"):
            im.convert("RGBA" if has_alpha else "RGB").save(out, "PNG", optimize=True)
            return out.getvalue(), "image/png"
        im.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue(), "image/jpeg"

    def to_data_uri(self, url: str) -> str | None:
        if url in self.cache:
            return self.cache[url]
        result = None
        try:
            got = self._download(url)
            if got:
                shrunk = self._shrink(*got)
                if shrunk and self.total + len(shrunk[0]) <= TOTAL_CAP:
                    self.total += len(shrunk[0])
                    result = f"data:{shrunk[1]};base64," + base64.b64encode(shrunk[0]).decode("ascii")
        except Exception:
            result = None
        if result is None:
            self.skipped += 1
        self.cache[url] = result
        return result

    def embed(self, html: str, urls: list[str]) -> str:
        """본문 HTML 안의 이미지 주소를 data: 주소로 바꿉니다. 못 받은 그림은 대체 문구로 바꿉니다."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src.startswith("data:"):
                continue
            uri = self.to_data_uri(src)
            if uri:
                img["src"] = uri
            else:
                note = soup.new_tag("span", attrs={"class": "img-missing"})
                note.string = f"[그림을 불러오지 못했습니다{': ' + img['alt'] if img.get('alt') else ''}]"
                img.replace_with(note)
        body = soup.body
        return body.decode_contents() if body else str(soup)
