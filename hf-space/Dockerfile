# Hugging Face Spaces 용 — GitHub 저장소의 server/ 를 받아 실행합니다.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      fonts-nanum fonts-nanum-coding fonts-noto-color-emoji fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Spaces 는 사용자 ID 1000 으로 실행합니다.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" PYTHONUNBUFFERED=1 WORK_DIR=/tmp/wikidocs2pdf
WORKDIR /home/user/app

# 최신 코드를 받으려면 이 값을 바꾸고 Space 를 다시 빌드(Factory rebuild)하세요.
ARG CODE_VERSION=1
RUN git clone --depth 1 https://github.com/jeong-jihyun/wikidocs-book-to-pdf.git repo
WORKDIR /home/user/app/repo/server
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
