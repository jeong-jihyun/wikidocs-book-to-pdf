# 1단계. 설치 — 변환 서버 이미지
FROM python:3.12-slim

# WeasyPrint 가 쓰는 글자·그림 라이브러리와 한글 글꼴
# - libharfbuzz-subset0 : 글꼴에서 쓰는 글자만 추리는 C 라이브러리. 없으면 변환이 수십 배 느려짐(시험으로 확인)
# - fonts-nanum*        : 한글 본문(나눔고딕)과 코드(나눔고딕코딩)
# - fonts-noto-color-emoji : ✅ 같은 이모지
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      fonts-nanum fonts-nanum-coding fonts-noto-color-emoji fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
# Render 는 PORT 환경변수로 포트를 알려 줍니다. 작업 상태를 메모리에 두므로 worker 는 1개만.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
