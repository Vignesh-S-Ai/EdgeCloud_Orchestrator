"""Edge-Cloud Decision Engine (Module 3).

Deterministic, rule-based placement engine that decides whether a workload
runs on the Edge Node or is offloaded to the Cloud Node. The engine is
independent of YOLO, FastAPI internals and KubeEdge; the rule-based policy can
be swapped for an ML/RL policy through the same interface.
"""

__version__ = "0.1.0"
