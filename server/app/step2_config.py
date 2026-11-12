"""2단계. 설정값

앱(모바일)에서 입력한 값이 서버로 넘어오면 이 모델로 검사합니다.
서버 환경 설정(Render 환경변수)도 여기서 읽습니다.
"""
from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field, field_validator

VERSION = "1.0.0"


def wikidocs_base() -> str:
    """위키독스 기본 주소. 시험할 때만 환경변수로 바꿉니다."""
    return os.environ.get("WIKIDOCS_BASE", "https://wikidocs.net").rstrip("/")


class Settings:
    """서버 환경변수 모음 (Render 대시보드의 Environment 에서 입력)."""

    @property
    def api_key(self) -> str:
        return os.environ.get("API_KEY", "")

    @property
    def google_client_id(self) -> str:
        return os.environ.get("GOOGLE_CLIENT_ID", "")

    @property
    def google_client_secret(self) -> str:
        return os.environ.get("GOOGLE_CLIENT_SECRET", "")

    @property
    def public_base_url(self) -> str:
        # Render 는 RENDER_EXTERNAL_URL 을 자동으로 넣어 줍니다.
        url = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")
        return url.rstrip("/")

    @property
    def work_dir(self) -> str:
        return os.environ.get("WORK_DIR", "/tmp/wikidocs2pdf")

    @property
    def min_delay_sec(self) -> float:
        # 위키독스 서버에 부담을 주지 않기 위한 최소 요청 간격
        return float(os.environ.get("MIN_DELAY_SEC", "0.5"))

    @property
    def job_ttl_hours(self) -> float:
        return float(os.environ.get("JOB_TTL_HOURS", "6"))


settings = Settings()

_FORBIDDEN_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class JobConfig(BaseModel):
    """앱의 '2단계 설정값 입력' 화면과 1:1 로 대응합니다."""

    book_url: str = Field(..., description="예: https://wikidocs.net/book/17550")
    output_name: str = "wikidocs_book.pdf"
    max_pages: int = Field(0, ge=0, le=2000, description="0 = 전체, 숫자 = 앞에서부터 그 개수만(시험용)")
    delay_sec: float = Field(1.0, ge=0, le=30, description="페이지 요청 사이 대기(초)")
    include_toc: bool = True
    include_images: bool = True

    @field_validator("book_url")
    @classmethod
    def _check_book_url(cls, v: str) -> str:
        v = v.strip()
        m = re.fullmatch(re.escape(wikidocs_base()) + r"/book/(\d+)/?", v)
        if not m:
            raise ValueError("책 주소 형식이 아닙니다. 예: https://wikidocs.net/book/17550")
        return f"{wikidocs_base()}/book/{m.group(1)}"

    @field_validator("output_name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        v = _FORBIDDEN_NAME_CHARS.sub("_", (v or "").strip())
        if not v:
            v = "wikidocs_book"
        if not v.lower().endswith(".pdf"):
            v += ".pdf"
        if len(v) > 100:
            v = v[:96] + ".pdf"
        return v

    @property
    def book_id(self) -> str:
        return self.book_url.rsplit("/", 1)[-1]
