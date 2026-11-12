"""4단계. 실제 크롤링 실행 + 진행상황 / 5단계. PDF 생성

작업(Job) 한 개가 하는 일
  1) 목차 읽기  2) 페이지별 수집(진행률 표시)  3) 장별 PDF 변환(진행률 표시)
  4) 표지·목차·본문 합치기  → 완성된 PDF 파일 경로를 job.pdf_path 에 기록

앱은 /jobs/{id} 를 주기적으로 불러 이 객체의 상태를 그대로 화면에 보여줍니다.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from .step2_config import JobConfig, settings, wikidocs_base
from .step3_crawler import Cancelled, CrawlError, TocItem, WikiClient, parse_page, parse_toc
from .step3_images import ImageEmbedder
from .step3_pdf_builder import (
    Chapter,
    merge_book,
    render_chapter,
    render_cover,
    render_toc,
    toc_start_numbers,
)

PHASE_LABEL = {
    "queued": "대기 중",
    "toc": "목차 읽는 중",
    "crawl": "페이지 수집 중",
    "render": "PDF 변환 중",
    "merge": "하나로 합치는 중",
    "done": "완료",
}


@dataclass
class Job:
    id: str
    cfg: JobConfig
    status: str = "queued"  # queued | running | done | error | cancelled
    phase: str = "queued"
    done: int = 0
    total: int = 0
    message: str = "대기 중"
    book_title: str = ""
    logs: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    pdf_path: str = ""
    pdf_pages: int = 0
    pdf_size: int = 0
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event)
    drive: dict = field(default_factory=lambda: {"status": "idle"})

    def log(self, text: str) -> None:
        self.logs.append(time.strftime("%H:%M:%S ") + text)
        del self.logs[:-40]

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def to_public(self) -> dict:
        d = {
            "id": self.id,
            "status": self.status,
            "phase": self.phase,
            "phase_label": PHASE_LABEL.get(self.phase, self.phase),
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "book_title": self.book_title,
            "output_name": self.cfg.output_name,
            "logs": self.logs[-12:],
            "failed": self.failed[:20],
            "failed_count": len(self.failed),
            "drive": self.drive,
        }
        if self.status == "done":
            d["pdf"] = {"name": self.cfg.output_name, "size": self.pdf_size, "pages": self.pdf_pages}
        return d


def _crumb(item: TocItem, by_id: dict[str, TocItem]) -> str:
    chain, cur, guard = [], item, 0
    while cur.parent_id and cur.parent_id in by_id and guard < 6:
        cur = by_id[cur.parent_id]
        chain.append(cur.title)
        guard += 1
    return " › ".join(reversed(chain))


def run_job(job: Job) -> None:
    cfg = job.cfg
    work = os.path.join(settings.work_dir, job.id)
    os.makedirs(work, exist_ok=True)
    job.status = "running"
    try:
        delay = max(cfg.delay_sec, settings.min_delay_sec)
        client = WikiClient(wikidocs_base(), delay, job.check_cancel)

        # ── 목차
        job.phase, job.message = "toc", "책 목차를 읽고 있습니다"
        title, items = parse_toc(client.get_html(cfg.book_url), wikidocs_base())
        if not items:
            raise CrawlError("목차를 찾지 못했습니다. 공개된 책 주소가 맞는지 확인해 주세요.")
        if cfg.max_pages:
            items = items[: cfg.max_pages]
        job.book_title, job.total = title, len(items)
        job.log(f"책 '{title}' — 문서 {len(items)}개")
        by_id = {it.id: it for it in items}

        # ── 수집
        job.phase, job.done = "crawl", 0
        embedder = ImageEmbedder(wikidocs_base()) if cfg.include_images else None
        collected: dict[str, tuple[str, str]] = {}  # id -> (본문 html, 실패 사유)
        streak = 0
        for i, it in enumerate(items, 1):
            job.check_cancel()
            job.message = f"({i}/{len(items)}) {it.title}"
            try:
                page = parse_page(client.get_html(it.url), it.url, it.title)
                body = page.html
                if embedder:
                    body = embedder.embed(body, page.images)
                else:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(body, "lxml")
                    for im in soup.find_all("img"):
                        im.decompose()
                    body = soup.body.decode_contents() if soup.body else body
                collected[it.id] = (body, "")
                streak = 0
            except CrawlError as e:
                collected[it.id] = ("", str(e))
                job.failed.append({"title": it.title, "reason": str(e)})
                job.log(f"실패: {it.title} — {e}")
                streak += 1
                if streak >= 5:
                    raise CrawlError(f"연속 5개 페이지 실패로 중단합니다. 마지막 사유: {e}")
            job.done = i
        if embedder and embedder.skipped:
            job.log(f"불러오지 못한 그림 {embedder.skipped}개는 문구로 대체했습니다")

        # ── 장별 PDF
        job.phase, job.done = "render", 0
        chapters: list[Chapter] = []
        for i, it in enumerate(items, 1):
            job.check_cancel()
            job.message = f"({i}/{len(items)}) {it.title}"
            body, fail = collected.pop(it.id)
            path = os.path.join(work, f"ch_{i:04d}.pdf")
            pages = render_chapter(it, body, _crumb(it, by_id), path, fail)
            chapters.append(Chapter(it, path, pages))
            job.done = i

        # ── 합치기
        job.phase, job.done, job.message = "merge", 0, "표지·목차를 만들고 하나로 합치고 있습니다"
        cover = os.path.join(work, "cover.pdf")
        render_cover(title, cfg.book_url, len(items), cover)
        toc_pdf: Optional[str] = None
        if cfg.include_toc:
            toc_pdf = os.path.join(work, "toc.pdf")
            toc_pages = render_toc(items, {}, toc_pdf)  # 쪽수 먼저 알아내기
            for _ in range(2):  # 번호를 넣은 뒤 쪽수가 달라지면 한 번 더
                nums = toc_start_numbers(chapters, 1, toc_pages)
                new_pages = render_toc(items, nums, toc_pdf)
                if new_pages == toc_pages:
                    break
                toc_pages = new_pages
        out = os.path.join(work, "book.pdf")
        total_pages = merge_book(
            title, cover, toc_pdf, chapters, out, work,
            progress=lambda d, t: (setattr(job, "done", d), setattr(job, "total", t)),
        )
        for ch in chapters:
            try:
                os.remove(ch.pdf_path)
            except OSError:
                pass

        job.pdf_path, job.pdf_pages = out, total_pages
        job.pdf_size = os.path.getsize(out)
        job.phase, job.status, job.message = "done", "done", "PDF가 완성되었습니다"
        job.log(f"완성: {total_pages}쪽, {job.pdf_size / 1024 / 1024:.1f}MB")
    except Cancelled:
        job.status, job.message = "cancelled", "사용자가 취소했습니다"
        shutil.rmtree(work, ignore_errors=True)
    except CrawlError as e:
        job.status, job.message = "error", str(e)
        job.log("오류: " + str(e))
    except Exception as e:  # 예상 밖 오류도 앱 화면에 이유가 보이게
        job.status, job.message = "error", f"{type(e).__name__}: {e}"
        job.log("오류: " + job.message)
    finally:
        job.finished = time.time()


class JobManager:
    """한 번에 한 작업만 실행합니다(무료 서버 메모리 보호). 나머지는 줄을 섭니다."""

    MAX_ACTIVE = 3

    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = threading.Lock()

    def submit(self, cfg: JobConfig) -> Job:
        self.purge()
        with self.lock:
            active = [j for j in self.jobs.values() if j.status in ("queued", "running")]
            if len(active) >= self.MAX_ACTIVE:
                raise CrawlError("진행 중인 작업이 너무 많습니다. 잠시 뒤에 다시 시도해 주세요.")
            job = Job(id=uuid.uuid4().hex[:12], cfg=cfg)
            self.jobs[job.id] = job
        self.pool.submit(run_job, job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def purge(self) -> None:
        """오래된 작업과 파일을 지웁니다."""
        limit = settings.job_ttl_hours * 3600
        now = time.time()
        with self.lock:
            for jid in [j.id for j in self.jobs.values() if j.finished and now - j.finished > limit]:
                shutil.rmtree(os.path.join(settings.work_dir, jid), ignore_errors=True)
                del self.jobs[jid]


manager = JobManager()
