"""3단계(뒷부분). PDF 만들기

장(페이지) 하나씩 PDF 로 만든 뒤 합칩니다. (한 번에 책 전체를 만들면 Render 무료 서버 메모리 512MB 가 모자랄 수 있음)
합치면서 표지 → 목차(쪽 번호 포함) → 본문 순서로 놓고, 북마크와 쪽 번호를 넣습니다.
"""
from __future__ import annotations

import html as htmllib
import io
from dataclasses import dataclass
from datetime import date
from typing import Callable

from pypdf import PdfReader, PdfWriter
from weasyprint import HTML

from .step3_crawler import TocItem

try:  # WeasyPrint 68 이상
    from weasyprint import URLFetcher

    _FETCHER = URLFetcher(allowed_protocols=["data"])  # PDF 만드는 동안엔 data: 주소 외 접속 금지
except ImportError:  # 구버전 호환
    from weasyprint import default_url_fetcher

    def _FETCHER(url, *args, **kwargs):
        if url.startswith("data:"):
            return default_url_fetcher(url, *args, **kwargs)
        raise ValueError("외부 주소 접속 차단: " + url[:60])

FONT_STACK = '"NanumGothic", "Noto Sans CJK KR", "Malgun Gothic", "Apple SD Gothic Neo", "DejaVu Sans", sans-serif'
MONO_STACK = '"NanumGothicCoding", "Noto Sans Mono CJK KR", "DejaVu Sans Mono", monospace'

BASE_CSS = f"""
@page {{ size: A4; margin: 20mm 17mm 22mm 17mm; }}
html {{ font-family: {FONT_STACK}; font-size: 10pt; line-height: 1.6; color: #1f2933; }}
body {{ margin: 0; }}
h1.chapter {{ font-size: 20pt; line-height: 1.3; margin: 0 0 4mm; color: #102a43; border-bottom: 2px solid #d9e2ec; padding-bottom: 3mm; }}
.crumb {{ font-size: 8.5pt; color: #829ab1; margin-bottom: 2mm; }}
h1, h2, h3, h4, h5, h6 {{ break-after: avoid; color: #243b53; }}
h2 {{ font-size: 15pt; margin: 8mm 0 3mm; }} h3 {{ font-size: 12.5pt; margin: 6mm 0 2mm; }} h4 {{ font-size: 11pt; }}
p {{ margin: 0 0 3mm; overflow-wrap: anywhere; }}
a {{ color: #1c64f2; text-decoration: none; overflow-wrap: anywhere; }}
ul, ol {{ margin: 0 0 3mm; padding-left: 6mm; }} li {{ margin-bottom: 1mm; }}
blockquote {{ margin: 3mm 0; padding: 2mm 4mm; border-left: 3px solid #9fb3c8; background: #f0f4f8; color: #486581; }}
blockquote p:last-child {{ margin-bottom: 0; }}
img {{ max-width: 100%; height: auto; display: block; margin: 3mm auto; }}
.img-missing {{ color: #9aa5b1; font-size: 8.5pt; }}
code {{ font-family: {MONO_STACK}; font-size: 9pt; background: #f0f4f8; padding: 0 1mm; border-radius: 1mm; }}
pre {{ background: #f6f8fa; border: 1px solid #d9e2ec; border-radius: 2mm; padding: 3mm; margin: 3mm 0; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8.6pt; line-height: 1.45; }}
pre code {{ background: none; padding: 0; font-size: inherit; }}
table {{ border-collapse: collapse; width: 100%; margin: 3mm 0; font-size: 9pt; }}
th, td {{ border: 1px solid #bcccdc; padding: 1.5mm 2.5mm; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #f0f4f8; }}
hr {{ border: 0; border-top: 1px solid #d9e2ec; margin: 5mm 0; }}
.empty {{ color: #9aa5b1; font-style: italic; }}
.fail {{ color: #b91c1c; background: #fef2f2; padding: 3mm; border-radius: 2mm; }}
.hljs-comment, .hljs-quote {{ color: #6b7c93; font-style: italic; }}
.hljs-keyword, .hljs-selector-tag, .hljs-built_in {{ color: #b3261e; }}
.hljs-string, .hljs-attr, .hljs-regexp {{ color: #0a7a3d; }}
.hljs-number, .hljs-literal {{ color: #0b6bcb; }}
.hljs-title, .hljs-function, .hljs-name {{ color: #7b3fb5; }}
.hljs-variable, .hljs-params {{ color: #9a5b00; }}
"""

COVER_CSS = """
.cover { text-align: center; padding-top: 70mm; }
.cover h1 { font-size: 28pt; line-height: 1.35; color: #102a43; margin: 0 0 8mm; }
.cover .rule { width: 60mm; border-top: 3px solid #1c64f2; margin: 0 auto 8mm; }
.cover .meta { color: #627d98; font-size: 11pt; margin-bottom: 2mm; }
.cover .note { color: #9aa5b1; font-size: 8.5pt; margin-top: 40mm; }
"""

TOC_CSS = """
.toc-title { font-size: 20pt; color: #102a43; margin: 0 0 6mm; border-bottom: 2px solid #d9e2ec; padding-bottom: 3mm; }
.row { font-size: 9.6pt; margin: 0 0 1.2mm; padding-bottom: 0.8mm; border-bottom: 1px dotted #cbd5e0; break-inside: avoid; overflow: hidden; }
.row .p { float: right; color: #486581; padding-left: 4mm; }
.row .t { overflow-wrap: anywhere; }
.row.d0 { font-weight: bold; margin-top: 2.5mm; } .row.d1 { padding-left: 5mm; } .row.d2 { padding-left: 10mm; color: #486581; }
.row.d3 { padding-left: 15mm; color: #486581; }
"""


def _esc(s: str) -> str:
    return htmllib.escape(s, quote=True)


def _write_pdf(html: str, out_path: str) -> int:
    HTML(string=html, url_fetcher=_FETCHER).write_pdf(out_path)
    return len(PdfReader(out_path).pages)


def _doc(body: str, css: str = "", header: str = "") -> str:
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f"<style>{BASE_CSS}{css}{header}</style></head><body>{body}</body></html>"
    )


def render_chapter(item: TocItem, body_html: str, crumb: str, out_path: str, failed_msg: str = "") -> int:
    """장 하나를 PDF 한 개로 만들고 쪽수를 돌려줍니다."""
    if failed_msg:
        inner = f'<p class="fail">이 페이지를 불러오지 못했습니다: {_esc(failed_msg)}</p>'
    elif not body_html.strip():
        inner = '<p class="empty">(본문 없음 — 하위 문서의 묶음 제목입니다)</p>'
    else:
        inner = body_html
    crumb_html = f'<div class="crumb">{_esc(crumb)}</div>' if crumb else ""
    body = f'{crumb_html}<h1 class="chapter">{_esc(item.title)}</h1>{inner}'
    return _write_pdf(_doc(body), out_path)


def render_cover(book_title: str, book_url: str, count: int, out_path: str) -> int:
    body = (
        '<div class="cover">'
        f"<h1>{_esc(book_title)}</h1><div class=\"rule\"></div>"
        f'<div class="meta">총 {count}개 문서</div>'
        f'<div class="meta">{_esc(book_url)}</div>'
        f'<div class="meta">변환일 {date.today().isoformat()}</div>'
        '<div class="note">개인 소장·오프라인 열람용으로 변환한 파일입니다.<br>저작권은 원저자에게 있으며 무단 배포할 수 없습니다.</div>'
        "</div>"
    )
    return _write_pdf(_doc(body, COVER_CSS), out_path)


def render_toc(items: list[TocItem], first_pages: dict[str, int], out_path: str) -> int:
    rows = []
    for it in items:
        d = min(max(it.depth, 0), 3)
        num = first_pages.get(it.id, 0)
        rows.append(
            f'<div class="row d{d}"><span class="p">{num if num else ""}</span>'
            f'<span class="t">{_esc(it.title)}</span></div>'
        )
    body = '<h1 class="toc-title">목 차</h1>' + "".join(rows)
    return _write_pdf(_doc(body, TOC_CSS), out_path)


def _overlay_numbers(total: int, skip_first: int, out_path: str) -> None:
    """쪽 번호만 그린 투명 PDF 를 만듭니다."""
    css = (
        "@page { size: A4; margin: 0; } body { margin: 0; } "
        ".pg { height: 297mm; width: 210mm; position: relative; break-after: page; } "
        ".n { position: absolute; bottom: 10mm; left: 0; right: 0; text-align: center; font-size: 9pt; color: #829ab1; }"
    )
    pages = "".join(
        f'<div class="pg"><div class="n">{i - skip_first + 1 if i >= skip_first else ""}</div></div>'
        for i in range(total)
    )
    HTML(string=_doc(pages, css), url_fetcher=_FETCHER).write_pdf(out_path)


@dataclass
class Chapter:
    item: TocItem
    pdf_path: str
    pages: int


def merge_book(
    book_title: str,
    cover_pdf: str,
    toc_pdf: str | None,
    chapters: list[Chapter],
    out_path: str,
    tmp_dir: str,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """표지·목차·장들을 하나로 합치고 북마크와 쪽 번호를 넣습니다. 전체 쪽수를 돌려줍니다."""
    writer = PdfWriter()
    for src in [cover_pdf] + ([toc_pdf] if toc_pdf else []):
        for pg in PdfReader(src).pages:
            writer.add_page(pg)

    outline_refs: dict[str, object] = {}
    for i, ch in enumerate(chapters):
        start = len(writer.pages)
        for pg in PdfReader(ch.pdf_path).pages:
            writer.add_page(pg)
        parent = outline_refs.get(ch.item.parent_id) if ch.item.parent_id else None
        outline_refs[ch.item.id] = writer.add_outline_item(ch.item.title, start, parent=parent)
        if progress:
            progress(i + 1, len(chapters))

    writer.add_metadata({"/Title": book_title, "/Author": "wikidocs.net", "/Creator": "wikidocs-book-to-pdf"})
    try:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except Exception:
        pass

    merged_tmp = f"{tmp_dir}/merged_raw.pdf"
    with open(merged_tmp, "wb") as f:
        writer.write(f)

    # 쪽 번호 찍기 (표지는 제외하고 목차부터 1)
    total = len(writer.pages)
    overlay_path = f"{tmp_dir}/numbers.pdf"
    _overlay_numbers(total, 1, overlay_path)
    base = PdfReader(merged_tmp)
    over = PdfReader(overlay_path)
    final = PdfWriter(clone_from=base)
    for idx in range(1, total):
        final.pages[idx].merge_page(over.pages[idx])
    final.add_metadata({"/Title": book_title, "/Author": "wikidocs.net", "/Creator": "wikidocs-book-to-pdf"})
    with open(out_path, "wb") as f:
        final.write(f)
    return total


def toc_start_numbers(chapters: list[Chapter], cover_pages: int, toc_pages: int) -> dict[str, int]:
    """목차에 적을 '시작 쪽 번호'(표지 제외, 목차 첫 쪽이 1)를 계산합니다."""
    nums: dict[str, int] = {}
    cur = toc_pages + 1  # 표지는 번호 없음, 목차가 1쪽부터라서 본문은 목차 쪽수 다음부터
    for ch in chapters:
        nums[ch.item.id] = cur
        cur += ch.pages
    return nums
