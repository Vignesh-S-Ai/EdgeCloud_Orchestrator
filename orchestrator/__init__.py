"""Edge-Cloud Orchestrator (Module 4).

Single entry point that ties the Edge Node (M1), Cloud Node (M2) and the
Decision Engine (M3) into one end-to-end workflow:

    WORKLOAD -> ORCHESTRATOR -> SCHEDULER -> EDGE/CLOUD -> INFERENCE -> RESULT

The orchestrator never decides placement itself; it asks the scheduler for a
``/decision``, then forwards the same ``image_base64`` to the chosen node and
returns a unified, latency-annotated result. It only talks to public APIs
(``/decision``, ``/detect``, ``/infer``, ``/health``) and never touches module
internals, preserving the edge/cloud AI-isolation invariant.
"""

__version__ = "0.1.0"
