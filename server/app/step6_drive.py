"""6단계. 구글 드라이브에 저장 (폴더는 모바일 앱에서 고름)

흐름
  앱 → POST /auth/google/start       : 로그인 주소를 받아 브라우저로 엽니다
  구글 → GET /auth/google/callback   : 서버가 코드를 받아 토큰으로 바꿔 보관(메모리)
  앱 → GET  /drive/folders           : 내 드라이브 폴더 목록을 보며 폴더 선택
  앱 → POST /jobs/{id}/drive         : 완성된 PDF 를 선택한 폴더에 올림

권한(scope): 기존에 있는 폴더 안에 파일을 만들려면 'drive' 권한이 필요합니다.
(drive.file 은 앱이 만든 폴더에만 쓸 수 있어 폴더 고르기에 맞지 않음)
토큰은 서버 메모리에만 있고 서버가 다시 시작되면 사라집니다(다시 로그인).
"""
from __future__ import annotations

import os
import re
import secrets
import threading
import time
from typing import Optional
from urllib.parse import urlencode

import requests

from .step2_config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "openid email https://www.googleapis.com/auth/drive"
FOLDER_MIME = "application/vnd.google-apps.folder"
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,100}$")


class DriveError(Exception):
    pass


class GoogleAuth:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()

    # ── 로그인 ──
    def configured(self) -> bool:
        return bool(settings.google_client_id and settings.google_client_secret and settings.public_base_url)

    def redirect_uri(self) -> str:
        return settings.public_base_url + "/auth/google/callback"

    def start(self) -> tuple[str, str]:
        if not self.configured():
            raise DriveError(
                "서버에 구글 로그인 설정이 없습니다. Render 환경변수 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET 을 넣어 주세요."
            )
        self._purge()
        sid, state = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        with self.lock:
            self.sessions[sid] = {"state": state, "created": time.time(), "tokens": None, "email": ""}
        q = urlencode({
            "client_id": settings.google_client_id,
            "redirect_uri": self.redirect_uri(),
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        })
        return sid, f"{AUTH_URL}?{q}"

    def callback(self, code: str, state: str) -> str:
        with self.lock:
            sid = next((k for k, v in self.sessions.items() if secrets.compare_digest(v["state"], state)), None)
            if not sid or time.time() - self.sessions[sid]["created"] > 600:
                raise DriveError("로그인 유효시간이 지났습니다. 앱에서 다시 시도해 주세요.")
            self.sessions[sid]["state"] = secrets.token_urlsafe(8)  # 한 번 쓰면 무효
        r = requests.post(TOKEN_URL, data={
            "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
            "redirect_uri": self.redirect_uri(), "grant_type": "authorization_code",
        }, timeout=20)
        if r.status_code != 200:
            raise DriveError("구글 로그인 확인에 실패했습니다: " + r.text[:200])
        tok = r.json()
        email = ""
        try:
            u = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=15)
            email = u.json().get("email", "") if u.status_code == 200 else ""
        except requests.RequestException:
            pass
        with self.lock:
            self.sessions[sid]["tokens"] = {
                "access": tok["access_token"],
                "refresh": tok.get("refresh_token", ""),
                "exp": time.time() + int(tok.get("expires_in", 3600)) - 60,
            }
            self.sessions[sid]["email"] = email
        return sid

    def info(self, sid: str) -> dict:
        s = self.sessions.get(sid)
        return {"signed_in": bool(s and s["tokens"]), "email": (s or {}).get("email", "")}

    def logout(self, sid: str) -> None:
        with self.lock:
            self.sessions.pop(sid, None)

    def _purge(self) -> None:
        now = time.time()
        with self.lock:
            for k in [k for k, v in self.sessions.items() if now - v["created"] > 24 * 3600]:
                del self.sessions[k]

    def token(self, sid: str) -> str:
        s = self.sessions.get(sid)
        if not s or not s["tokens"]:
            raise DriveError("구글에 로그인되어 있지 않습니다. 앱에서 다시 로그인해 주세요.")
        t = s["tokens"]
        if time.time() >= t["exp"]:
            if not t["refresh"]:
                raise DriveError("로그인이 만료되었습니다. 앱에서 다시 로그인해 주세요.")
            r = requests.post(TOKEN_URL, data={
                "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "refresh_token": t["refresh"], "grant_type": "refresh_token",
            }, timeout=20)
            if r.status_code != 200:
                raise DriveError("로그인이 만료되었습니다. 앱에서 다시 로그인해 주세요.")
            t["access"] = r.json()["access_token"]
            t["exp"] = time.time() + int(r.json().get("expires_in", 3600)) - 60
        return t["access"]

    # ── 폴더 목록 ──
    def _api(self, sid: str, method: str, url: str, **kw) -> requests.Response:
        r = requests.request(method, url, headers={"Authorization": f"Bearer {self.token(sid)}"}, timeout=30, **kw)
        if r.status_code == 401:
            raise DriveError("구글 로그인이 만료되었습니다. 앱에서 다시 로그인해 주세요.")
        if r.status_code == 403 and "insufficient" in r.text.lower():
            raise DriveError("드라이브 권한이 부족합니다. 로그아웃 후 다시 로그인하며 권한을 허용해 주세요.")
        return r

    def list_folders(self, sid: str, parent: str = "root") -> dict:
        if parent == "shared":
            q = f"sharedWithMe = true and mimeType = '{FOLDER_MIME}' and trashed = false"
        elif parent == "root" or _ID.match(parent):
            q = f"'{parent}' in parents and mimeType = '{FOLDER_MIME}' and trashed = false"
        else:
            raise DriveError("폴더 번호 형식이 올바르지 않습니다.")
        folders, token = [], None
        for _ in range(10):
            params = {
                "q": q, "fields": "nextPageToken,files(id,name)", "orderBy": "name", "pageSize": 100,
                "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
            }
            if token:
                params["pageToken"] = token
            r = self._api(sid, "GET", f"{DRIVE}/files", params=params)
            if r.status_code != 200:
                raise DriveError("폴더 목록을 가져오지 못했습니다: " + r.text[:200])
            j = r.json()
            folders += j.get("files", [])
            token = j.get("nextPageToken")
            if not token:
                break
        name = "내 드라이브" if parent == "root" else ("공유 문서함" if parent == "shared" else self.folder_name(sid, parent))
        return {"id": parent, "name": name, "folders": folders}

    def folder_name(self, sid: str, folder_id: str) -> str:
        r = self._api(sid, "GET", f"{DRIVE}/files/{folder_id}", params={"fields": "name", "supportsAllDrives": "true"})
        return r.json().get("name", folder_id) if r.status_code == 200 else folder_id

    # ── 올리기 ──
    def upload(self, sid: str, folder_id: str, path: str, name: str) -> dict:
        if folder_id != "root" and not _ID.match(folder_id):
            raise DriveError("폴더 번호 형식이 올바르지 않습니다.")
        size = os.path.getsize(path)
        meta = {"name": name, "mimeType": "application/pdf"}
        if folder_id != "root":
            meta["parents"] = [folder_id]
        init = requests.post(
            UPLOAD,
            params={"uploadType": "resumable", "supportsAllDrives": "true", "fields": "id,name,webViewLink"},
            headers={
                "Authorization": f"Bearer {self.token(sid)}",
                "X-Upload-Content-Type": "application/pdf",
                "X-Upload-Content-Length": str(size),
            },
            json=meta, timeout=30,
        )
        if init.status_code == 404:
            raise DriveError("선택한 폴더를 찾을 수 없거나 쓸 권한이 없습니다.")
        if init.status_code != 200 or "Location" not in init.headers:
            raise DriveError("드라이브 업로드를 시작하지 못했습니다: " + init.text[:200])
        with open(path, "rb") as f:
            put = requests.put(
                init.headers["Location"], data=f,
                headers={"Content-Type": "application/pdf", "Content-Length": str(size)},
                timeout=(15, 600),
            )
        if put.status_code not in (200, 201):
            raise DriveError("드라이브 업로드에 실패했습니다: " + put.text[:200])
        j = put.json()
        return {"file_id": j.get("id"), "name": j.get("name"), "link": j.get("webViewLink", "")}


google = GoogleAuth()
