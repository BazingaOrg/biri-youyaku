FROM python:3.11-slim

# ffmpeg / ffprobe：SenseVoice 分段切片需要
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/*

# 装 uv（编译期）
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev

COPY biri_youyaku /app/biri_youyaku

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 17821
CMD ["uv", "run", "--no-dev", "uvicorn", "biri_youyaku.app:app", "--host", "0.0.0.0", "--port", "17821"]
