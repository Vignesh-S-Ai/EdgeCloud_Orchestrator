"""Edge Node package for Edge-Cloud Orchestration.

The Edge Node is responsible for capturing video, running local YOLOv8
inference, exposing a FastAPI surface, and reporting system metrics.

Layering rule (see edge/README.md):
    ai/*  ->  api/*  ->  monitoring/*  ->  scheduler/*
All external communication (cloud, dashboard) happens ONLY through the API layer.
"""

__version__ = "0.1.0"
