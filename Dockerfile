FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY video_quality /workspace/video_quality
COPY pyproject.toml /workspace/pyproject.toml
COPY tests /workspace/tests

CMD ["python", "-m", "video_quality.cli", "run", "--config", "config/experiment.json"]
