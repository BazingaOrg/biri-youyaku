# 默认 image 体积优先，**不预装 ASR extras**（funasr + torch 加起来几个 GB）。
# 如果你的视频没有官方字幕、需要本地 ASR 转写，把下面 `uv sync` 那行改成：
#   RUN uv sync --frozen --no-dev --extra asr
# 注意 asr-mlx 是 Apple Silicon 专属，Linux Docker 装不上别用。
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
