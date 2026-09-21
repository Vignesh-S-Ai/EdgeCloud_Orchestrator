# syntax=docker/dockerfile:1
# Scheduler (Decision Engine) — lightweight, no ML deps.
# Build: docker build -f scheduler/Dockerfile -t scheduler:0.1.0 .

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY scheduler/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY scheduler/ /app/scheduler/

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=3)"

CMD ["uvicorn", "scheduler.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8002"]
