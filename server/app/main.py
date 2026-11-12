"""서버 진입점 (FastAPI)

앱이 부르는 주소
  GET  /health                       서버 살아있는지 (인증 없음)
  GET  /ping                         API 키가 맞는지 확인
  POST /jobs                         변환 시작  (2단계 설정값을 받음)
  GET  /jobs/{id}                    진행 상황 (4단계)
  GET  /jobs/{id}/pdf                완성된 PDF 내려받기 (5단계)
  DELETE /jobs/{id}                  취소/삭제
  POST /auth/google/start            구글 로그인 시작 (6단계)
  GET  /auth/google/callback         구글이 돌려보내는 주소 (인증 없음, state 로 확인)
  GET  /auth/session/{sid}           로그인 됐는지
  GET  /drive/folders                폴더 목록
  POST /jobs/{id}/drive              선택한 폴더에 PDF 저장
"""
from __future__ import annotations

import html
import os
import secrets
import shutil
import threading

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .step2_config import VERSION, JobConfig, settings
from .step3_crawler import CrawlError
from .step4_runner import manager
from .step6_drive import DriveError, google

app = FastAPI(title="wikidocs-book-to-pdf", version=VERSION)


def require_key(x_api_key: str = Header(default="")) -> None:
    key = settings.api_key
    if not key:
        raise HTTPException(503, "서버에 API_KEY 환경변수가 설정되지 않았습니다.")
    if not secrets.compare_digest(x_api_key.encode(), key.encode()):
        raise HTTPException(401, "API 키가 올바르지 않습니다.")


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION, "google_configured": google.configured()}


@app.get("/ping", dependencies=[Depends(require_key)])
def ping():
    return {"ok": True, "google_configured": google.configured()}


# ── 변환 작업 ──
@app.post("/jobs", dependencies=[Depends(require_key)])
def create_job(cfg: JobConfig):
    try:
        job = manager.submit(cfg)
    except CrawlError as e:
        raise HTTPException(429, str(e))
    return {"id": job.id}


def _job(job_id: str):
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다(서버가 다시 시작되었거나 오래되어 삭제됨).")
    return job


@app.get("/jobs/{job_id}", dependencies=[Depends(require_key)])
def job_status(job_id: str):
    return _job(job_id).to_public()


@app.get("/jobs/{job_id}/pdf", dependencies=[Depends(require_key)])
def job_pdf(job_id: str):
    job = _job(job_id)
    if job.status != "done" or not os.path.exists(job.pdf_path):
        raise HTTPException(409, "아직 PDF가 완성되지 않았습니다.")
    return FileResponse(job.pdf_path, media_type="application/pdf", filename=job.cfg.output_name)


@app.delete("/jobs/{job_id}", dependencies=[Depends(require_key)])
def job_cancel(job_id: str):
    job = _job(job_id)
    if job.status in ("queued", "running"):
        job.cancel.set()
        return {"ok": True, "cancelling": True}
    shutil.rmtree(os.path.join(settings.work_dir, job.id), ignore_errors=True)
    manager.jobs.pop(job.id, None)
    return {"ok": True}


# ── 구글 로그인 / 드라이브 ──
@app.post("/auth/google/start", dependencies=[Depends(require_key)])
def google_start():
    try:
        sid, url = google.start()
    except DriveError as e:
        raise HTTPException(503, str(e))
    return {"session_id": sid, "url": url}


_PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{font-family:sans-serif;padding:28px;text-align:center;color:#102a43}}
a.b{{display:inline-block;margin-top:18px;padding:14px 22px;background:#1c64f2;color:#fff;border-radius:10px;text-decoration:none}}</style>
</head><body><h2>{title}</h2><p>{msg}</p>{button}</body></html>"""


@app.get("/auth/google/callback", response_class=HTMLResponse)
def google_callback(code: str = "", state: str = "", error: str = ""):
    if error or not code or not state:
        msg = html.escape(error or "로그인이 취소되었습니다.")
        return HTMLResponse(_PAGE.format(title="로그인 실패", msg=msg, button=""), status_code=400)
    try:
        google.callback(code, state)
    except DriveError as e:
        return HTMLResponse(_PAGE.format(title="로그인 실패", msg=html.escape(str(e)), button=""), status_code=400)
    return HTMLResponse(_PAGE.format(
        title="로그인 완료", msg="이 창을 닫고 앱으로 돌아가세요.",
        button='<a class="b" href="wikidocs2pdf://auth?ok=1">앱으로 돌아가기</a>'
               '<script>setTimeout(function(){location.href="wikidocs2pdf://auth?ok=1"},400)</script>',
    ))


@app.get("/auth/session/{sid}", dependencies=[Depends(require_key)])
def google_session(sid: str):
    return google.info(sid)


@app.delete("/auth/session/{sid}", dependencies=[Depends(require_key)])
def google_logout(sid: str):
    google.logout(sid)
    return {"ok": True}


@app.get("/drive/folders", dependencies=[Depends(require_key)])
def drive_folders(session: str = Query(...), parent: str = Query("root")):
    try:
        return google.list_folders(session, parent)
    except DriveError as e:
        raise HTTPException(400, str(e))


class DriveBody(BaseModel):
    session_id: str
    folder_id: str = "root"


def _upload_in_background(job, body: DriveBody) -> None:
    try:
        job.drive = {"status": "uploading", "message": "드라이브에 올리는 중"}
        res = google.upload(body.session_id, body.folder_id, job.pdf_path, job.cfg.output_name)
        job.drive = {"status": "done", **res}
    except DriveError as e:
        job.drive = {"status": "error", "message": str(e)}
    except Exception as e:
        job.drive = {"status": "error", "message": f"{type(e).__name__}: {e}"}


@app.post("/jobs/{job_id}/drive", dependencies=[Depends(require_key)])
def job_to_drive(job_id: str, body: DriveBody):
    job = _job(job_id)
    if job.status != "done" or not os.path.exists(job.pdf_path):
        raise HTTPException(409, "아직 PDF가 완성되지 않았습니다.")
    if job.drive.get("status") == "uploading":
        return job.drive
    job.drive = {"status": "uploading", "message": "드라이브에 올리는 중"}
    threading.Thread(target=_upload_in_background, args=(job, body), daemon=True).start()
    return job.drive
