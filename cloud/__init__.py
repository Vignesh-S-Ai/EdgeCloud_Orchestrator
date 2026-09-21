"""Cloud Node package for Edge-Cloud Orchestration.

The Cloud Node is the remote inference service (AWS EC2 Free Tier target). It
receives base64-encoded images from Edge Nodes, runs YOLOv8 inference and
returns detection results plus system metrics, establishing the

    EDGE -> CLOUD -> INFERENCE -> RESULT -> EDGE

flow.

Layering rule (see cloud/README.md):
    ai/*  ->  api/*  ->  monitoring/*
All external communication (Edge nodes, dashboard) happens ONLY through the
API layer.
"""

__version__ = "0.1.0"
