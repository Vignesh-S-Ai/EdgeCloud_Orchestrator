# Phase 10 — Gate 10C: CloudCore Router REST TLS (east-west) — NOT IMPLEMENTED

**Date:** 2026-09-02
**Predecessor:** Gate 10B (PASS/CLOSED, `docs/phase10/10B_release.md`)
**Gate:** 10C — "secure CloudCore REST `http://10.0.1.113:9443` via HTTPS with cert verification (internal east-west CloudCore REST)."

## STATUS: NOT APPROVED / NOT IMPLEMENTED
## VERDICT: PASS WITH LIMITATION

**Reason:** Native CloudCore Router REST TLS is unavailable in the deployed KubeEdge v1.23.1 version. Adding a proxy or maintaining a custom CloudCore build would introduce an architectural change beyond the approved Phase 10 scope.

---

## 1. Source/config investigation proving native REST TLS is unavailable

Live CloudCore instance (read-only investigation; **no production changes made**):

- CloudCore runs as a **systemd service**, not a k8s pod:
  `/usr/local/bin/cloudcore --config /etc/kubeedge/config/cloudcore.yaml` (PID 503357).
- Installed version confirmed: `/etc/kubeedge/kubeedge-v1.23.1-linux-amd64/version` → **`v1.23.1`**.
- Installed source tree is **prebuilt binaries only** (no Go source); native behaviour was therefore verified from the upstream KubeEdge **v1.23.1** source (GitHub).

Three independent confirmations that the Router REST `:9443` server has **no native TLS**:

1. **Server code** — `cloud/pkg/router/listener/http.go`, `RestHandler.Serve()`:
   ```go
   server := &http.Server{ Addr: ..., Handler: mux, /* TODO: add tls for router */ }
   //err := server.ListenAndServeTLS("", "")
   if err := server.ListenAndServe(); err != nil { ... }
   ```
   Always plain `ListenAndServe()`; `ListenAndServeTLS` is commented out with an upstream **`// TODO: add tls for router`**.

2. **Config schema** — `staging/src/github.com/kubeedge/api/apis/componentconfig/cloudcore/v1alpha1/types.go`, `type Router struct`:
   ```go
   type Router struct {
       Enable      bool   `json:"enable"`
       Address     string `json:"address,omitempty"`
       Port        uint32 `json:"port,omitempty"`
       RestTimeout uint32 `json:"restTimeout,omitempty"`
   }
   ```
   No `tlsCAFile` / `tlsCertFile` / `tlsPrivateKeyFile` — unlike `CloudHub` and `CloudStream`, which do define TLS fields. The Router has no TLS knobs.

3. **Installed instance** — running cloudcore v1.23.1 config `modules.router` has only `address/enable/port/restTimeout`; no TLS keys.

Client-side touch-point (not exercised, recorded for any future TLS path): the orchestrator's `EdgeClient` (`orchestrator/clients.py`) and the scheduler's `MetricsClient` (`scheduler/metrics_client.py`) both use `httpx.AsyncClient(...)` with default `verify=True`. Under TLS they would need the private CA supplied (env `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` via httpx `trust_env`, or explicit `verify=` path). **No `verify=False` would be used** (gate forbids it).

## 2. Current :9443 transport remains HTTP

`:9443` remains a plaintext CloudCore Router REST listener. No TLS was added because native TLS is not available and adding a proxy/build is out of the approved scope.

## 3. :9443 remains internal-only and is NOT exposed through the Cloud SG

`:9443` stays restricted to the internal east-west path (orchestrator/scheduler → CloudCore). It is **not** opened to the public internet and **not** exposed through the Cloud security group.

## 4. Existing edge :8000 security posture remains unchanged

The edge node's `:8000` remains blocked externally (no public exposure). Direct `edge:8000` still times out. This security posture is unchanged by 10C.

## 5. CloudHub :10000/:10002 existing TLS remains unchanged

The CloudHub channel listeners (`:10000` websocket, `:10002` HTTPS) continue to use their existing TLS configuration (`tlsCAFile`/`tlsCertFile`/`tlsPrivateKeyFile` under `modules.cloudHub`). Untouched by 10C.

## 6. No production changes were made during 10C

Investigation only (SSM read-only diagnostics + upstream source fetch). No CloudCore config, no deployment, no Security Group, no IAM, no Terraform, no code change.

## 7. No rollback is required

Nothing was mutated, so there is nothing to roll back. (Pre-existing host backup `/etc/kubeedge/config/cloudcore.yaml.bak.gate2` remains in place from a prior phase.)

## 8. Future options recorded, NOT implemented

The following remain **future options only** and were **not** implemented:
- Deploy an nginx / TLS-terminating reverse proxy in front of CloudCore REST `:9443`.
- Patch and rebuild a custom CloudCore binary to add native router TLS (upstream TODO).

---

## Decision

**Gate 10C: SKIPPED — NOT APPROVED / NOT IMPLEMENTED — PASS WITH LIMITATION** (the limitation being: CloudCore Router REST :9443 remains HTTP because native TLS is unavailable in KubeEdge v1.23.1).

**10C is STOPPED.** Proceeding to **Gate 10D** as instructed, after this report.
