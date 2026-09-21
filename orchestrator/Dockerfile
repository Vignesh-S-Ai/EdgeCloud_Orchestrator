# syntax=docker/dockerfile:1
# Orchestrator — lightweight, no ML deps.  Imports scheduler.models at runtime,
# so the scheduler package is copied alongside the orchestrator code.
# Build: docker build -f orchestrator/Dockerfile -t orchestrator:0.1.0 .

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY scheduler/requirements.txt ./scheduler-requirements.txt
COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY scheduler/ /app/scheduler/
COPY orchestrator/ /app/orchestrator/

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health', timeout=3)"

CMD ["uvicorn", "orchestrator.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8003"]
