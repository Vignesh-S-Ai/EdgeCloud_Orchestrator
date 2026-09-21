# syntax=docker/dockerfile:1
# --------------------------------------------------------------------------
# Cloud Node image - production build (CPU-only, non-root, slim).
# Build from the repository root so the whole repo is the build context:
#     docker build -f cloud/Dockerfile -t cloud-node:0.1.0 .
# --------------------------------------------------------------------------

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CLOUD_HOST=0.0.0.0 \
    CLOUD_PORT=8001

# OpenCV headless still needs glib; Ultralytics needs OpenMP.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only PyTorch first (small image), then the rest.
# ultralytics pulls the GUI opencv-python wheel; force the headless wheel to
# win afterwards so the slim image has no X11/libxcb runtime requirements.
COPY cloud/requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision \
    && pip install -r requirements.txt \
    && pip install --no-cache-dir --no-deps --force-reinstall \
        "opencv-python-headless>=4.10,<5.0"

# Copy the Cloud Node package (keeps the image free of host-side code).
COPY cloud/ /app/cloud/

# Non-root runtime user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=3)"

CMD ["uvicorn", "cloud.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
