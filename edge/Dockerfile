# syntax=docker/dockerfile:1
# --------------------------------------------------------------------------
# Edge Node image - production build (CPU-only, non-root, slim).
# Build from the repository root so the whole repo is the build context:
#     docker build -f edge/Dockerfile -t edge-node:0.1.0 .
# --------------------------------------------------------------------------

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EDGE_HOST=0.0.0.0 \
    EDGE_PORT=8000

# OpenCV headless still needs glib; Ultralytics needs OpenMP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only PyTorch first (small image), then the rest.
COPY edge/requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision \
    && pip install -r requirements.txt \
    && pip install --no-cache-dir --no-deps --force-reinstall \
        "opencv-python-headless>=4.10,<5.0"

# Copy the Edge Node package (keeps the image free of host-side code).
COPY edge/ /app/edge/

# Non-root runtime user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

CMD ["uvicorn", "edge.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
