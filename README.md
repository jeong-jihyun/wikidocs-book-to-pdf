# wikidocs-book-to-pdf

[WikiDocs](https://wikidocs.net) 책 주소를 넣으면 **모든 페이지를 모아 PDF 한 권**으로 만들어 주는 도구입니다.
무거운 작업(수집·변환)은 **서버**가 하고, **모바일 앱(React Native)** 에서 설정값을 입력하고 구글 드라이브 폴더를 지정하고 결과를 받습니다.

```
 폰 앱 (React Native) ──HTTPS──▶  변환 서버 (FastAPI, Render)  ──▶ wikidocs.net
   설정 입력 · 폴더 선택                수집 · PDF 변환 · 드라이브 업로드      (목차, 페이지, 그림)
   진행 확인 · PDF 받기 ◀────────  완성된 PDF
```

## 단계와 코드 위치

| 단계 | 내용 | 코드 |
|---|---|---|
| 1 | 패키지 설치 | `server/requirements.txt`, `server/Dockerfile`, `mobile/package.json` |
| 2 | ✏️ 설정값 입력 (URL, 파일명, 최대 페이지 수 …) | 앱 `mobile/src/screens/SettingsScreen.tsx` → 서버 `server/app/step2_config.py` |
| 3 | 크롤러 & PDF 빌더 | `server/app/step3_crawler.py`, `step3_images.py`, `step3_pdf_builder.py` |
| 4 | 크롤링 실행 + 진행상황 | 서버 `step4_runner.py` → 앱 `ProgressScreen.tsx` |
| 5 | PDF 생성 + 내려받기 | 서버 `GET /jobs/{id}/pdf` → 앱 `ResultScreen.tsx` |
| 6 | 구글 드라이브 저장 (폴더는 앱에서 지정) | 서버 `step6_drive.py` → 앱 `FolderPicker.tsx`, `ResultScreen.tsx` |

## 시작하기

처음이라면 **[docs/SETUP.md](docs/SETUP.md)** 를 순서대로 따라 하세요 (GitHub → Render 서버 → 구글 설정 → APK 설치 → 앱 사용).

- 서버 배포: 저장소 루트의 `render.yaml` (Render Blueprint)
- APK 빌드: `.github/workflows/build-apk.yml` — `mobile/` 이 바뀌어 `main` 에 올라가면 자동 빌드, Releases 의 **최신 테스트 APK** 에서 내려받기

## 개발·시험

```bash
# 서버 (가짜 위키독스로 전체 흐름 시험)
cd server
pip install -r requirements-dev.txt
python -m pytest -q

# 서버 직접 실행
API_KEY=내비밀키 uvicorn app.main:app --reload

# 앱
cd mobile
npm install
npx tsc --noEmit
npx expo export --platform android   # JS 번들이 만들어지는지 확인
```

WeasyPrint 는 시스템 라이브러리가 필요합니다. 특히 `libharfbuzz-subset` 이 없으면 PDF 변환이 수십 배 느려집니다 (Dockerfile 에 포함됨).
내 PC(Windows)에서 서버를 직접 돌리는 것보다 Docker 나 Render 를 권장합니다.

## 동작 규칙과 한계

- 위키독스 `robots.txt` 를 확인하고, 페이지 사이에 쉬는 시간(기본 1초, 최소 0.5초)을 둡니다. 접속자 정보(User-Agent)를 숨기지 않습니다.
- `wikidocs.net/book/숫자` 형식의 주소만 받습니다. 로그인이 필요한 비공개 책은 변환할 수 없습니다.
- 본인이 열람할 수 있는 책을 **개인 소장·오프라인 열람용**으로 변환하는 용도입니다. 저작권은 원저자에게 있으며, 변환본을 배포하지 마세요.
- Render 무료 서버는 한 번에 작업 1개만 처리하고, 서버가 재시작되면 진행 중 작업과 구글 로그인이 사라집니다.
- 수식·동영상·미리보기 위젯 같은 동적 요소는 PDF 에 들어가지 않습니다.
